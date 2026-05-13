"""Configuration and policy model for the libvirt MCP server."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_csv(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [p.strip() for p in raw.split(",") if p.strip()]


def _parse_hypervisors() -> dict[str, str]:
    values = _env_csv("LIBVIRT_URIS", "")
    if not values:
        default_uri = os.getenv("LIBVIRT_URI", "qemu:///system")
        return {"default": default_uri}

    parsed: dict[str, str] = {}
    anonymous_index = 1
    for value in values:
        if "=" in value:
            ref, uri = value.split("=", 1)
            ref = ref.strip()
            uri = uri.strip()
            if ref and uri:
                parsed[ref] = uri
                continue

        parsed[f"hv{anonymous_index}"] = value
        anonymous_index += 1

    if "default" not in parsed:
        parsed["default"] = next(iter(parsed.values()))
    return parsed


@dataclass(slots=True)
class ServerConfig:
    libvirt_uri: str
    hypervisors: dict[str, str]
    ssh_identity: str | None
    support_session: bool

    allow_mutations: bool
    mutation_domain_allowlist: set[str]
    allow_define: bool
    allow_destructive: bool
    destructive_domain_allowlist: set[str]
    allow_qmp: bool
    allow_uri_override: bool
    allow_secret_read: bool

    qmp_socket_dir: str
    qmp_allowlist: set[str]
    qmp_mutation_allowlist: set[str]
    qmp_event_log_path: str
    test_resource_prefix: str

    audit_log_path: str
    log_level: str
    max_concurrent_operations: int

    @classmethod
    def from_env(cls) -> "ServerConfig":
        qmp_allow_raw = _env_csv("MCP_QMP_ALLOWLIST", "query-status,query-version,query-cpus-fast,query-balloon,query-block,query-blockstats,query-pci,query-iothreads,query-chardev,query-vnc,query-block-jobs,query-machines,query-commands,query-hotpluggable-cpus,query-memory-devices,query-block-dirty-bitmaps,query-migrate,query-migrate-capabilities,query-migrate-parameters")
        qmp_allowlist = set(qmp_allow_raw)

        return cls(
            libvirt_uri=os.getenv("LIBVIRT_URI", "qemu:///system"),
            hypervisors=_parse_hypervisors(),
            ssh_identity=os.getenv("LIBVIRT_SSH_IDENTITY"),
            support_session=_env_bool("MCP_LIBVIRT_SUPPORT_SESSION", True),
            allow_mutations=_env_bool("MCP_LIBVIRT_ALLOW_MUTATIONS", False),
            mutation_domain_allowlist=set(_env_csv("MCP_LIBVIRT_MUTATION_DOMAIN_ALLOWLIST", "")),
            allow_define=_env_bool("MCP_LIBVIRT_ALLOW_DEFINE", False),
            allow_destructive=_env_bool("MCP_LIBVIRT_ALLOW_DESTRUCTIVE", False),
            destructive_domain_allowlist=set(_env_csv("MCP_LIBVIRT_DESTRUCTIVE_DOMAIN_ALLOWLIST", "")),
            allow_qmp=_env_bool("MCP_QMP_ENABLE", True),
            allow_uri_override=_env_bool("MCP_LIBVIRT_ALLOW_URI_OVERRIDE", False),
            allow_secret_read=_env_bool("MCP_LIBVIRT_ALLOW_SECRET_READ", False),
            qmp_socket_dir=os.getenv("MCP_QMP_SOCKET_DIR", "/var/run/qemu-server"),
            qmp_allowlist=qmp_allowlist,
            qmp_mutation_allowlist=set(_env_csv(
                "MCP_QMP_MUTATION_ALLOWLIST",
                "balloon,block-stream,block-job-cancel,block-job-pause,block-job-resume,block-job-complete,device_add,device_del,cpu-add,object-add,object-del,drive-mirror,blockdev-backup,nbd-server-start,nbd-server-add,nbd-server-remove,nbd-server-stop,block-dirty-bitmap-add,block-dirty-bitmap-remove,block-dirty-bitmap-clear,netdev_add,netdev_del,chardev-add,chardev-remove",
            )),
            qmp_event_log_path=os.getenv("MCP_QMP_EVENT_LOG_PATH", "./qmp-events.log"),
            test_resource_prefix=os.getenv("LIBVIRT_MCP_TEST_PREFIX", "mcp_test_"),
            audit_log_path=os.getenv("MCP_AUDIT_LOG_PATH", "./audit.log"),
            log_level=os.getenv("MCP_LOG_LEVEL", "INFO"),
            max_concurrent_operations=_env_int("MCP_MAX_CONCURRENT_OPERATIONS", 0),
        )

    def get_hypervisor_uri(self, hypervisor_ref: str | None) -> str:
        if hypervisor_ref is None:
            return self.hypervisors.get("default", self.libvirt_uri)
        if hypervisor_ref not in self.hypervisors:
            raise KeyError(hypervisor_ref)
        return self.hypervisors[hypervisor_ref]

    def to_policy_dict(self) -> dict[str, Any]:
        return {
            "allow_mutations": self.allow_mutations,
            "mutation_domain_allowlist": sorted(self.mutation_domain_allowlist),
            "allow_define": self.allow_define,
            "allow_destructive": self.allow_destructive,
            "destructive_domain_allowlist": sorted(self.destructive_domain_allowlist),
            "allow_qmp": self.allow_qmp,
            "allow_uri_override": self.allow_uri_override,
            "allow_secret_read": self.allow_secret_read,
            "qmp_event_log_path": self.qmp_event_log_path,
            "test_resource_prefix": self.test_resource_prefix,
            "max_concurrent_operations": self.max_concurrent_operations,
        }
