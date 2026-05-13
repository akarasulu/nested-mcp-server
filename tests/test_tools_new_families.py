"""Unit tests for all new tool families added in the extended API implementation."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.errors import MCPError
from libvirt_mcp_server.tools import (
    network_tools,
    storage_tools,
    host_tools,
    domain_tools,
)
from libvirt_mcp_server.tools import node_device_tools, block_job_tools, checkpoint_tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg_readonly():
    cfg = ServerConfig.from_env()
    cfg.allow_mutations = False
    cfg.allow_define = False
    cfg.test_resource_prefix = "mcp_test_"
    return cfg


@pytest.fixture
def cfg_mutations():
    cfg = ServerConfig.from_env()
    cfg.allow_mutations = True
    cfg.allow_define = True
    cfg.test_resource_prefix = "mcp_test_"
    return cfg


def _make_adapter(**methods):
    adapter = MagicMock()
    for name, retval in methods.items():
        getattr(adapter, name).return_value = retval
    return adapter


# ---------------------------------------------------------------------------
# Area 1: Node devices
# ---------------------------------------------------------------------------


def test_list_node_devices_readonly(cfg_readonly):
    adapter = _make_adapter(list_node_devices=[{"source": "libvirt", "name": "pci_0000_00_01_0", "xml_summary": {}}])
    result = node_device_tools.list_node_devices(cfg_readonly, adapter)
    assert result["total_count"] == 1
    adapter.list_node_devices.assert_called_once()


def test_get_node_device_readonly(cfg_readonly):
    adapter = _make_adapter(get_node_device={"source": "libvirt", "timestamp": "t", "device_name": "dev0", "xml": "<device/>", "xml_summary": {}})
    result = node_device_tools.get_node_device(cfg_readonly, adapter, device_name="dev0")
    assert result["device_name"] == "dev0"
    adapter.get_node_device.assert_called_once_with(cfg_readonly.get_hypervisor_uri(None), "dev0")


def test_detach_node_device_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        node_device_tools.detach_node_device(cfg_readonly, adapter, device_name="pci_0000_00_01_0")
    assert exc.value.code == "MUTATION_DISABLED"
    adapter.detach_node_device.assert_not_called()


def test_detach_node_device_allowed(cfg_mutations):
    adapter = _make_adapter(detach_node_device={"source": "libvirt", "timestamp": "t", "device_name": "pci_0000_00_01_0", "status": "detached"})
    result = node_device_tools.detach_node_device(cfg_mutations, adapter, device_name="pci_0000_00_01_0")
    assert result["status"] == "detached"
    adapter.detach_node_device.assert_called_once()


def test_reattach_node_device_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        node_device_tools.reattach_node_device(cfg_readonly, adapter, device_name="pci_0000_00_01_0")
    assert exc.value.code == "MUTATION_DISABLED"


def test_reattach_node_device_allowed(cfg_mutations):
    adapter = _make_adapter(reattach_node_device={"source": "libvirt", "timestamp": "t", "device_name": "pci_0000_00_01_0", "status": "reattached"})
    result = node_device_tools.reattach_node_device(cfg_mutations, adapter, device_name="pci_0000_00_01_0")
    assert result["status"] == "reattached"


# ---------------------------------------------------------------------------
# Area 2: Host network interfaces
# ---------------------------------------------------------------------------


def test_list_interfaces_readonly(cfg_readonly):
    adapter = _make_adapter(list_interfaces=[{"source": "libvirt", "name": "eth0", "mac": "aa:bb:cc:dd:ee:ff", "is_active": True}])
    result = network_tools.list_interfaces(cfg_readonly, adapter)
    assert result["total_count"] == 1


def test_get_interface_readonly(cfg_readonly):
    adapter = _make_adapter(get_interface={"source": "libvirt", "timestamp": "t", "name": "eth0", "mac": None, "is_active": True, "xml": "<interface/>"})
    result = network_tools.get_interface(cfg_readonly, adapter, iface_name="eth0")
    assert result["name"] == "eth0"
    adapter.get_interface.assert_called_once()


def test_define_interface_xml_blocked_when_define_off(cfg_readonly):
    adapter = MagicMock()
    xml = "<interface type='bridge'><name>mcp_test_br0</name></interface>"
    with pytest.raises(MCPError) as exc:
        network_tools.define_interface_xml(cfg_readonly, adapter, interface_xml=xml)
    assert exc.value.code == "DEFINE_DISABLED"
    adapter.define_interface_xml.assert_not_called()


def test_define_interface_xml_requires_test_prefix(cfg_mutations):
    adapter = MagicMock()
    xml = "<interface type='bridge'><name>prod_br0</name></interface>"
    with pytest.raises(MCPError) as exc:
        network_tools.define_interface_xml(cfg_mutations, adapter, interface_xml=xml)
    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_define_interface_xml_allowed(cfg_mutations):
    adapter = _make_adapter(define_interface_xml={"source": "libvirt", "timestamp": "t", "iface_name": "mcp_test_br0", "status": "defined"})
    xml = "<interface type='bridge'><name>mcp_test_br0</name></interface>"
    result = network_tools.define_interface_xml(cfg_mutations, adapter, interface_xml=xml)
    assert result["status"] == "defined"


def test_start_interface_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        network_tools.start_interface(cfg_readonly, adapter, iface_name="mcp_test_br0")
    assert exc.value.code == "MUTATION_DISABLED"


def test_start_interface_requires_test_prefix(cfg_mutations):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        network_tools.start_interface(cfg_mutations, adapter, iface_name="eth0")
    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_stop_interface_requires_test_prefix(cfg_mutations):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        network_tools.stop_interface(cfg_mutations, adapter, iface_name="eth0")
    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_undefine_interface_requires_test_prefix(cfg_mutations):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        network_tools.undefine_interface(cfg_mutations, adapter, iface_name="eth0")
    assert exc.value.code == "TEST_PREFIX_REQUIRED"


# ---------------------------------------------------------------------------
# Area 3: Network filters
# ---------------------------------------------------------------------------


def test_list_nwfilters_readonly(cfg_readonly):
    adapter = _make_adapter(list_nwfilters=[{"source": "libvirt", "name": "clean-traffic", "uuid": "abc"}])
    result = network_tools.list_nwfilters(cfg_readonly, adapter)
    assert result["total_count"] == 1


def test_get_nwfilter_readonly(cfg_readonly):
    adapter = _make_adapter(get_nwfilter={"source": "libvirt", "timestamp": "t", "name": "clean-traffic", "uuid": "abc", "xml": "<filter/>"})
    result = network_tools.get_nwfilter(cfg_readonly, adapter, filter_name="clean-traffic")
    assert result["name"] == "clean-traffic"


def test_define_nwfilter_xml_blocked_when_define_off(cfg_readonly):
    adapter = MagicMock()
    xml = "<filter name='mcp_test_filter'></filter>"
    with pytest.raises(MCPError) as exc:
        network_tools.define_nwfilter_xml(cfg_readonly, adapter, filter_xml=xml)
    assert exc.value.code == "DEFINE_DISABLED"


def test_define_nwfilter_xml_requires_test_prefix(cfg_mutations):
    adapter = MagicMock()
    xml = "<filter name='prod-filter'></filter>"
    with pytest.raises(MCPError) as exc:
        network_tools.define_nwfilter_xml(cfg_mutations, adapter, filter_xml=xml)
    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_undefine_nwfilter_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        network_tools.undefine_nwfilter(cfg_readonly, adapter, filter_name="mcp_test_filter")
    assert exc.value.code == "MUTATION_DISABLED"


def test_undefine_nwfilter_requires_test_prefix(cfg_mutations):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        network_tools.undefine_nwfilter(cfg_mutations, adapter, filter_name="prod-filter")
    assert exc.value.code == "TEST_PREFIX_REQUIRED"


# ---------------------------------------------------------------------------
# Area 4: Network DHCP leases
# ---------------------------------------------------------------------------


def test_get_network_dhcp_leases_readonly(cfg_readonly):
    leases = [{"iface": "virbr0", "ipaddr": "192.168.122.10", "mac": "aa:bb:cc:dd:ee:ff"}]
    adapter = _make_adapter(get_network_dhcp_leases=leases)
    result = network_tools.get_network_dhcp_leases(cfg_readonly, adapter, network_name="default")
    assert result["total_count"] == 1
    assert result["network_name"] == "default"
    adapter.get_network_dhcp_leases.assert_called_once()


# ---------------------------------------------------------------------------
# Area 5: Network autostart
# ---------------------------------------------------------------------------


def test_set_network_autostart_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        network_tools.set_network_autostart(cfg_readonly, adapter, network_name="mcp_test_net", autostart=True)
    assert exc.value.code == "MUTATION_DISABLED"


def test_set_network_autostart_requires_test_prefix(cfg_mutations):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        network_tools.set_network_autostart(cfg_mutations, adapter, network_name="default", autostart=True)
    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_set_network_autostart_allowed(cfg_mutations):
    adapter = _make_adapter(set_network_autostart={"source": "libvirt", "timestamp": "t", "network_name": "mcp_test_net", "autostart": True})
    result = network_tools.set_network_autostart(cfg_mutations, adapter, network_name="mcp_test_net", autostart=True)
    assert result["autostart"] is True
    adapter.set_network_autostart.assert_called_once()


# ---------------------------------------------------------------------------
# Area 6: Block jobs
# ---------------------------------------------------------------------------


def test_block_pull_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        block_job_tools.block_pull(cfg_readonly, adapter, domain_ref="vm1", disk="vda")
    assert exc.value.code == "MUTATION_DISABLED"
    adapter.block_pull.assert_not_called()


def test_block_pull_allowed(cfg_mutations):
    adapter = _make_adapter(block_pull={"source": "libvirt", "timestamp": "t", "domain_ref": "vm1", "disk": "vda", "status": "pull_started"})
    result = block_job_tools.block_pull(cfg_mutations, adapter, domain_ref="vm1", disk="vda")
    assert result["status"] == "pull_started"
    adapter.block_pull.assert_called_once_with(cfg_mutations.get_hypervisor_uri(None), "vm1", "vda", 0)


def test_block_commit_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        block_job_tools.block_commit(cfg_readonly, adapter, domain_ref="vm1", disk="vda")
    assert exc.value.code == "MUTATION_DISABLED"


def test_block_job_abort_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        block_job_tools.block_job_abort(cfg_readonly, adapter, domain_ref="vm1", disk="vda")
    assert exc.value.code == "MUTATION_DISABLED"


def test_block_job_info_readonly(cfg_readonly):
    adapter = _make_adapter(block_job_info={"source": "libvirt", "timestamp": "t", "domain_ref": "vm1", "disk": "vda", "status": "no_job"})
    result = block_job_tools.block_job_info(cfg_readonly, adapter, domain_ref="vm1", disk="vda")
    assert result["status"] == "no_job"
    adapter.block_job_info.assert_called_once()


def test_block_pull_domain_mutation_allowlist(cfg_mutations):
    cfg_mutations.mutation_domain_allowlist = {"allowed-vm"}
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        block_job_tools.block_pull(cfg_mutations, adapter, domain_ref="other-vm", disk="vda")
    assert exc.value.code == "MUTATION_DOMAIN_DENIED"


# ---------------------------------------------------------------------------
# Area 7: Checkpoints
# ---------------------------------------------------------------------------


def test_list_domain_checkpoints_readonly(cfg_readonly):
    adapter = _make_adapter(list_domain_checkpoints=[{"source": "libvirt", "name": "cp1", "xml": "<checkpoint/>"}])
    result = checkpoint_tools.list_domain_checkpoints(cfg_readonly, adapter, domain_ref="vm1")
    assert result["total_count"] == 1
    assert result["domain_ref"] == "vm1"


def test_create_domain_checkpoint_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        checkpoint_tools.create_domain_checkpoint(cfg_readonly, adapter, domain_ref="vm1", checkpoint_xml="<domaincheckpoint/>")
    assert exc.value.code == "MUTATION_DISABLED"
    adapter.create_domain_checkpoint.assert_not_called()


def test_create_domain_checkpoint_allowed(cfg_mutations):
    adapter = _make_adapter(create_domain_checkpoint={"source": "libvirt", "timestamp": "t", "domain_ref": "vm1", "checkpoint_name": "cp1", "status": "created"})
    result = checkpoint_tools.create_domain_checkpoint(cfg_mutations, adapter, domain_ref="vm1", checkpoint_xml="<domaincheckpoint/>")
    assert result["status"] == "created"
    adapter.create_domain_checkpoint.assert_called_once()


def test_delete_domain_checkpoint_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        checkpoint_tools.delete_domain_checkpoint(cfg_readonly, adapter, domain_ref="vm1", checkpoint_name="cp1")
    assert exc.value.code == "MUTATION_DISABLED"


def test_delete_domain_checkpoint_domain_allowlist(cfg_mutations):
    cfg_mutations.mutation_domain_allowlist = {"allowed-vm"}
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        checkpoint_tools.delete_domain_checkpoint(cfg_mutations, adapter, domain_ref="other-vm", checkpoint_name="cp1")
    assert exc.value.code == "MUTATION_DOMAIN_DENIED"


# ---------------------------------------------------------------------------
# Area 8: Storage volume clone
# ---------------------------------------------------------------------------


def test_clone_storage_volume_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        storage_tools.clone_storage_volume(
            cfg_readonly, adapter,
            pool_name="mcp_test_pool", volume_name="mcp_test_vol",
            src_pool_name="default", src_volume_name="base.qcow2",
            volume_xml="<volume/>",
        )
    assert exc.value.code == "MUTATION_DISABLED"


def test_clone_storage_volume_requires_test_prefix(cfg_mutations):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        storage_tools.clone_storage_volume(
            cfg_mutations, adapter,
            pool_name="default", volume_name="prod-vol",
            src_pool_name="default", src_volume_name="base.qcow2",
            volume_xml="<volume/>",
        )
    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_clone_storage_volume_allowed(cfg_mutations):
    adapter = _make_adapter(
        clone_storage_volume={
            "source": "libvirt", "timestamp": "t",
            "pool_name": "mcp_test_pool", "volume_name": "mcp_test_vol",
            "src_pool_name": "default", "src_volume_name": "base.qcow2",
            "status": "cloned",
        }
    )
    result = storage_tools.clone_storage_volume(
        cfg_mutations, adapter,
        pool_name="mcp_test_pool", volume_name="mcp_test_vol",
        src_pool_name="default", src_volume_name="base.qcow2",
        volume_xml="<volume/>",
    )
    assert result["status"] == "cloned"
    adapter.clone_storage_volume.assert_called_once()


# ---------------------------------------------------------------------------
# Area 9: Storage pool autostart and refresh
# ---------------------------------------------------------------------------


def test_set_storage_pool_autostart_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        storage_tools.set_storage_pool_autostart(cfg_readonly, adapter, pool_name="mcp_test_pool", autostart=True)
    assert exc.value.code == "MUTATION_DISABLED"


def test_set_storage_pool_autostart_requires_test_prefix(cfg_mutations):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        storage_tools.set_storage_pool_autostart(cfg_mutations, adapter, pool_name="prod_pool", autostart=True)
    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_set_storage_pool_autostart_allowed(cfg_mutations):
    adapter = _make_adapter(set_storage_pool_autostart={"source": "libvirt", "timestamp": "t", "pool_name": "mcp_test_pool", "autostart": True})
    result = storage_tools.set_storage_pool_autostart(cfg_mutations, adapter, pool_name="mcp_test_pool", autostart=True)
    assert result["autostart"] is True
    adapter.set_storage_pool_autostart.assert_called_once()


def test_refresh_storage_pool_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        storage_tools.refresh_storage_pool(cfg_readonly, adapter, pool_name="mcp_test_pool")
    assert exc.value.code == "MUTATION_DISABLED"


def test_refresh_storage_pool_allowed(cfg_mutations):
    adapter = _make_adapter(refresh_storage_pool={"source": "libvirt", "timestamp": "t", "pool_name": "mcp_test_pool", "status": "refreshed"})
    result = storage_tools.refresh_storage_pool(cfg_mutations, adapter, pool_name="mcp_test_pool")
    assert result["status"] == "refreshed"
    adapter.refresh_storage_pool.assert_called_once()


# ---------------------------------------------------------------------------
# Area 10: Domain capabilities
# ---------------------------------------------------------------------------


def test_get_domain_capabilities_readonly(cfg_readonly):
    adapter = _make_adapter(
        get_domain_capabilities={
            "source": "libvirt", "timestamp": "t",
            "xml": "<domainCapabilities/>", "summary": {"arch": "x86_64", "machine": "pc", "domain": "kvm"},
        }
    )
    result = host_tools.get_domain_capabilities(cfg_readonly, adapter)
    assert result["summary"]["arch"] == "x86_64"
    adapter.get_domain_capabilities.assert_called_once()


def test_get_domain_capabilities_with_params(cfg_readonly):
    adapter = _make_adapter(
        get_domain_capabilities={
            "source": "libvirt", "timestamp": "t",
            "xml": "<domainCapabilities/>", "summary": {},
        }
    )
    host_tools.get_domain_capabilities(cfg_readonly, adapter, arch="aarch64", machine="virt")
    adapter.get_domain_capabilities.assert_called_once_with(
        cfg_readonly.get_hypervisor_uri(None),
        emulatorbin=None,
        arch="aarch64",
        machine="virt",
        virttype=None,
    )


def test_get_host_numa_topology_readonly(cfg_readonly):
    adapter = _make_adapter(
        get_host_numa_topology={
            "source": "libvirt",
            "timestamp": "t",
            "cells": [{"cell_id": 0, "memory_kb": 1024, "cpus": [], "cpu_count": 0}],
            "total_count": 1,
            "numa_supported": True,
        }
    )
    result = host_tools.get_host_numa_topology(cfg_readonly, adapter)
    assert result["numa_supported"] is True
    assert result["hypervisor_ref"] == "default"
    adapter.get_host_numa_topology.assert_called_once_with(cfg_readonly.get_hypervisor_uri(None))


# ---------------------------------------------------------------------------
# Area 11: Domain vCPU and memory tuning
# ---------------------------------------------------------------------------


def test_set_domain_vcpus_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        domain_tools.set_domain_vcpus(cfg_readonly, adapter, domain_ref="vm1", vcpu_count=2)
    assert exc.value.code == "MUTATION_DISABLED"
    adapter.set_vcpus.assert_not_called()


def test_set_domain_vcpus_allowed(cfg_mutations):
    adapter = _make_adapter(set_vcpus={"source": "libvirt", "timestamp": "t", "domain_ref": "vm1", "vcpu_count": 4, "status": "applied"})
    result = domain_tools.set_domain_vcpus(cfg_mutations, adapter, domain_ref="vm1", vcpu_count=4)
    assert result["vcpu_count"] == 4
    assert result["live"] is True
    assert result["persistent"] is True
    # flags: live(1) | config(2) = 3
    adapter.set_vcpus.assert_called_once_with(cfg_mutations.get_hypervisor_uri(None), "vm1", 4, 3)


def test_set_domain_vcpus_live_only(cfg_mutations):
    adapter = _make_adapter(set_vcpus={"source": "libvirt", "timestamp": "t", "domain_ref": "vm1", "vcpu_count": 2, "status": "applied"})
    domain_tools.set_domain_vcpus(cfg_mutations, adapter, domain_ref="vm1", vcpu_count=2, live=True, persistent=False)
    # flags: live(1) only
    adapter.set_vcpus.assert_called_once_with(cfg_mutations.get_hypervisor_uri(None), "vm1", 2, 1)


def test_set_domain_vcpus_domain_allowlist(cfg_mutations):
    cfg_mutations.mutation_domain_allowlist = {"allowed-vm"}
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        domain_tools.set_domain_vcpus(cfg_mutations, adapter, domain_ref="other-vm", vcpu_count=2)
    assert exc.value.code == "MUTATION_DOMAIN_DENIED"


def test_set_domain_memory_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        domain_tools.set_domain_memory(cfg_readonly, adapter, domain_ref="vm1", memory_kb=2097152)
    assert exc.value.code == "MUTATION_DISABLED"
    adapter.set_memory.assert_not_called()


def test_set_domain_memory_allowed(cfg_mutations):
    adapter = _make_adapter(set_memory={"source": "libvirt", "timestamp": "t", "domain_ref": "vm1", "memory_kb": 2097152, "status": "applied"})
    result = domain_tools.set_domain_memory(cfg_mutations, adapter, domain_ref="vm1", memory_kb=2097152)
    assert result["memory_kb"] == 2097152
    # flags: live(1) | config(2) = 3
    adapter.set_memory.assert_called_once_with(cfg_mutations.get_hypervisor_uri(None), "vm1", 2097152, 3)


def test_set_domain_memory_persistent_only(cfg_mutations):
    adapter = _make_adapter(set_memory={"source": "libvirt", "timestamp": "t", "domain_ref": "vm1", "memory_kb": 1048576, "status": "applied"})
    domain_tools.set_domain_memory(cfg_mutations, adapter, domain_ref="vm1", memory_kb=1048576, live=False, persistent=True)
    # flags: config(2) only
    adapter.set_memory.assert_called_once_with(cfg_mutations.get_hypervisor_uri(None), "vm1", 1048576, 2)


def test_get_domain_numa_topology_readonly(cfg_readonly):
    adapter = _make_adapter(
        get_domain_numa_topology={
            "source": "libvirt",
            "timestamp": "t",
            "domain_ref": "vm1",
            "numa_configured": True,
            "cells": [{"cell_id": 0, "cpus": "0-1", "memory_kb": 1048576}],
            "total_count": 1,
        }
    )
    result = domain_tools.get_domain_numa_topology(cfg_readonly, adapter, domain_ref="vm1")
    assert result["numa_configured"] is True
    assert result["hypervisor_ref"] == "default"
    adapter.get_domain_numa_topology.assert_called_once_with(cfg_readonly.get_hypervisor_uri(None), "vm1")


def test_set_domain_numa_topology_blocked_when_mutations_off(cfg_readonly):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        domain_tools.set_domain_numa_topology(
            cfg_readonly,
            adapter,
            domain_ref="mcp_test_vm1",
            cells=[{"cell_id": 0, "cpus": "0", "memory_kb": 1048576}],
        )
    assert exc.value.code == "MUTATION_DISABLED"
    adapter.set_domain_numa_topology.assert_not_called()


def test_set_domain_numa_topology_requires_test_prefix(cfg_mutations):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        domain_tools.set_domain_numa_topology(
            cfg_mutations,
            adapter,
            domain_ref="prod_vm1",
            cells=[{"cell_id": 0, "cpus": "0", "memory_kb": 1048576}],
        )
    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_set_domain_numa_topology_rejects_live_update(cfg_mutations):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        domain_tools.set_domain_numa_topology(
            cfg_mutations,
            adapter,
            domain_ref="mcp_test_vm1",
            cells=[{"cell_id": 0, "cpus": "0", "memory_kb": 1048576}],
            live=True,
        )
    assert exc.value.code == "NUMA_LIVE_UPDATE_UNSUPPORTED"


def test_set_domain_numa_topology_allowed(cfg_mutations):
    adapter = _make_adapter(
        set_domain_numa_topology={
            "source": "libvirt",
            "timestamp": "t",
            "domain_ref": "mcp_test_vm1",
            "status": "numa_topology_updated",
            "cells": [{"cell_id": 0, "cpus": "0", "memory_kb": 1048576}],
            "total_count": 1,
        }
    )
    result = domain_tools.set_domain_numa_topology(
        cfg_mutations,
        adapter,
        domain_ref="mcp_test_vm1",
        cells=[{"cell_id": 0, "cpus": "0", "memory_kb": 1048576}],
    )
    assert result["status"] == "numa_topology_updated"
    assert result["persistent"] is True
    adapter.set_domain_numa_topology.assert_called_once()
