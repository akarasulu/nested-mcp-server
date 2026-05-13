from __future__ import annotations

import pytest

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.errors import MCPError
from libvirt_mcp_server.tools import snapshot_tools


class FakeSnapshotAdapter:
    def create_domain_snapshot(self, uri, domain_ref, snapshot_xml):
        return {
            "source": "libvirt",
            "domain_ref": domain_ref,
            "snapshot_name": "snap1",
            "status": "created",
        }

    def revert_domain_snapshot(self, uri, domain_ref, snapshot_name):
        return {
            "source": "libvirt",
            "domain_ref": domain_ref,
            "snapshot_name": snapshot_name,
            "status": "reverted",
        }

    def delete_domain_snapshot(self, uri, domain_ref, snapshot_name):
        return {
            "source": "libvirt",
            "domain_ref": domain_ref,
            "snapshot_name": snapshot_name,
            "status": "deleted",
        }


def _cfg() -> ServerConfig:
    cfg = ServerConfig.from_env()
    cfg.allow_mutations = True
    cfg.mutation_domain_allowlist = {"mcp_test_dummy"}
    return cfg


def test_create_snapshot_blocked_when_domain_not_allowlisted():
    cfg = _cfg()
    adapter = FakeSnapshotAdapter()

    with pytest.raises(MCPError) as exc:
        snapshot_tools.create_domain_snapshot(
            cfg,
            adapter,
            domain_ref="deb13",
            snapshot_xml="<domainsnapshot/>",
            hypervisor_ref=None,
        )

    assert exc.value.code == "MUTATION_DOMAIN_DENIED"


def test_create_snapshot_allowed_for_allowlisted_domain():
    cfg = _cfg()
    adapter = FakeSnapshotAdapter()

    result = snapshot_tools.create_domain_snapshot(
        cfg,
        adapter,
        domain_ref="mcp_test_dummy",
        snapshot_xml="<domainsnapshot/>",
        hypervisor_ref=None,
    )

    assert result["domain_ref"] == "mcp_test_dummy"


def test_revert_delete_snapshot_blocked_when_domain_not_allowlisted():
    cfg = _cfg()
    adapter = FakeSnapshotAdapter()

    with pytest.raises(MCPError) as revert_exc:
        snapshot_tools.revert_domain_snapshot(
            cfg,
            adapter,
            domain_ref="deb13",
            snapshot_name="snap1",
            hypervisor_ref=None,
        )
    assert revert_exc.value.code == "MUTATION_DOMAIN_DENIED"

    with pytest.raises(MCPError) as delete_exc:
        snapshot_tools.delete_domain_snapshot(
            cfg,
            adapter,
            domain_ref="deb13",
            snapshot_name="snap1",
            hypervisor_ref=None,
        )
    assert delete_exc.value.code == "MUTATION_DOMAIN_DENIED"
