"""Unit tests for domain stats, CPU pinning, storage resize/wipe/build tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.errors import MCPError
from libvirt_mcp_server.tools import domain_tools, storage_tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(*, allow_mutations: bool = False) -> ServerConfig:
    cfg = MagicMock(spec=ServerConfig)
    cfg.allow_mutations = allow_mutations
    cfg.mutation_domain_allowlist = set()
    cfg.allow_destructive = False
    cfg.destructive_domain_allowlist = set()
    cfg.test_resource_prefix = "mcp_test_"
    cfg.get_hypervisor_uri = MagicMock(return_value="qemu:///system")
    return cfg


# ---------------------------------------------------------------------------
# get_domain_stats
# ---------------------------------------------------------------------------


def test_get_domain_stats_returns_all_keys():
    adapter = MagicMock()
    adapter.get_domain_stats.return_value = {
        "source": "libvirt",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "domain_ref": "vm1",
        "block_stats": {"rd_requests": 10},
        "interface_stats": {"rx_bytes": 100},
        "memory_stats": {"5": 1024},
        "cpu_stats": {"cpu_time": 9000},
    }
    result = domain_tools.get_domain_stats(_config(), adapter, domain_ref="vm1", hypervisor_ref=None)
    assert "block_stats" in result
    assert "interface_stats" in result
    assert "memory_stats" in result
    assert "cpu_stats" in result
    assert result["hypervisor_ref"] == "default"


# ---------------------------------------------------------------------------
# get_domain_block_stats
# ---------------------------------------------------------------------------


def test_get_domain_block_stats_snake_case_mapping():
    adapter = MagicMock()
    adapter.get_domain_block_stats.return_value = {
        "source": "libvirt",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "domain_ref": "vm1",
        "disk": "vda",
        "rd_requests": 5,
        "rd_bytes": 1024,
        "wr_requests": 3,
        "wr_bytes": 512,
        "errors": 0,
    }
    result = domain_tools.get_domain_block_stats(
        _config(), adapter, domain_ref="vm1", disk="vda", hypervisor_ref="hv1"
    )
    assert result["rd_requests"] == 5
    assert result["wr_bytes"] == 512
    assert result["disk"] == "vda"
    assert result["hypervisor_ref"] == "hv1"
    adapter.get_domain_block_stats.assert_called_once_with("qemu:///system", "vm1", "vda")


# ---------------------------------------------------------------------------
# get_domain_interface_stats
# ---------------------------------------------------------------------------


def test_get_domain_interface_stats_all_fields():
    adapter = MagicMock()
    adapter.get_domain_interface_stats.return_value = {
        "source": "libvirt",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "domain_ref": "vm1",
        "interface": "vnet0",
        "rx_bytes": 100,
        "rx_packets": 10,
        "rx_errors": 0,
        "rx_drop": 0,
        "tx_bytes": 200,
        "tx_packets": 20,
        "tx_errors": 0,
        "tx_drop": 0,
    }
    result = domain_tools.get_domain_interface_stats(
        _config(), adapter, domain_ref="vm1", interface="vnet0", hypervisor_ref=None
    )
    for field in ("rx_bytes", "rx_packets", "rx_errors", "rx_drop", "tx_bytes", "tx_packets", "tx_errors", "tx_drop"):
        assert field in result, f"Missing field: {field}"
    assert result["interface"] == "vnet0"


# ---------------------------------------------------------------------------
# get_domain_memory_stats
# ---------------------------------------------------------------------------


def test_get_domain_memory_stats_str_cast_keys():
    adapter = MagicMock()
    adapter.get_domain_memory_stats.return_value = {
        "source": "libvirt",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "domain_ref": "vm1",
        "stats": {"5": 1024, "6": 512},
    }
    result = domain_tools.get_domain_memory_stats(_config(), adapter, domain_ref="vm1", hypervisor_ref=None)
    assert "stats" in result
    stats = result["stats"]
    assert "5" in stats
    assert "6" in stats


# ---------------------------------------------------------------------------
# get_domain_vcpu_pin_info (read-only, call-through)
# ---------------------------------------------------------------------------


def test_get_domain_vcpu_pin_info_call_through():
    adapter = MagicMock()
    adapter.get_domain_vcpu_pin_info.return_value = {
        "source": "libvirt",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "domain_ref": "vm1",
        "vcpu_count": 4,
        "pinmaps": ["ff", "ff", "ff", "ff"],
    }
    result = domain_tools.get_domain_vcpu_pin_info(_config(), adapter, domain_ref="vm1", hypervisor_ref=None)
    adapter.get_domain_vcpu_pin_info.assert_called_once_with("qemu:///system", "vm1")
    assert result["vcpu_count"] == 4


# ---------------------------------------------------------------------------
# set_domain_vcpu_pin — mutations disabled
# ---------------------------------------------------------------------------


def test_set_domain_vcpu_pin_mutations_disabled():
    adapter = MagicMock()
    cfg = _config(allow_mutations=False)
    with pytest.raises(MCPError) as exc:
        domain_tools.set_domain_vcpu_pin(
            cfg, adapter, domain_ref="vm1", vcpu=0, cpumap=[1, 0, 0, 0], hypervisor_ref=None
        )
    assert exc.value.code == "MUTATION_DISABLED"


# ---------------------------------------------------------------------------
# set_domain_emulator_pin — mutations disabled
# ---------------------------------------------------------------------------


def test_set_domain_emulator_pin_mutations_disabled():
    adapter = MagicMock()
    cfg = _config(allow_mutations=False)
    with pytest.raises(MCPError) as exc:
        domain_tools.set_domain_emulator_pin(
            cfg, adapter, domain_ref="vm1", cpumap=[1, 0, 0, 0], hypervisor_ref=None
        )
    assert exc.value.code == "MUTATION_DISABLED"


# ---------------------------------------------------------------------------
# resize_storage_volume — mutations disabled and test_prefix check
# ---------------------------------------------------------------------------


def test_resize_storage_volume_mutations_disabled():
    adapter = MagicMock()
    cfg = _config(allow_mutations=False)
    with pytest.raises(MCPError) as exc:
        storage_tools.resize_storage_volume(
            cfg, adapter, pool_name="mcp_test_pool", volume_name="mcp_test_vol", capacity_bytes=1073741824, hypervisor_ref=None
        )
    assert exc.value.code == "MUTATION_DISABLED"


def test_resize_storage_volume_test_prefix_required():
    adapter = MagicMock()
    cfg = _config(allow_mutations=True)
    with pytest.raises(MCPError) as exc:
        storage_tools.resize_storage_volume(
            cfg, adapter, pool_name="mcp_test_pool", volume_name="prod_vol", capacity_bytes=1073741824, hypervisor_ref=None
        )
    assert exc.value.code == "TEST_PREFIX_REQUIRED"


# ---------------------------------------------------------------------------
# wipe_storage_volume — same guards
# ---------------------------------------------------------------------------


def test_wipe_storage_volume_mutations_disabled():
    adapter = MagicMock()
    cfg = _config(allow_mutations=False)
    with pytest.raises(MCPError) as exc:
        storage_tools.wipe_storage_volume(
            cfg, adapter, pool_name="mcp_test_pool", volume_name="mcp_test_vol", hypervisor_ref=None
        )
    assert exc.value.code == "MUTATION_DISABLED"


def test_wipe_storage_volume_test_prefix_required():
    adapter = MagicMock()
    cfg = _config(allow_mutations=True)
    with pytest.raises(MCPError) as exc:
        storage_tools.wipe_storage_volume(
            cfg, adapter, pool_name="mcp_test_pool", volume_name="prod_vol", hypervisor_ref=None
        )
    assert exc.value.code == "TEST_PREFIX_REQUIRED"


# ---------------------------------------------------------------------------
# build_storage_pool — mutations disabled
# ---------------------------------------------------------------------------


def test_build_storage_pool_mutations_disabled():
    adapter = MagicMock()
    cfg = _config(allow_mutations=False)
    with pytest.raises(MCPError) as exc:
        storage_tools.build_storage_pool(
            cfg, adapter, pool_name="mcp_test_pool", hypervisor_ref=None
        )
    assert exc.value.code == "MUTATION_DISABLED"


def test_build_storage_pool_test_prefix_required():
    adapter = MagicMock()
    cfg = _config(allow_mutations=True)
    with pytest.raises(MCPError) as exc:
        storage_tools.build_storage_pool(
            cfg, adapter, pool_name="prod_pool", hypervisor_ref=None
        )
    assert exc.value.code == "TEST_PREFIX_REQUIRED"
