"""QMP tools with policy checks."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.adapters.qmp_adapter import QMPAdapter
from libvirt_mcp_server.errors import MCPError


async def qmp_command(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    command: str,
    arguments: dict,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command=command, arguments=arguments)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_capabilities(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.capabilities(domain_ref=domain_ref)
    raw_response = payload.get("response", {})
    raw_return = raw_response.get("return", [])
    commands: list[dict] = []
    if isinstance(raw_return, list):
        for item in raw_return:
            if isinstance(item, dict) and "name" in item:
                name = item["name"]
                in_allowlist = qmp_adapter._is_allowed(name)
                commands.append({"name": name, "allowed": in_allowlist})
    payload["commands"] = commands
    payload["command_count"] = len(commands)
    payload["allowed_count"] = sum(1 for c in commands if c["allowed"])
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_events(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    event_types: list[str],
    since: str | None,
    hypervisor_ref: str | None,
    timeout_seconds: float = 2.0,
) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.collect_events(
        domain_ref=domain_ref,
        timeout_seconds=timeout_seconds,
        event_types=event_types if event_types else None,
    )
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    payload["since"] = since
    _append_qmp_events(config, payload)
    return payload


def qmp_replay_events(
    config: ServerConfig,
    *,
    domain_ref: str | None,
    event_types: list[str],
    since: str | None,
    limit: int,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_allowed(config)
    event_log = Path(config.qmp_event_log_path)
    filters = set(event_types)
    items: list[dict] = []
    if event_log.exists():
        for line in event_log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if domain_ref and record.get("domain_ref") != domain_ref:
                continue
            if since and str(record.get("timestamp", "")) < since:
                continue
            event_name = record.get("event", {}).get("event")
            if filters and event_name not in filters:
                continue
            items.append(record)
    sliced = items[-limit:]
    return {
        "source": "qmp",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref or "default",
        "domain_ref": domain_ref,
        "event_types_filter": event_types,
        "items": sliced,
        "total_count": len(sliced),
        "event_log_path": str(event_log),
    }


def plan_qmp_backup(
    config: ServerConfig,
    *,
    domain_ref: str,
    device: str,
    export_name: str | None,
    address: dict,
    bitmap: str | None,
    writable: bool,
    backup_target: str | None,
    sync: str,
    job_id: str | None,
    speed: int,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_allowed(config)
    steps = _backup_plan_steps(
        device=device,
        export_name=export_name,
        address=address,
        bitmap=bitmap,
        writable=writable,
        backup_target=backup_target,
        sync=sync,
        job_id=job_id,
        speed=speed,
    )
    return {
        "source": "server",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref or "default",
        "domain_ref": domain_ref,
        "requires_mutations": True,
        "steps": steps,
        "total_count": len(steps),
    }


async def start_qmp_nbd_backup(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    device: str,
    export_name: str | None,
    address: dict,
    bitmap: str | None,
    writable: bool,
    backup_target: str | None,
    sync: str,
    job_id: str | None,
    speed: int,
    cleanup_on_failure: bool,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "start_qmp_nbd_backup")
    completed: list[dict] = []
    try:
        start_result = await qmp_nbd_server_start(
            config,
            qmp_adapter,
            domain_ref=domain_ref,
            address=address,
            tls_creds=None,
            tls_authz=None,
            hypervisor_ref=hypervisor_ref,
        )
        completed.append({"step": "qmp_nbd_server_start", "result": start_result})

        add_result = await qmp_nbd_server_add(
            config,
            qmp_adapter,
            domain_ref=domain_ref,
            device=device,
            export_name=export_name,
            writable=writable,
            bitmap=bitmap,
            hypervisor_ref=hypervisor_ref,
        )
        completed.append({"step": "qmp_nbd_server_add", "result": add_result})

        if backup_target:
            backup_result = await qmp_blockdev_backup(
                config,
                qmp_adapter,
                domain_ref=domain_ref,
                device=device,
                target=backup_target,
                sync=sync,
                job_id=job_id,
                speed=speed,
                hypervisor_ref=hypervisor_ref,
            )
            completed.append({"step": "qmp_blockdev_backup", "result": backup_result})
    except Exception:
        if cleanup_on_failure and completed:
            try:
                await qmp_adapter.execute(domain_ref=domain_ref, command="nbd-server-stop", arguments={})
            except Exception:
                pass
        raise

    return {
        "source": "server",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref or "default",
        "domain_ref": domain_ref,
        "status": "started",
        "steps": completed,
        "total_count": len(completed),
    }


async def stop_qmp_nbd_backup(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    export_name: str | None,
    remove_export: bool,
    stop_server: bool,
    mode: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "stop_qmp_nbd_backup")
    completed: list[dict] = []
    if remove_export and export_name:
        remove_result = await qmp_nbd_server_remove(
            config,
            qmp_adapter,
            domain_ref=domain_ref,
            export_name=export_name,
            mode=mode,
            hypervisor_ref=hypervisor_ref,
        )
        completed.append({"step": "qmp_nbd_server_remove", "result": remove_result})
    if stop_server:
        stop_result = await qmp_nbd_server_stop(
            config,
            qmp_adapter,
            domain_ref=domain_ref,
            hypervisor_ref=hypervisor_ref,
        )
        completed.append({"step": "qmp_nbd_server_stop", "result": stop_result})
    return {
        "source": "server",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref or "default",
        "domain_ref": domain_ref,
        "status": "stopped",
        "steps": completed,
        "total_count": len(completed),
    }


async def get_qmp_backup_status(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    job_id: str | None,
    event_limit: int,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_allowed(config)
    jobs = await qmp_adapter.execute(domain_ref=domain_ref, command="query-block-jobs", arguments={})
    replay = qmp_replay_events(
        config,
        domain_ref=domain_ref,
        event_types=["BLOCK_JOB_COMPLETED", "BLOCK_JOB_CANCELLED", "BLOCK_JOB_ERROR", "JOB_STATUS_CHANGE"],
        since=None,
        limit=event_limit,
        hypervisor_ref=hypervisor_ref,
    )
    return {
        "source": "server",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref or "default",
        "domain_ref": domain_ref,
        "job_id": job_id,
        "block_jobs": jobs,
        "events": replay["items"],
        "event_count": replay["total_count"],
    }


# ---------------------------------------------------------------------------
# Typed read-only query tools
# ---------------------------------------------------------------------------


async def qmp_query_status(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-status", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_query_version(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-version", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_query_cpus(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-cpus-fast", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_query_balloon(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-balloon", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_query_block(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-block", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_query_blockstats(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-blockstats", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_query_pci(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-pci", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_query_iothreads(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-iothreads", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_query_chardev(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-chardev", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_query_vnc(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-vnc", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_query_block_jobs(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-block-jobs", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_query_machines(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-machines", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


# ---------------------------------------------------------------------------
# Mutation tools
# ---------------------------------------------------------------------------


async def qmp_balloon(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    balloon_mb: int,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_balloon")
    payload = await qmp_adapter.execute(
        domain_ref=domain_ref,
        command="balloon",
        arguments={"value": balloon_mb * 1024 * 1024},
    )
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_block_stream(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    device: str,
    base: str | None = None,
    speed: int = 0,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_block_stream")
    arguments: dict = {"device": device}
    if base is not None:
        arguments["base"] = base
    if speed > 0:
        arguments["speed"] = speed
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="block-stream", arguments=arguments)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_block_job_cancel(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    device: str,
    force: bool = False,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_block_job_cancel")
    payload = await qmp_adapter.execute(
        domain_ref=domain_ref,
        command="block-job-cancel",
        arguments={"device": device, "force": force},
    )
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_block_job_pause(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    device: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_block_job_pause")
    payload = await qmp_adapter.execute(
        domain_ref=domain_ref,
        command="block-job-pause",
        arguments={"device": device},
    )
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_block_job_resume(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    device: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_block_job_resume")
    payload = await qmp_adapter.execute(
        domain_ref=domain_ref,
        command="block-job-resume",
        arguments={"device": device},
    )
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_block_job_complete(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    device: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_block_job_complete")
    payload = await qmp_adapter.execute(
        domain_ref=domain_ref,
        command="block-job-complete",
        arguments={"device": device},
    )
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_device_add(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    driver: str,
    device_id: str,
    device_opts: dict,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_device_add")
    arguments = {"driver": driver, "id": device_id, **device_opts}
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="device_add", arguments=arguments)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_device_del(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    device_id: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_device_del")
    payload = await qmp_adapter.execute(
        domain_ref=domain_ref,
        command="device_del",
        arguments={"id": device_id},
    )
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


# ---------------------------------------------------------------------------
# Part 1A: CPU hotplug
# ---------------------------------------------------------------------------


async def qmp_query_hotpluggable_cpus(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-hotpluggable-cpus", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_cpu_add(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    cpu_index: int,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_cpu_add")
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="cpu-add", arguments={"id": cpu_index})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


# ---------------------------------------------------------------------------
# Part 1B: Memory device controls
# ---------------------------------------------------------------------------


async def qmp_query_memory_devices(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-memory-devices", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_object_add(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    qom_type: str,
    obj_id: str,
    props: dict,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_object_add")
    arguments = {"qom-type": qom_type, "id": obj_id, **props}
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="object-add", arguments=arguments)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_object_del(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    obj_id: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_object_del")
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="object-del", arguments={"id": obj_id})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


# ---------------------------------------------------------------------------
# Part 1C: Block mirror and bitmaps
# ---------------------------------------------------------------------------


async def qmp_drive_mirror(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    device: str,
    target: str,
    format: str = "qcow2",
    sync: str = "full",
    speed: int = 0,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_drive_mirror")
    arguments: dict = {"device": device, "target": target, "format": format, "sync": sync}
    if speed > 0:
        arguments["speed"] = speed
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="drive-mirror", arguments=arguments)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_blockdev_backup(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    device: str,
    target: str,
    sync: str = "full",
    job_id: str | None = None,
    speed: int = 0,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_blockdev_backup")
    arguments: dict = {"device": device, "target": target, "sync": sync}
    if job_id:
        arguments["job-id"] = job_id
    if speed > 0:
        arguments["speed"] = speed
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="blockdev-backup", arguments=arguments)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_nbd_server_start(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    address: dict,
    tls_creds: str | None = None,
    tls_authz: str | None = None,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_nbd_server_start")
    arguments: dict = {"addr": address}
    if tls_creds:
        arguments["tls-creds"] = tls_creds
    if tls_authz:
        arguments["tls-authz"] = tls_authz
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="nbd-server-start", arguments=arguments)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_nbd_server_add(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    device: str,
    export_name: str | None = None,
    writable: bool = False,
    bitmap: str | None = None,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_nbd_server_add")
    arguments: dict = {"device": device, "writable": writable}
    if export_name:
        arguments["name"] = export_name
    if bitmap:
        arguments["bitmap"] = bitmap
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="nbd-server-add", arguments=arguments)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_nbd_server_remove(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    export_name: str,
    mode: str = "safe",
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_nbd_server_remove")
    payload = await qmp_adapter.execute(
        domain_ref=domain_ref,
        command="nbd-server-remove",
        arguments={"name": export_name, "mode": mode},
    )
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_nbd_server_stop(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_nbd_server_stop")
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="nbd-server-stop", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_query_block_dirty_bitmaps(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-block-dirty-bitmaps", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_block_dirty_bitmap_add(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    node: str,
    name: str,
    persistent: bool = True,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_block_dirty_bitmap_add")
    payload = await qmp_adapter.execute(
        domain_ref=domain_ref,
        command="block-dirty-bitmap-add",
        arguments={"node": node, "name": name, "persistent": persistent},
    )
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_block_dirty_bitmap_remove(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    node: str,
    name: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_block_dirty_bitmap_remove")
    payload = await qmp_adapter.execute(
        domain_ref=domain_ref,
        command="block-dirty-bitmap-remove",
        arguments={"node": node, "name": name},
    )
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_block_dirty_bitmap_clear(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    node: str,
    name: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_block_dirty_bitmap_clear")
    payload = await qmp_adapter.execute(
        domain_ref=domain_ref,
        command="block-dirty-bitmap-clear",
        arguments={"node": node, "name": name},
    )
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


# ---------------------------------------------------------------------------
# Part 1D: Netdev and chardev management
# ---------------------------------------------------------------------------


async def qmp_netdev_add(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    netdev_type: str,
    netdev_id: str,
    netdev_opts: dict,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_netdev_add")
    arguments = {"type": netdev_type, "id": netdev_id, **netdev_opts}
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="netdev_add", arguments=arguments)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_netdev_del(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    netdev_id: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_netdev_del")
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="netdev_del", arguments={"id": netdev_id})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_chardev_add(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    chardev_id: str,
    backend: dict,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_chardev_add")
    payload = await qmp_adapter.execute(
        domain_ref=domain_ref,
        command="chardev-add",
        arguments={"id": chardev_id, "backend": backend},
    )
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_chardev_remove(
    config: ServerConfig,
    qmp_adapter: QMPAdapter,
    *,
    domain_ref: str,
    chardev_id: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_qmp_mutations_allowed(config, "qmp_chardev_remove")
    payload = await qmp_adapter.execute(
        domain_ref=domain_ref,
        command="chardev-remove",
        arguments={"id": chardev_id},
    )
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


# ---------------------------------------------------------------------------
# Part 1E: Migration telemetry (read-only)
# ---------------------------------------------------------------------------


async def qmp_query_migrate(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-migrate", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_query_migrate_capabilities(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-migrate-capabilities", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


async def qmp_query_migrate_parameters(config: ServerConfig, qmp_adapter: QMPAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict:
    _ensure_qmp_allowed(config)
    payload = await qmp_adapter.execute(domain_ref=domain_ref, command="query-migrate-parameters", arguments={})
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


# ---------------------------------------------------------------------------
# Policy helpers
# ---------------------------------------------------------------------------


def _ensure_qmp_allowed(config: ServerConfig) -> None:
    if not config.allow_qmp:
        raise MCPError(code="QMP_DISABLED", message="QMP access is disabled by policy")


def _ensure_qmp_mutations_allowed(config: ServerConfig, tool_name: str) -> None:
    _ensure_qmp_allowed(config)
    if not config.allow_mutations:
        raise MCPError(
            code="MUTATIONS_DISABLED",
            message=f"Tool '{tool_name}' requires allow_mutations=true in server config",
        )


def _append_qmp_events(config: ServerConfig, payload: dict) -> None:
    events = payload.get("events") or []
    if not events:
        return
    event_log = Path(config.qmp_event_log_path)
    event_log.parent.mkdir(parents=True, exist_ok=True)
    observed_at = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()
    with event_log.open("a", encoding="utf-8") as handle:
        for event in events:
            record = {
                "source": "qmp",
                "timestamp": observed_at,
                "domain_ref": payload.get("domain_ref"),
                "event": event,
            }
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def _backup_plan_steps(
    *,
    device: str,
    export_name: str | None,
    address: dict,
    bitmap: str | None,
    writable: bool,
    backup_target: str | None,
    sync: str,
    job_id: str | None,
    speed: int,
) -> list[dict]:
    steps: list[dict] = [
        {"tool": "qmp_nbd_server_start", "arguments": {"address": address}},
        {
            "tool": "qmp_nbd_server_add",
            "arguments": {
                "device": device,
                "export_name": export_name,
                "writable": writable,
                "bitmap": bitmap,
            },
        },
    ]
    if backup_target:
        args = {"device": device, "target": backup_target, "sync": sync, "job_id": job_id}
        if speed > 0:
            args["speed"] = speed
        steps.append({"tool": "qmp_blockdev_backup", "arguments": args})
    steps.append(
        {
            "tool": "stop_qmp_nbd_backup",
            "arguments": {"export_name": export_name, "remove_export": bool(export_name), "stop_server": True},
        }
    )
    return steps
