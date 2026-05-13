"""Host and discovery tools."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.adapters.libvirt_adapter import LibvirtAdapter


def host_info(config: ServerConfig, libvirt_adapter: LibvirtAdapter, hypervisor_ref: str | None = None) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.host_info(uri)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    payload["policy"] = config.to_policy_dict()
    return payload


def list_hypervisors(config: ServerConfig) -> dict[str, Any]:
    items = [
        {
            "hypervisor_ref": ref,
            "uri": uri,
            "transport": "ssh" if "+ssh://" in uri else "local",
            "is_session": uri.endswith("/session"),
            "is_default": ref == "default",
        }
        for ref, uri in config.hypervisors.items()
    ]
    return {
        "source": "libvirt",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "items": items,
        "total_count": len(items),
    }


def get_hypervisor(config: ServerConfig, hypervisor_ref: str) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    return {
        "source": "libvirt",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref,
        "uri": uri,
        "transport": "ssh" if "+ssh://" in uri else "local",
        "is_session": uri.endswith("/session"),
    }


def get_domain_capabilities(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    emulatorbin: str | None = None,
    arch: str | None = None,
    machine: str | None = None,
    virttype: str | None = None,
    hypervisor_ref: str | None = None,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_domain_capabilities(uri, emulatorbin=emulatorbin, arch=arch, machine=machine, virttype=virttype)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def get_host_numa_topology(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    hypervisor_ref: str | None = None,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_host_numa_topology(uri)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def get_audit_log(
    config: ServerConfig,
    audit_log_path: str,
    *,
    limit: int = 100,
    tool_name: str | None = None,
    result_filter: str | None = None,
    since: str | None = None,
) -> dict:
    import json
    from pathlib import Path
    path = Path(audit_log_path)
    entries: list = []
    if path.exists():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if tool_name and entry.get("tool_name") != tool_name:
                    continue
                if result_filter and entry.get("result") != result_filter:
                    continue
                if since and entry.get("timestamp", "") < since:
                    continue
                entries.append(entry)
                if len(entries) >= limit:
                    break
        except Exception as exc:
            return {
                "source": "server",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
                "items": [],
                "total_count": 0,
            }
    return {
        "source": "server",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "items": entries,
        "total_count": len(entries),
        "filters": {
            "tool_name": tool_name,
            "result": result_filter,
            "since": since,
            "limit": limit,
        },
    }


def get_qmp_policy(config: ServerConfig) -> dict:
    return {
        "source": "server",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "qmp_enabled": config.allow_qmp,
        "allow_mutations": config.allow_mutations,
        "read_allowlist": sorted(config.qmp_allowlist),
        "mutation_allowlist": sorted(config.qmp_mutation_allowlist),
        "effective_allowlist": sorted(
            config.qmp_allowlist | (config.qmp_mutation_allowlist if config.allow_mutations else set())
        ),
    }


def get_policy_scopes(config: ServerConfig) -> dict:
    scopes = [
        {
            "scope": "read_only",
            "enabled": True,
            "families": ["host", "domain_inspect", "network_inspect", "storage_inspect", "qmp_query"],
            "policy_gate": None,
        },
        {
            "scope": "mutation",
            "enabled": config.allow_mutations,
            "families": ["domain_lifecycle", "network_lifecycle", "storage_lifecycle", "block_jobs", "qmp_runtime_controls"],
            "policy_gate": "allow_mutations",
        },
        {
            "scope": "define",
            "enabled": config.allow_define,
            "families": ["domain_define", "network_define", "storage_pool_define", "interface_define", "nwfilter_define"],
            "policy_gate": "allow_define",
        },
        {
            "scope": "destructive",
            "enabled": config.allow_destructive,
            "families": ["domain_destroy", "snapshot_delete", "storage_volume_delete", "secret_undefine"],
            "policy_gate": "allow_destructive",
        },
        {
            "scope": "qmp",
            "enabled": config.allow_qmp,
            "families": ["qmp_query", "qmp_events", "qmp_bridge"],
            "policy_gate": "allow_qmp",
        },
        {
            "scope": "secret_read",
            "enabled": config.allow_secret_read,
            "families": ["secret_value_read"],
            "policy_gate": "allow_secret_read",
        },
    ]
    return {
        "source": "server",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "items": scopes,
        "total_count": len(scopes),
        "policy": config.to_policy_dict(),
    }
