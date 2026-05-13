import pytest

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.errors import MCPError
from libvirt_mcp_server.tools import network_tools, storage_tools


class FakeLibvirtAdapter:
    def __init__(self):
        self.last = None

    def define_network_xml(self, uri, network_xml):
        self.last = ("define_network_xml", uri, network_xml)
        return {"source": "libvirt", "status": "defined"}

    def start_network(self, uri, network_name):
        self.last = ("start_network", uri, network_name)
        return {"source": "libvirt", "status": "started", "network_name": network_name}

    def define_storage_pool_xml(self, uri, pool_xml):
        self.last = ("define_storage_pool_xml", uri, pool_xml)
        return {"source": "libvirt", "status": "defined"}

    def create_storage_volume_xml(self, uri, pool_name, volume_xml):
        self.last = ("create_storage_volume_xml", uri, pool_name, volume_xml)
        return {"source": "libvirt", "status": "created", "pool_name": pool_name}

    def get_storage_pool_xml(self, uri, pool_name):
        self.last = ("get_storage_pool_xml", uri, pool_name)
        return {"source": "libvirt", "pool_name": pool_name, "xml": "<pool/>"}

    def get_storage_pool_metadata(self, uri, pool_name):
        self.last = ("get_storage_pool_metadata", uri, pool_name)
        return {"source": "libvirt", "pool_name": pool_name, "has_metadata": False}

    def get_storage_volume_metadata(self, uri, pool_name, volume_name):
        self.last = ("get_storage_volume_metadata", uri, pool_name, volume_name)
        return {"source": "libvirt", "pool_name": pool_name, "volume_name": volume_name, "has_metadata": True}

    def upload_storage_volume(self, uri, pool_name, volume_name, source_path, *, offset, length):
        self.last = ("upload_storage_volume", uri, pool_name, volume_name, source_path, offset, length)
        return {
            "source": "libvirt",
            "status": "uploaded",
            "pool_name": pool_name,
            "volume_name": volume_name,
            "source_path": source_path,
            "offset": offset,
            "length": length,
            "bytes_transferred": length,
        }

    def download_storage_volume(self, uri, pool_name, volume_name, target_path, *, offset, length):
        self.last = ("download_storage_volume", uri, pool_name, volume_name, target_path, offset, length)
        return {
            "source": "libvirt",
            "status": "downloaded",
            "pool_name": pool_name,
            "volume_name": volume_name,
            "target_path": target_path,
            "offset": offset,
            "length": length,
            "bytes_transferred": length or 0,
        }


@pytest.fixture
def config():
    cfg = ServerConfig.from_env()
    cfg.allow_mutations = True
    cfg.allow_define = True
    cfg.test_resource_prefix = "mcp_test_"
    return cfg


def test_define_network_xml_requires_test_prefix(config):
    adapter = FakeLibvirtAdapter()

    with pytest.raises(MCPError) as exc:
        network_tools.define_network_xml(
            config,
            adapter,
            network_xml="<network><name>prod-net</name></network>",
            hypervisor_ref=None,
        )

    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_start_network_allows_test_prefix(config):
    adapter = FakeLibvirtAdapter()

    result = network_tools.start_network(
        config,
        adapter,
        network_name="mcp_test_net",
        hypervisor_ref=None,
    )

    assert result["status"] == "started"
    assert result["network_name"] == "mcp_test_net"


def test_define_storage_pool_xml_requires_test_prefix(config):
    adapter = FakeLibvirtAdapter()

    pool_xml = """
<pool type='dir'>
  <name>prod_pool</name>
  <target><path>/tmp/prod_pool</path></target>
</pool>
"""

    with pytest.raises(MCPError) as exc:
        storage_tools.define_storage_pool_xml(
            config,
            adapter,
            pool_xml=pool_xml,
            hypervisor_ref=None,
        )

    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_create_storage_volume_xml_requires_prefixed_pool_and_volume(config):
    adapter = FakeLibvirtAdapter()

    volume_xml = """
<volume>
  <name>mcp_test_vol.qcow2</name>
  <capacity unit='bytes'>1048576</capacity>
  <target><format type='qcow2'/></target>
</volume>
"""

    with pytest.raises(MCPError) as exc:
        storage_tools.create_storage_volume_xml(
            config,
            adapter,
            pool_name="non_test_pool",
            volume_xml=volume_xml,
            hypervisor_ref=None,
        )

    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_create_storage_volume_xml_allows_prefixed_names(config):
    adapter = FakeLibvirtAdapter()

    volume_xml = """
<volume>
  <name>mcp_test_vol.qcow2</name>
  <capacity unit='bytes'>1048576</capacity>
  <target><format type='qcow2'/></target>
</volume>
"""

    result = storage_tools.create_storage_volume_xml(
        config,
        adapter,
        pool_name="mcp_test_pool",
        volume_xml=volume_xml,
        hypervisor_ref=None,
    )

    assert result["status"] == "created"
    assert result["pool_name"] == "mcp_test_pool"


def test_get_storage_pool_xml_is_readonly(config):
    adapter = FakeLibvirtAdapter()
    config.allow_mutations = False

    result = storage_tools.get_storage_pool_xml(config, adapter, pool_name="pool0", hypervisor_ref=None)

    assert result["xml"] == "<pool/>"
    assert result["hypervisor_ref"] == "default"
    assert adapter.last == ("get_storage_pool_xml", "qemu:///system", "pool0")


def test_get_storage_pool_metadata_is_readonly(config):
    adapter = FakeLibvirtAdapter()
    config.allow_mutations = False

    result = storage_tools.get_storage_pool_metadata(config, adapter, pool_name="pool0", hypervisor_ref=None)

    assert result["has_metadata"] is False
    assert result["hypervisor_ref"] == "default"
    assert adapter.last == ("get_storage_pool_metadata", "qemu:///system", "pool0")


def test_get_storage_volume_metadata_is_readonly(config):
    adapter = FakeLibvirtAdapter()
    config.allow_mutations = False

    result = storage_tools.get_storage_volume_metadata(
        config,
        adapter,
        pool_name="pool0",
        volume_name="vol0",
        hypervisor_ref=None,
    )

    assert result["has_metadata"] is True
    assert result["hypervisor_ref"] == "default"
    assert adapter.last == ("get_storage_volume_metadata", "qemu:///system", "pool0", "vol0")


def test_create_linked_clone_volume_rejects_absolute_backing_when_relative_required(config):
    adapter = FakeLibvirtAdapter()

    with pytest.raises(MCPError) as exc:
        storage_tools.create_linked_clone_volume(
            config,
            adapter,
            pool_name="mcp_test_pool",
            volume_name="mcp_test_child.qcow2",
            backing_file="/var/lib/libvirt/images/vda.qcow2",
            capacity_bytes=1048576,
            format="qcow2",
            backing_format="qcow2",
            relative_backing=True,
            hypervisor_ref=None,
        )

    assert exc.value.code == "INVALID_BACKING_PATH"


def test_create_linked_clone_volume_allows_relative_backing(config):
    adapter = FakeLibvirtAdapter()

    result = storage_tools.create_linked_clone_volume(
        config,
        adapter,
        pool_name="mcp_test_pool",
        volume_name="mcp_test_child.qcow2",
        backing_file="../vda.qcow2",
        capacity_bytes=1048576,
        format="qcow2",
        backing_format="qcow2",
        relative_backing=True,
        hypervisor_ref=None,
    )

    assert result["status"] == "created"
    assert result["pool_name"] == "mcp_test_pool"
    assert result["backing_file"] == "../vda.qcow2"
    assert result["relative_backing"] is True
    assert "<backingStore>" in adapter.last[3]
    assert "../vda.qcow2" in adapter.last[3]


def test_upload_storage_volume_requires_mutations(config, tmp_path):
    config.allow_mutations = False
    adapter = FakeLibvirtAdapter()
    source = tmp_path / "payload.bin"
    source.write_bytes(b"payload")

    with pytest.raises(MCPError) as exc:
        storage_tools.upload_storage_volume(
            config,
            adapter,
            pool_name="mcp_test_pool",
            volume_name="mcp_test_vol.raw",
            source_path=str(source),
            hypervisor_ref=None,
        )

    assert exc.value.code == "MUTATION_DISABLED"


def test_upload_storage_volume_requires_prefixed_names(config, tmp_path):
    adapter = FakeLibvirtAdapter()
    source = tmp_path / "payload.bin"
    source.write_bytes(b"payload")

    with pytest.raises(MCPError) as exc:
        storage_tools.upload_storage_volume(
            config,
            adapter,
            pool_name="prod_pool",
            volume_name="mcp_test_vol.raw",
            source_path=str(source),
            hypervisor_ref=None,
        )

    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_upload_storage_volume_rejects_unsafe_source_path(config):
    adapter = FakeLibvirtAdapter()

    with pytest.raises(MCPError) as exc:
        storage_tools.upload_storage_volume(
            config,
            adapter,
            pool_name="mcp_test_pool",
            volume_name="mcp_test_vol.raw",
            source_path="/etc/passwd",
            hypervisor_ref=None,
        )

    assert exc.value.code == "TRANSFER_PATH_DENIED"


def test_upload_storage_volume_computes_default_length(config, tmp_path):
    adapter = FakeLibvirtAdapter()
    source = tmp_path / "payload.bin"
    source.write_bytes(b"abcdef")

    result = storage_tools.upload_storage_volume(
        config,
        adapter,
        pool_name="mcp_test_pool",
        volume_name="mcp_test_vol.raw",
        source_path=str(source),
        offset=2,
        hypervisor_ref=None,
    )

    assert result["status"] == "uploaded"
    assert result["length"] == 4
    assert adapter.last[-2:] == (2, 4)


def test_upload_storage_volume_rejects_out_of_range(config, tmp_path):
    adapter = FakeLibvirtAdapter()
    source = tmp_path / "payload.bin"
    source.write_bytes(b"abcdef")

    with pytest.raises(MCPError) as exc:
        storage_tools.upload_storage_volume(
            config,
            adapter,
            pool_name="mcp_test_pool",
            volume_name="mcp_test_vol.raw",
            source_path=str(source),
            offset=4,
            length=4,
            hypervisor_ref=None,
        )

    assert exc.value.code == "INVALID_TRANSFER_RANGE"


def test_download_storage_volume_rejects_unsafe_target_path(config):
    adapter = FakeLibvirtAdapter()

    with pytest.raises(MCPError) as exc:
        storage_tools.download_storage_volume(
            config,
            adapter,
            pool_name="mcp_test_pool",
            volume_name="mcp_test_vol.raw",
            target_path="/etc/nested-mcp-download.bin",
            hypervisor_ref=None,
        )

    assert exc.value.code == "TRANSFER_PATH_DENIED"


def test_download_storage_volume_allows_tmp_target(config, tmp_path):
    adapter = FakeLibvirtAdapter()
    target = tmp_path / "download.bin"

    result = storage_tools.download_storage_volume(
        config,
        adapter,
        pool_name="mcp_test_pool",
        volume_name="mcp_test_vol.raw",
        target_path=str(target),
        offset=1,
        length=5,
        hypervisor_ref=None,
    )

    assert result["status"] == "downloaded"
    assert result["length"] == 5
    assert adapter.last[-2:] == (1, 5)
