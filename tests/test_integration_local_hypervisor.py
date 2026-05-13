"""Integration tests against a local hypervisor.

These tests are intentionally opt-in and must target dedicated test resources.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time

import pytest

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.server import LibvirtMCPServer


pytestmark = pytest.mark.integration


def _get_test_domain_env() -> str:
    # Prefer a generic test-domain variable and keep backward compatibility.
    return os.getenv("LIBVIRT_MCP_TEST_DOMAIN", "") or os.getenv("LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN", "")


def test_local_hypervisor_readonly_smoke():
    if os.getenv("LIBVIRT_MCP_RUN_INTEGRATION") != "1":
        pytest.skip("Set LIBVIRT_MCP_RUN_INTEGRATION=1 to run integration tests")

    # Guard against accidental production targeting.
    test_prefix = os.getenv("LIBVIRT_MCP_TEST_PREFIX", "mcp_test_")
    prod_markers = ["prod", "production", "critical"]
    if any(marker in test_prefix.lower() for marker in prod_markers):
        pytest.skip("Unsafe test prefix indicates production-like resources")

    cfg = ServerConfig.from_env()
    server = LibvirtMCPServer(config=cfg)

    host_numa = asyncio.run(server.call_tool("get_host_numa_topology", {}))
    assert "error" not in host_numa
    assert "numa_supported" in host_numa

    host = asyncio.run(server.call_tool("host_info", {}))
    assert "error" not in host
    assert "capabilities_summary" in host
    assert "capabilities_xml" not in host

    policy_scopes = asyncio.run(server.call_tool("get_policy_scopes", {}))
    assert "error" not in policy_scopes
    assert policy_scopes["total_count"] >= 1

    replayed_events = asyncio.run(server.call_tool("qmp_replay_events", {"limit": 10}))
    assert "error" not in replayed_events
    assert "items" in replayed_events

    domains = asyncio.run(server.call_tool("list_domains", {"active_only": False, "inactive_only": False}))
    assert "error" not in domains
    assert "items" in domains

    networks = asyncio.run(server.call_tool("list_networks", {}))
    assert "error" not in networks

    pools = asyncio.run(server.call_tool("list_storage_pools", {}))
    assert "error" not in pools

    if networks.get("items"):
        network_name = networks["items"][0]["name"]
        network = asyncio.run(server.call_tool("get_network", {"network_name": network_name}))
        assert "error" not in network
        assert network["name"] == network_name

    if pools.get("items"):
        pool_name = pools["items"][0]["name"]
        pool = asyncio.run(server.call_tool("get_storage_pool", {"pool_name": pool_name}))
        assert "error" not in pool
        assert pool["name"] == pool_name

        pool_xml = asyncio.run(server.call_tool("get_storage_pool_xml", {"pool_name": pool_name}))
        assert "error" not in pool_xml
        assert "<pool" in pool_xml["xml"]

        pool_metadata = asyncio.run(server.call_tool("get_storage_pool_metadata", {"pool_name": pool_name}))
        assert "error" not in pool_metadata
        assert "has_metadata" in pool_metadata

        # Try to list volumes, but skip if pool is not active
        volumes = asyncio.run(server.call_tool("list_storage_volumes", {"pool_name": pool_name}))
        if "error" not in volumes and volumes.get("items"):
            vol_name = volumes["items"][0]["name"]
            vol = asyncio.run(
                server.call_tool(
                    "get_storage_volume",
                    {"pool_name": pool_name, "volume_name": vol_name},
                )
            )
            assert "error" not in vol
            assert vol["name"] == vol_name

            vol_metadata = asyncio.run(
                server.call_tool(
                    "get_storage_volume_metadata",
                    {"pool_name": pool_name, "volume_name": vol_name},
                )
            )
            assert "error" not in vol_metadata
            assert "has_metadata" in vol_metadata

    if domains.get("items"):
        domain_ref = domains["items"][0]["name"]
        snapshots = asyncio.run(server.call_tool("list_domain_snapshots", {"domain_ref": domain_ref}))
        assert "error" not in snapshots


def test_domain_introspection():
    """Read-only domain introspection tests on any available domain."""
    if os.getenv("LIBVIRT_MCP_RUN_INTEGRATION") != "1":
        pytest.skip("Set LIBVIRT_MCP_RUN_INTEGRATION=1 to run integration tests")

    cfg = ServerConfig.from_env()
    server = LibvirtMCPServer(config=cfg)

    # List all domains
    domains = asyncio.run(server.call_tool("list_domains", {}))
    assert "error" not in domains
    assert "items" in domains
    assert len(domains["items"]) > 0

    # Get details on first domain
    domain_ref = domains["items"][0]["name"]
    domain = asyncio.run(server.call_tool("get_domain", {"domain_ref": domain_ref}))
    assert "error" not in domain
    assert domain["name"] == domain_ref
    assert "state" in domain
    assert "vcpu_count" in domain

    # Get domain XML (inactive and live variants)
    xml_inactive = asyncio.run(
        server.call_tool("get_domain_xml", {"domain_ref": domain_ref, "inactive": True, "live": False})
    )
    assert "error" not in xml_inactive
    assert "xml" in xml_inactive
    assert "<domain" in xml_inactive["xml"]

    xml_live = asyncio.run(
        server.call_tool("get_domain_xml", {"domain_ref": domain_ref, "inactive": False, "live": True})
    )
    assert "error" not in xml_live
    assert "xml" in xml_live

    numa = asyncio.run(server.call_tool("get_domain_numa_topology", {"domain_ref": domain_ref}))
    assert "error" not in numa
    assert "numa_configured" in numa


def test_hypervisor_discovery():
    """Test hypervisor and host discovery operations."""
    if os.getenv("LIBVIRT_MCP_RUN_INTEGRATION") != "1":
        pytest.skip("Set LIBVIRT_MCP_RUN_INTEGRATION=1 to run integration tests")

    cfg = ServerConfig.from_env()
    server = LibvirtMCPServer(config=cfg)

    # List hypervisors
    hypervisors = asyncio.run(server.call_tool("list_hypervisors", {}))
    assert "error" not in hypervisors
    assert "items" in hypervisors
    assert len(hypervisors["items"]) > 0

    # Get default hypervisor
    hyp_ref = hypervisors["items"][0]["hypervisor_ref"]
    hypervisor = asyncio.run(server.call_tool("get_hypervisor", {"hypervisor_ref": hyp_ref}))
    assert "error" not in hypervisor
    assert hypervisor["hypervisor_ref"] == hyp_ref


def test_qmp_operations():
    """Test QMP query operations."""
    if os.getenv("LIBVIRT_MCP_RUN_INTEGRATION") != "1":
        pytest.skip("Set LIBVIRT_MCP_RUN_INTEGRATION=1 to run integration tests")

    cfg = ServerConfig.from_env()
    server = LibvirtMCPServer(config=cfg)

    # Get first domain
    domains = asyncio.run(server.call_tool("list_domains", {"active_only": False}))
    if not domains.get("items"):
        pytest.skip("No domains available for QMP testing")

    domain_ref = domains["items"][0]["name"]

    # Query QMP status (safe read-only operation)
    # This may fail if domain is not running or QMP is unavailable
    status = asyncio.run(
        server.call_tool("qmp_command", {"domain_ref": domain_ref, "command": "query-status"})
    )
    # Accept either success or graceful failure (not in allowlist, not running, etc.)
    assert isinstance(status, dict)
    # If successful, verify response structure
    if "error" not in status and status.get("response"):
        assert "return" in status["response"] or "error" in status["response"]


def test_snapshot_mutation_cycle_on_dedicated_test_vm():
    """Full snapshot lifecycle: create -> list -> revert -> delete."""
    if os.getenv("LIBVIRT_MCP_RUN_INTEGRATION") != "1":
        pytest.skip("Set LIBVIRT_MCP_RUN_INTEGRATION=1 to run integration tests")

    test_prefix = os.getenv("LIBVIRT_MCP_TEST_PREFIX", "mcp_test_")
    prod_markers = ["prod", "production", "critical"]
    if any(marker in test_prefix.lower() for marker in prod_markers):
        pytest.skip("Unsafe test prefix indicates production-like resources")

    domain_ref = _get_test_domain_env()
    if not domain_ref:
        pytest.skip("Set LIBVIRT_MCP_TEST_DOMAIN (or LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN) to a dedicated non-production VM")
    if not domain_ref.startswith(test_prefix):
        pytest.skip("LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN must start with LIBVIRT_MCP_TEST_PREFIX")

    cfg = ServerConfig.from_env()
    cfg.allow_mutations = True
    cfg.allow_define = True
    server = LibvirtMCPServer(config=cfg)

    snapshot_name = f"{test_prefix}snap_{int(time.time())}"
    snapshot_xml = (
        "<domainsnapshot>"
        f"<name>{snapshot_name}</name>"
        "<description>integration snapshot cycle</description>"
        "</domainsnapshot>"
    )

    create = asyncio.run(
        server.call_tool(
            "create_domain_snapshot",
            {"domain_ref": domain_ref, "snapshot_xml": snapshot_xml},
        )
    )
    assert "error" not in create
    assert create["snapshot_name"] == snapshot_name

    listed = asyncio.run(server.call_tool("list_domain_snapshots", {"domain_ref": domain_ref}))
    assert "error" not in listed
    assert any(item["name"] == snapshot_name for item in listed.get("items", []))

    reverted = asyncio.run(
        server.call_tool(
            "revert_domain_snapshot",
            {"domain_ref": domain_ref, "snapshot_name": snapshot_name},
        )
    )
    assert "error" not in reverted
    assert reverted["snapshot_name"] == snapshot_name

    deleted = asyncio.run(
        server.call_tool(
            "delete_domain_snapshot",
            {"domain_ref": domain_ref, "snapshot_name": snapshot_name},
        )
    )
    assert "error" not in deleted
    assert deleted["snapshot_name"] == snapshot_name


def test_domain_lifecycle_mutations_on_test_vm():
    """Test domain lifecycle operations (start/stop/reboot/suspend/resume) on dedicated test VM."""
    if os.getenv("LIBVIRT_MCP_RUN_INTEGRATION") != "1":
        pytest.skip("Set LIBVIRT_MCP_RUN_INTEGRATION=1 to run integration tests")

    test_prefix = os.getenv("LIBVIRT_MCP_TEST_PREFIX", "mcp_test_")
    prod_markers = ["prod", "production", "critical"]
    if any(marker in test_prefix.lower() for marker in prod_markers):
        pytest.skip("Unsafe test prefix indicates production-like resources")

    domain_ref = _get_test_domain_env()
    if not domain_ref:
        pytest.skip("Set LIBVIRT_MCP_TEST_DOMAIN (or LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN) to a dedicated non-production VM")
    if not domain_ref.startswith(test_prefix):
        pytest.skip("LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN must start with LIBVIRT_MCP_TEST_PREFIX")

    cfg = ServerConfig.from_env()
    cfg.allow_mutations = True
    cfg.allow_define = True
    server = LibvirtMCPServer(config=cfg)

    # Start domain (safe to retry)
    start = asyncio.run(server.call_tool("start_domain", {"domain_ref": domain_ref}))
    assert "error" not in start or "already running" in str(start.get("error", "")).lower()

    # Small delay for domain to start
    time.sleep(0.5)

    # Get domain state after start attempt
    domain = asyncio.run(server.call_tool("get_domain", {"domain_ref": domain_ref}))
    assert "error" not in domain
    initial_state = domain["state"]

    # Suspend (pause) domain
    suspend = asyncio.run(server.call_tool("suspend_domain", {"domain_ref": domain_ref}))
    # May succeed or fail depending on current state
    if "error" not in suspend:
        time.sleep(0.2)
        domain = asyncio.run(server.call_tool("get_domain", {"domain_ref": domain_ref}))
        assert "error" not in domain
        assert domain["state"].lower() == "paused"

        # Resume domain
        resume = asyncio.run(server.call_tool("resume_domain", {"domain_ref": domain_ref}))
        assert "error" not in resume
        time.sleep(0.2)

    # Reboot domain (if it's running)
    domain = asyncio.run(server.call_tool("get_domain", {"domain_ref": domain_ref}))
    if domain.get("state", "").lower() == "running":
        reboot = asyncio.run(server.call_tool("reboot_domain", {"domain_ref": domain_ref}))
        # Reboot may succeed or fail depending on guest support
        assert isinstance(reboot, dict)

    # Shutdown domain (graceful, may take time)
    shutdown = asyncio.run(server.call_tool("shutdown_domain", {"domain_ref": domain_ref}))
    assert "error" not in shutdown

    time.sleep(0.5)
    domain = asyncio.run(server.call_tool("get_domain", {"domain_ref": domain_ref}))
    # Domain should be stopped or stopping
    assert "error" not in domain


def test_domain_autostart_on_test_vm():
    """Test set_domain_autostart operation."""
    if os.getenv("LIBVIRT_MCP_RUN_INTEGRATION") != "1":
        pytest.skip("Set LIBVIRT_MCP_RUN_INTEGRATION=1 to run integration tests")

    test_prefix = os.getenv("LIBVIRT_MCP_TEST_PREFIX", "mcp_test_")
    prod_markers = ["prod", "production", "critical"]
    if any(marker in test_prefix.lower() for marker in prod_markers):
        pytest.skip("Unsafe test prefix indicates production-like resources")

    domain_ref = _get_test_domain_env()
    if not domain_ref:
        pytest.skip("Set LIBVIRT_MCP_TEST_DOMAIN (or LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN) to a dedicated non-production VM")
    if not domain_ref.startswith(test_prefix):
        pytest.skip("LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN must start with LIBVIRT_MCP_TEST_PREFIX")

    cfg = ServerConfig.from_env()
    cfg.allow_mutations = True
    server = LibvirtMCPServer(config=cfg)

    # Disable autostart
    disable = asyncio.run(server.call_tool("set_domain_autostart", {"domain_ref": domain_ref, "autostart": False}))
    assert "error" not in disable
    assert disable["autostart"] is False

    # Enable autostart
    enable = asyncio.run(server.call_tool("set_domain_autostart", {"domain_ref": domain_ref, "autostart": True}))
    assert "error" not in enable
    assert enable["autostart"] is True

    # Disable again (cleanup)
    disable = asyncio.run(server.call_tool("set_domain_autostart", {"domain_ref": domain_ref, "autostart": False}))
    assert "error" not in disable


def test_define_destroy_parity_for_network_storage_and_domain():
    """Integration mutation parity for network/storage/domain define-destroy flows."""
    if os.getenv("LIBVIRT_MCP_RUN_INTEGRATION") != "1":
        pytest.skip("Set LIBVIRT_MCP_RUN_INTEGRATION=1 to run integration tests")

    test_prefix = os.getenv("LIBVIRT_MCP_TEST_PREFIX", "mcp_test_")
    prod_markers = ["prod", "production", "critical"]
    if any(marker in test_prefix.lower() for marker in prod_markers):
        pytest.skip("Unsafe test prefix indicates production-like resources")

    cfg = ServerConfig.from_env()
    cfg.allow_mutations = True
    cfg.allow_define = True
    server = LibvirtMCPServer(config=cfg)

    stamp = str(int(time.time()))
    network_name = f"{test_prefix}it_net_{stamp}"
    pool_name = f"{test_prefix}it_pool_{stamp}"
    volume_name = f"{test_prefix}it_vol_{stamp}.raw"
    domain_name = f"{test_prefix}it_domain_{stamp}"
    cfg.mutation_domain_allowlist.add(domain_name)

    bridge_name = f"virbr9{stamp[-3:]}"
    pool_dir = tempfile.mkdtemp(prefix=f"{test_prefix}pool_{stamp}_")
    upload_path = os.path.join(tempfile.gettempdir(), f"{test_prefix}upload_{stamp}.bin")
    download_path = os.path.join(tempfile.gettempdir(), f"{test_prefix}download_{stamp}.bin")
    upload_payload = b"nested-mcp-storage-transfer"

    network_xml = (
        "<network>"
        f"<name>{network_name}</name>"
        f"<bridge name='{bridge_name}' stp='on' delay='0'/>"
        "<forward mode='nat'/>"
        "<ip address='192.168.191.1' netmask='255.255.255.0'>"
        "<dhcp><range start='192.168.191.100' end='192.168.191.150'/></dhcp>"
        "</ip>"
        "</network>"
    )
    pool_xml = (
        "<pool type='dir'>"
        f"<name>{pool_name}</name>"
        "<target>"
        f"<path>{pool_dir}</path>"
        "</target>"
        "</pool>"
    )
    volume_xml = (
        "<volume>"
        f"<name>{volume_name}</name>"
        "<capacity unit='bytes'>10485760</capacity>"
        "<target><format type='raw'/></target>"
        "</volume>"
    )
    domain_xml = (
        "<domain type='kvm'>"
        f"<name>{domain_name}</name>"
        "<memory unit='MiB'>256</memory>"
        "<currentMemory unit='MiB'>256</currentMemory>"
        "<vcpu>1</vcpu>"
        "<os><type arch='x86_64' machine='q35'>hvm</type></os>"
        "<devices><emulator>/usr/bin/qemu-system-x86_64</emulator></devices>"
        "</domain>"
    )

    network_defined = False
    network_started = False
    pool_defined = False
    pool_started = False
    volume_created = False
    domain_defined = False

    try:
        defined_net = asyncio.run(server.call_tool("define_network_xml", {"network_xml": network_xml}))
        assert "error" not in defined_net
        network_defined = True

        started_net = asyncio.run(server.call_tool("start_network", {"network_name": network_name}))
        assert "error" not in started_net
        network_started = True

        defined_pool = asyncio.run(server.call_tool("define_storage_pool_xml", {"pool_xml": pool_xml}))
        assert "error" not in defined_pool
        pool_defined = True

        started_pool = asyncio.run(server.call_tool("start_storage_pool", {"pool_name": pool_name}))
        assert "error" not in started_pool
        pool_started = True

        created_vol = asyncio.run(
            server.call_tool(
                "create_storage_volume_xml",
                {"pool_name": pool_name, "volume_xml": volume_xml},
            )
        )
        assert "error" not in created_vol
        assert created_vol["volume_name"] == volume_name
        volume_created = True

        with open(upload_path, "wb") as handle:
            handle.write(upload_payload)
        uploaded = asyncio.run(
            server.call_tool(
                "upload_storage_volume",
                {"pool_name": pool_name, "volume_name": volume_name, "source_path": upload_path},
            )
        )
        assert "error" not in uploaded
        assert uploaded["bytes_transferred"] == len(upload_payload)

        downloaded = asyncio.run(
            server.call_tool(
                "download_storage_volume",
                {
                    "pool_name": pool_name,
                    "volume_name": volume_name,
                    "target_path": download_path,
                    "length": len(upload_payload),
                },
            )
        )
        assert "error" not in downloaded
        assert downloaded["bytes_transferred"] == len(upload_payload)
        with open(download_path, "rb") as handle:
            assert handle.read() == upload_payload

        defined_domain = asyncio.run(server.call_tool("define_domain_xml", {"domain_xml": domain_xml}))
        assert "error" not in defined_domain
        domain_defined = True

        updated_numa = asyncio.run(
            server.call_tool(
                "set_domain_numa_topology",
                {
                    "domain_ref": domain_name,
                    "cells": [{"cell_id": 0, "cpus": "0", "memory_kb": 262144}],
                },
            )
        )
        assert "error" not in updated_numa
        assert updated_numa["total_count"] == 1

        domain_numa = asyncio.run(server.call_tool("get_domain_numa_topology", {"domain_ref": domain_name}))
        assert "error" not in domain_numa
        assert domain_numa["numa_configured"] is True
        assert domain_numa["cells"][0]["memory_kb"] == 262144
    finally:
        for transfer_path in (upload_path, download_path):
            try:
                os.unlink(transfer_path)
            except FileNotFoundError:
                pass

        if domain_defined:
            asyncio.run(server.call_tool("undefine_domain", {"domain_ref": domain_name}))

        if volume_created:
            asyncio.run(
                server.call_tool(
                    "delete_storage_volume",
                    {"pool_name": pool_name, "volume_name": volume_name},
                )
            )

        if pool_started:
            asyncio.run(server.call_tool("destroy_storage_pool", {"pool_name": pool_name}))

        if pool_defined:
            asyncio.run(server.call_tool("undefine_storage_pool", {"pool_name": pool_name}))

        if network_started:
            asyncio.run(server.call_tool("destroy_network", {"network_name": network_name}))

        if network_defined:
            asyncio.run(server.call_tool("undefine_network", {"network_name": network_name}))


def test_parity_mutations_reject_non_test_prefix_resources():
    """Safety gate test: parity mutation tools must reject non-test-prefixed resources."""
    if os.getenv("LIBVIRT_MCP_RUN_INTEGRATION") != "1":
        pytest.skip("Set LIBVIRT_MCP_RUN_INTEGRATION=1 to run integration tests")

    test_prefix = os.getenv("LIBVIRT_MCP_TEST_PREFIX", "mcp_test_")
    prod_markers = ["prod", "production", "critical"]
    if any(marker in test_prefix.lower() for marker in prod_markers):
        pytest.skip("Unsafe test prefix indicates production-like resources")

    cfg = ServerConfig.from_env()
    cfg.allow_mutations = True
    cfg.allow_define = True
    server = LibvirtMCPServer(config=cfg)

    domain_xml = (
        "<domain type='kvm'>"
        "<name>prod_domain_guardrail</name>"
        "<memory unit='MiB'>256</memory>"
        "<currentMemory unit='MiB'>256</currentMemory>"
        "<vcpu>1</vcpu>"
        "<os><type arch='x86_64' machine='q35'>hvm</type></os>"
        "<devices><emulator>/usr/bin/qemu-system-x86_64</emulator></devices>"
        "</domain>"
    )
    network_xml = (
        "<network>"
        "<name>prod_network_guardrail</name>"
        "<bridge name='virbr250' stp='on' delay='0'/>"
        "<forward mode='nat'/>"
        "</network>"
    )
    pool_xml = (
        "<pool type='dir'>"
        "<name>prod_pool_guardrail</name>"
        "<target><path>/tmp/prod_pool_guardrail</path></target>"
        "</pool>"
    )
    volume_xml = (
        "<volume>"
        "<name>prod_volume_guardrail.qcow2</name>"
        "<capacity unit='bytes'>1048576</capacity>"
        "<target><format type='qcow2'/></target>"
        "</volume>"
    )

    checks = [
        ("define_domain_xml", {"domain_xml": domain_xml}),
        ("undefine_domain", {"domain_ref": "prod_domain_guardrail"}),
        ("define_network_xml", {"network_xml": network_xml}),
        ("start_network", {"network_name": "prod_network_guardrail"}),
        ("destroy_network", {"network_name": "prod_network_guardrail"}),
        ("undefine_network", {"network_name": "prod_network_guardrail"}),
        ("define_storage_pool_xml", {"pool_xml": pool_xml}),
        ("start_storage_pool", {"pool_name": "prod_pool_guardrail"}),
        ("destroy_storage_pool", {"pool_name": "prod_pool_guardrail"}),
        ("undefine_storage_pool", {"pool_name": "prod_pool_guardrail"}),
        (
            "create_storage_volume_xml",
            {"pool_name": "prod_pool_guardrail", "volume_xml": volume_xml},
        ),
        (
            "delete_storage_volume",
            {"pool_name": "prod_pool_guardrail", "volume_name": "prod_volume_guardrail.qcow2"},
        ),
    ]

    for tool_name, payload in checks:
        result = asyncio.run(server.call_tool(tool_name, payload))
        assert "error" in result, tool_name
        assert result["error"]["code"] == "TEST_PREFIX_REQUIRED", tool_name


def test_define_tools_blocked_when_allow_define_disabled():
    """Define operations must fail with DEFINE_DISABLED when allow_define=false."""
    if os.getenv("LIBVIRT_MCP_RUN_INTEGRATION") != "1":
        pytest.skip("Set LIBVIRT_MCP_RUN_INTEGRATION=1 to run integration tests")

    cfg = ServerConfig.from_env()
    cfg.allow_mutations = True
    cfg.allow_define = False
    cfg.test_resource_prefix = os.getenv("LIBVIRT_MCP_TEST_PREFIX", "mcp_test_")
    server = LibvirtMCPServer(config=cfg)

    prefix = cfg.test_resource_prefix
    domain_xml = (
        "<domain type='kvm'>"
        f"<name>{prefix}define_blocked_domain</name>"
        "<memory unit='MiB'>256</memory>"
        "<currentMemory unit='MiB'>256</currentMemory>"
        "<vcpu>1</vcpu>"
        "<os><type arch='x86_64' machine='q35'>hvm</type></os>"
        "<devices><emulator>/usr/bin/qemu-system-x86_64</emulator></devices>"
        "</domain>"
    )
    network_xml = (
        "<network>"
        f"<name>{prefix}define_blocked_network</name>"
        "<bridge name='virbr251' stp='on' delay='0'/>"
        "<forward mode='nat'/>"
        "</network>"
    )
    pool_xml = (
        "<pool type='dir'>"
        f"<name>{prefix}define_blocked_pool</name>"
        "<target><path>/tmp/define_blocked_pool</path></target>"
        "</pool>"
    )

    checks = [
        ("define_domain_xml", {"domain_xml": domain_xml}),
        ("define_network_xml", {"network_xml": network_xml}),
        ("define_storage_pool_xml", {"pool_xml": pool_xml}),
    ]

    for tool_name, payload in checks:
        result = asyncio.run(server.call_tool(tool_name, payload))
        assert "error" in result, tool_name
        assert result["error"]["code"] == "DEFINE_DISABLED", tool_name


def test_create_linked_clone_volume_with_relative_backing():
    """Create linked clone in libvirt storage pool using relative backing file path."""
    if os.getenv("LIBVIRT_MCP_RUN_INTEGRATION") != "1":
        pytest.skip("Set LIBVIRT_MCP_RUN_INTEGRATION=1 to run integration tests")

    test_prefix = os.getenv("LIBVIRT_MCP_TEST_PREFIX", "mcp_test_")
    prod_markers = ["prod", "production", "critical"]
    if any(marker in test_prefix.lower() for marker in prod_markers):
        pytest.skip("Unsafe test prefix indicates production-like resources")

    cfg = ServerConfig.from_env()
    cfg.allow_mutations = True
    cfg.allow_define = True
    server = LibvirtMCPServer(config=cfg)

    stamp = str(int(time.time()))
    pool_name = f"{test_prefix}it_linked_pool_{stamp}"
    parent_name = f"{test_prefix}parent_{stamp}.qcow2"
    child_name = f"{test_prefix}child_{stamp}.qcow2"
    pool_dir = tempfile.mkdtemp(prefix=f"{test_prefix}linked_pool_{stamp}_")

    pool_xml = (
        "<pool type='dir'>"
        f"<name>{pool_name}</name>"
        "<target>"
        f"<path>{pool_dir}</path>"
        "</target>"
        "</pool>"
    )
    parent_xml = (
        "<volume>"
        f"<name>{parent_name}</name>"
        "<capacity unit='bytes'>20971520</capacity>"
        "<target><format type='qcow2'/></target>"
        "</volume>"
    )

    pool_defined = False
    pool_started = False
    parent_created = False
    child_created = False

    try:
        defined_pool = asyncio.run(server.call_tool("define_storage_pool_xml", {"pool_xml": pool_xml}))
        assert "error" not in defined_pool
        pool_defined = True

        started_pool = asyncio.run(server.call_tool("start_storage_pool", {"pool_name": pool_name}))
        assert "error" not in started_pool
        pool_started = True

        created_parent = asyncio.run(
            server.call_tool(
                "create_storage_volume_xml",
                {"pool_name": pool_name, "volume_xml": parent_xml},
            )
        )
        assert "error" not in created_parent
        assert created_parent["volume_name"] == parent_name
        parent_created = True

        created_child = asyncio.run(
            server.call_tool(
                "create_linked_clone_volume",
                {
                    "pool_name": pool_name,
                    "volume_name": child_name,
                    "backing_file": parent_name,
                    "relative_backing": True,
                    "capacity_bytes": 107374182400,
                },
            )
        )
        assert "error" not in created_child
        assert created_child["volume_name"] == child_name
        assert created_child["backing_file"] == parent_name
        child_created = True

        got_child = asyncio.run(
            server.call_tool(
                "get_storage_volume",
                {"pool_name": pool_name, "volume_name": child_name},
            )
        )
        assert "error" not in got_child
        assert got_child["name"] == child_name
    finally:
        if child_created:
            asyncio.run(
                server.call_tool(
                    "delete_storage_volume",
                    {"pool_name": pool_name, "volume_name": child_name},
                )
            )

        if parent_created:
            asyncio.run(
                server.call_tool(
                    "delete_storage_volume",
                    {"pool_name": pool_name, "volume_name": parent_name},
                )
            )

        if pool_started:
            asyncio.run(server.call_tool("destroy_storage_pool", {"pool_name": pool_name}))

        if pool_defined:
            asyncio.run(server.call_tool("undefine_storage_pool", {"pool_name": pool_name}))
