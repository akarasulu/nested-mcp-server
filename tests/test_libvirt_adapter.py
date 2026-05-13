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
