from __future__ import annotations

from types import SimpleNamespace

import pytest

from libvirt_mcp_server.adapters.libvirt_adapter import LibvirtAdapter
from libvirt_mcp_server.errors import MCPError


class _FakeDomain:
    def __init__(self, name: str, active: bool):
        self._name = name
        self._active = active

    def info(self):
        return (1 if self._active else 5, 2048, 1024, 2, 123)

    def autostart(self):
        return 0

    def name(self):
        return self._name

    def UUIDString(self):
        return f"uuid-{self._name}"

    def isActive(self):
        return self._active


class _ConnDomains:
    def listAllDomains(self):
        return [
            _FakeDomain("vm-active", True),
            _FakeDomain("vm-inactive", False),
            _FakeDomain("other", True),
        ]


def test_list_domains_filter_branches(monkeypatch):
    adapter = LibvirtAdapter()
    monkeypatch.setattr(adapter, "_connect", lambda _uri: _ConnDomains())

    only_active = adapter.list_domains("qemu:///system", active_only=True)
    assert {d["name"] for d in only_active} == {"vm-active", "other"}

    only_inactive = adapter.list_domains("qemu:///system", inactive_only=True)
    assert {d["name"] for d in only_inactive} == {"vm-inactive"}

    prefixed = adapter.list_domains("qemu:///system", name_prefix="vm-")
    assert {d["name"] for d in prefixed} == {"vm-active", "vm-inactive"}


class _ConnPoolLookupFails:
    def storagePoolLookupByName(self, _pool_name: str):
        raise RuntimeError("missing-pool")


def test_list_storage_volumes_pool_not_found_branch(monkeypatch):
    adapter = LibvirtAdapter()
    monkeypatch.setattr(adapter, "_connect", lambda _uri: _ConnPoolLookupFails())

    with pytest.raises(MCPError) as exc:
        adapter.list_storage_volumes("qemu:///system", "missing-pool")

    assert exc.value.code == "STORAGE_POOL_NOT_FOUND"


class _PoolVolumeLookupFails:
    def storageVolLookupByName(self, _name: str):
        raise RuntimeError("missing-volume")


class _ConnPoolOk:
    def storagePoolLookupByName(self, _pool_name: str):
        return _PoolVolumeLookupFails()


def test_get_storage_volume_not_found_branch(monkeypatch):
    adapter = LibvirtAdapter()
    monkeypatch.setattr(adapter, "_connect", lambda _uri: _ConnPoolOk())

    with pytest.raises(MCPError) as exc:
        adapter.get_storage_volume("qemu:///system", "pool", "missing-volume")

    assert exc.value.code == "STORAGE_VOLUME_NOT_FOUND"


class _FakeXmlObject:
    def __init__(self, xml: str):
        self.xml = xml

    def XMLDesc(self, _flags: int):
        return self.xml


class _FakePoolForMetadata(_FakeXmlObject):
    def __init__(self, pool_xml: str, volume_xml: str):
        super().__init__(pool_xml)
        self.volume = _FakeXmlObject(volume_xml)

    def storageVolLookupByName(self, _name: str):
        return self.volume


class _ConnStorageMetadata:
    def __init__(self, pool_xml: str, volume_xml: str):
        self.pool = _FakePoolForMetadata(pool_xml, volume_xml)

    def storagePoolLookupByName(self, _pool_name: str):
        return self.pool


def test_get_storage_pool_metadata_parses_libvirt_xml(monkeypatch):
    pool_xml = """
<pool type='dir'>
  <name>pool0</name>
  <uuid>pool-uuid</uuid>
  <source><dir path='/srv/images'/></source>
  <target><path>/var/lib/libvirt/images</path></target>
  <metadata xmlns:nested='https://example.invalid/nested'><nested:owner>ops</nested:owner></metadata>
</pool>
"""
    adapter = LibvirtAdapter()
    monkeypatch.setattr(adapter, "_connect", lambda _uri: _ConnStorageMetadata(pool_xml, "<volume/>"))

    result = adapter.get_storage_pool_metadata("qemu:///system", "pool0")

    assert result["pool_type"] == "dir"
    assert result["name"] == "pool0"
    assert result["target_path"] == "/var/lib/libvirt/images"
    assert result["pool_source"]["dir"] == "/srv/images"
    assert result["has_metadata"] is True
    assert result["metadata_element_count"] == 1
    assert "https://example.invalid/nested" in result["metadata_namespaces"]


def test_get_storage_volume_metadata_parses_target_and_backing(monkeypatch):
    volume_xml = """
<volume type='file'>
  <name>vol0.qcow2</name>
  <key>/var/lib/libvirt/images/vol0.qcow2</key>
  <capacity unit='MiB'>64</capacity>
  <allocation unit='bytes'>4096</allocation>
  <target>
    <path>/var/lib/libvirt/images/vol0.qcow2</path>
    <format type='qcow2'/>
    <features><lazy_refcounts/></features>
  </target>
  <backingStore>
    <path>base.qcow2</path>
    <format type='qcow2'/>
  </backingStore>
</volume>
"""
    adapter = LibvirtAdapter()
    monkeypatch.setattr(adapter, "_connect", lambda _uri: _ConnStorageMetadata("<pool/>", volume_xml))

    result = adapter.get_storage_volume_metadata("qemu:///system", "pool0", "vol0.qcow2")

    assert result["volume_type"] == "file"
    assert result["capacity_bytes"] == 67108864
    assert result["allocation_bytes"] == 4096
    assert result["target"]["format"] == "qcow2"
    assert result["target"]["features"] == ["lazy_refcounts"]
    assert result["backing_store"] == {"path": "base.qcow2", "format": "qcow2"}
    assert result["has_metadata"] is False


class _DomainCreateFails:
    def snapshotCreateXML(self, _xml: str, _flags: int):
        raise RuntimeError("create-failed")


def test_create_snapshot_failure_branch(monkeypatch):
    adapter = LibvirtAdapter()
    monkeypatch.setattr(adapter, "_connect", lambda _uri: object())
    monkeypatch.setattr(adapter, "_lookup_domain", lambda _c, _d: _DomainCreateFails())

    with pytest.raises(MCPError) as exc:
        adapter.create_domain_snapshot("qemu:///system", "vm", "<domainsnapshot/>")

    assert exc.value.code == "SNAPSHOT_CREATE_FAILED"


class _Snapshot:
    def delete(self, _flags: int):
        raise RuntimeError("delete-failed")


class _DomainRevertFails:
    def snapshotLookupByName(self, _name: str, _flags: int):
        return _Snapshot()

    def revertToSnapshot(self, _snap, _flags: int):
        raise RuntimeError("revert-failed")


class _DomainDeleteLookupFails:
    def snapshotLookupByName(self, _name: str, _flags: int):
        raise RuntimeError("missing-snapshot")


class _DomainDeleteFails:
    def snapshotLookupByName(self, _name: str, _flags: int):
        return _Snapshot()


def test_revert_snapshot_failure_branch(monkeypatch):
    adapter = LibvirtAdapter()
    monkeypatch.setattr(adapter, "_connect", lambda _uri: object())
    monkeypatch.setattr(adapter, "_lookup_domain", lambda _c, _d: _DomainRevertFails())

    with pytest.raises(MCPError) as exc:
        adapter.revert_domain_snapshot("qemu:///system", "vm", "snap1")

    assert exc.value.code == "SNAPSHOT_REVERT_FAILED"


def test_delete_snapshot_lookup_failure_branch(monkeypatch):
    adapter = LibvirtAdapter()
    monkeypatch.setattr(adapter, "_connect", lambda _uri: object())
    monkeypatch.setattr(adapter, "_lookup_domain", lambda _c, _d: _DomainDeleteLookupFails())

    with pytest.raises(MCPError) as exc:
        adapter.delete_domain_snapshot("qemu:///system", "vm", "snap-missing")

    assert exc.value.code == "SNAPSHOT_NOT_FOUND"


def test_delete_snapshot_delete_failure_branch(monkeypatch):
    adapter = LibvirtAdapter()
    monkeypatch.setattr(adapter, "_connect", lambda _uri: object())
    monkeypatch.setattr(adapter, "_lookup_domain", lambda _c, _d: _DomainDeleteFails())

    with pytest.raises(MCPError) as exc:
        adapter.delete_domain_snapshot("qemu:///system", "vm", "snap1")

    assert exc.value.code == "SNAPSHOT_DELETE_FAILED"


class _FakeStream:
    def __init__(self, incoming: bytes = b""):
        self.incoming = incoming
        self.sent = bytearray()
        self.finished = False
        self.aborted = False

    def send(self, data: bytes):
        self.sent.extend(data)
        return len(data)

    def recv(self, size: int):
        if not self.incoming:
            return b""
        chunk = self.incoming[:size]
        self.incoming = self.incoming[size:]
        return chunk

    def finish(self):
        self.finished = True

    def abort(self):
        self.aborted = True


class _FakeVolumeForTransfer:
    def __init__(self):
        self.upload_args = None
        self.download_args = None

    def upload(self, stream, offset, length, flags):
        self.upload_args = (stream, offset, length, flags)

    def download(self, stream, offset, length, flags):
        self.download_args = (stream, offset, length, flags)


class _FakePoolForTransfer:
    def __init__(self, volume):
        self.volume = volume

    def storageVolLookupByName(self, _name):
        return self.volume


class _FakeConnForTransfer:
    def __init__(self, stream, volume):
        self.stream = stream
        self.volume = volume

    def storagePoolLookupByName(self, _name):
        return _FakePoolForTransfer(self.volume)

    def newStream(self, _flags):
        return self.stream


def test_upload_storage_volume_streams_file(monkeypatch, tmp_path):
    source = tmp_path / "payload.bin"
    source.write_bytes(b"abcdef")
    stream = _FakeStream()
    volume = _FakeVolumeForTransfer()
    conn = _FakeConnForTransfer(stream, volume)
    adapter = LibvirtAdapter()
    monkeypatch.setattr(adapter, "_connect", lambda _uri: conn)

    result = adapter.upload_storage_volume(
        "qemu:///system",
        "pool",
        "volume.raw",
        str(source),
        offset=2,
        length=3,
    )

    assert result["status"] == "uploaded"
    assert result["bytes_transferred"] == 3
    assert bytes(stream.sent) == b"cde"
    assert stream.finished is True
    assert volume.upload_args[1:] == (2, 3, 0)


def test_download_storage_volume_streams_to_file(monkeypatch, tmp_path):
    target = tmp_path / "download.bin"
    stream = _FakeStream(incoming=b"abcdef")
    volume = _FakeVolumeForTransfer()
    conn = _FakeConnForTransfer(stream, volume)
    adapter = LibvirtAdapter()
    monkeypatch.setattr(adapter, "_connect", lambda _uri: conn)

    result = adapter.download_storage_volume(
        "qemu:///system",
        "pool",
        "volume.raw",
        str(target),
        offset=1,
        length=4,
    )

    assert result["status"] == "downloaded"
    assert result["bytes_transferred"] == 4
    assert target.read_bytes() == b"abcd"
    assert stream.finished is True
    assert volume.download_args[1:] == (1, 4, 0)


def test_parse_host_numa_cells_from_capabilities():
    adapter = LibvirtAdapter()
    xml = """
<capabilities>
  <host>
    <topology>
      <cells num='1'>
        <cell id='0'>
          <memory unit='KiB'>2097152</memory>
          <cpus num='2'>
            <cpu id='0' socket_id='0' core_id='0' siblings='0-1'/>
            <cpu id='1' socket_id='0' core_id='0' siblings='0-1'/>
          </cpus>
        </cell>
      </cells>
    </topology>
  </host>
</capabilities>
"""
    cells = adapter._parse_host_numa_cells(xml)
    assert cells == [
        {
            "cell_id": 0,
            "memory_kb": 2097152,
            "cpus": [
                {"id": 0, "socket_id": 0, "core_id": 0, "siblings": "0-1"},
                {"id": 1, "socket_id": 0, "core_id": 0, "siblings": "0-1"},
            ],
            "cpu_count": 2,
        }
    ]


def test_parse_domain_numa_xml():
    adapter = LibvirtAdapter()
    xml = """
<domain>
  <name>mcp_test_vm1</name>
  <cpu>
    <numa>
      <cell id='0' cpus='0-1' memory='1024' unit='MiB'/>
    </numa>
  </cpu>
</domain>
"""
    parsed = adapter._parse_domain_numa_xml(xml)
    assert parsed["numa_configured"] is True
    assert parsed["cells"] == [{"cell_id": 0, "cpus": "0-1", "memory_kb": 1048576, "unit": "KiB"}]


class _FakeDomainForNuma:
    def __init__(self):
        self.defined_xml = None

    def XMLDesc(self, _flags):
        return """
<domain type='kvm'>
  <name>mcp_test_vm1</name>
  <memory unit='KiB'>1048576</memory>
  <vcpu>1</vcpu>
</domain>
"""


class _FakeConnForNuma:
    def __init__(self, domain):
        self.domain = domain
        self.defined_xml = None

    def defineXML(self, xml):
        self.defined_xml = xml
        return self.domain


def test_set_domain_numa_topology_redefines_domain_xml(monkeypatch):
    adapter = LibvirtAdapter()
    domain = _FakeDomainForNuma()
    conn = _FakeConnForNuma(domain)
    monkeypatch.setattr(adapter, "_connect", lambda _uri: conn)
    monkeypatch.setattr(adapter, "_lookup_domain", lambda _conn, _ref: domain)

    result = adapter.set_domain_numa_topology(
        "qemu:///system",
        "mcp_test_vm1",
        [{"cell_id": 0, "cpus": "0", "memory_kb": 1048576}],
    )

    assert result["status"] == "numa_topology_updated"
    assert "<numa><cell id=\"0\" cpus=\"0\" memory=\"1048576\" unit=\"KiB\" /></numa>" in conn.defined_xml
