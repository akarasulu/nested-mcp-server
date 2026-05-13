"""libvirt adapter wrapped behind normalized responses and errors."""

from __future__ import annotations

from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from typing import Any

from libvirt_mcp_server.errors import MCPError

try:
    import libvirt  # type: ignore
except Exception:  # pragma: no cover - import depends on host installation
    libvirt = None


_LIBVIRT_STATE = {
    0: "nostate",
    1: "running",
    2: "blocked",
    3: "paused",
    4: "shutdown",
    5: "shutoff",
    6: "crashed",
    7: "pmsuspended",
}


class LibvirtAdapter:
    def __init__(self) -> None:
        self._connections: dict[str, Any] = {}

    def _ensure_libvirt(self) -> None:
        if libvirt is None:
            raise MCPError(
                code="LIBVIRT_UNAVAILABLE",
                message="libvirt-python is not available in this environment",
                retryable=False,
            )

    def _connect(self, uri: str):
        self._ensure_libvirt()
        if uri in self._connections:
            return self._connections[uri]
        try:
            conn = libvirt.open(uri)
        except Exception as exc:
            raise MCPError(
                code="LIBVIRT_CONNECTION_ERROR",
                message=f"Unable to connect to libvirt URI '{uri}'",
                retryable=True,
                details={"uri": uri, "source": "libvirt", "cause": str(exc)},
            )
        if conn is None:
            raise MCPError(
                code="LIBVIRT_CONNECTION_ERROR",
                message=f"libvirt.open returned no connection for '{uri}'",
                retryable=True,
                details={"uri": uri, "source": "libvirt"},
            )
        self._connections[uri] = conn
        return conn

    def host_info(self, uri: str) -> dict[str, Any]:
        conn = self._connect(uri)
        node = conn.getInfo()
        capabilities_xml = conn.getCapabilities()
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uri": uri,
            "hostname": conn.getHostname(),
            "hypervisor_type": conn.getType(),
            "libvirt_version": conn.getLibVersion(),
            "node_info": {
                "model": node[0],
                "memory_mb": int(node[1]),
                "cpus": int(node[2]),
                "mhz": int(node[3]),
                "numa_nodes": int(node[4]),
                "sockets": int(node[5]),
                "cores": int(node[6]),
                "threads": int(node[7]),
            },
            "capabilities_summary": self._summarize_capabilities(capabilities_xml),
        }

    def list_domains(
        self,
        uri: str,
        *,
        active_only: bool = False,
        inactive_only: bool = False,
        name_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        conn = self._connect(uri)
        domains = conn.listAllDomains()
        out: list[dict[str, Any]] = []
        for dom in domains:
            summary = self._domain_summary(dom)
            if active_only and not summary["is_active"]:
                continue
            if inactive_only and summary["is_active"]:
                continue
            if name_prefix and not summary["name"].startswith(name_prefix):
                continue
            out.append(summary)
        return out

    def get_domain(self, uri: str, domain_ref: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        return self._domain_summary(dom)

    def get_domain_xml(self, uri: str, domain_ref: str, *, live: bool, inactive: bool) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)

        flags = 0
        if live and hasattr(libvirt, "VIR_DOMAIN_XML_SECURE"):
            flags |= 0
        if inactive and hasattr(libvirt, "VIR_DOMAIN_XML_INACTIVE"):
            flags |= libvirt.VIR_DOMAIN_XML_INACTIVE

        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "xml": dom.XMLDesc(flags),
            "live": live,
            "inactive": inactive,
        }

    def define_domain_xml(self, uri: str, domain_xml: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            dom = conn.defineXML(domain_xml)
        except Exception as exc:
            raise MCPError(
                code="INVALID_DOMAIN_XML",
                message="Failed to define domain from XML",
                retryable=False,
                details={"source": "libvirt", "cause": str(exc)},
            )
        if dom is None:
            raise MCPError(
                code="INVALID_DOMAIN_XML",
                message="libvirt did not return a domain after defineXML",
                retryable=False,
                details={"source": "libvirt"},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": dom.name(),
            "status": "defined",
        }

    def undefine_domain(self, uri: str, domain_ref: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            dom.undefine()
        except Exception as exc:
            raise MCPError(
                code="DOMAIN_UNDEFINE_FAILED",
                message=f"Failed to undefine domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "status": "undefined",
        }

    def validate_domain_xml(self, uri: str, domain_xml: str) -> dict[str, Any]:
        self._ensure_libvirt()
        try:
            root = ET.fromstring(domain_xml)
        except ET.ParseError as exc:
            raise MCPError(
                code="INVALID_DOMAIN_XML",
                message=f"XML parse error: {exc}",
                retryable=False,
                details={"source": "libvirt", "cause": str(exc)},
            )
        if root.tag != "domain":
            raise MCPError(
                code="INVALID_DOMAIN_XML",
                message=f"Root element is <{root.tag}>, expected <domain>",
                retryable=False,
                details={"source": "libvirt"},
            )
        name_el = root.find("name")
        name = name_el.text.strip() if name_el is not None and name_el.text else None
        domain_type = root.get("type")
        issues: list[str] = []
        if name is None:
            issues.append("missing <name> element")
        if root.find("memory") is None:
            issues.append("missing <memory> element")
        if root.find("vcpu") is None:
            issues.append("missing <vcpu> element")
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": name,
            "domain_type": domain_type,
            "valid": len(issues) == 0,
            "issues": issues,
            "element_count": len(list(root)),
        }

    def update_domain_device_xml(self, uri: str, domain_ref: str, device_xml: str, *, live: bool, config: bool) -> dict[str, Any]:
        flags = 0
        if live:
            flags |= 1
        if config:
            flags |= 2
        if flags == 0:
            raise MCPError(
                code="INVALID_FLAGS",
                message="At least one of live or persistent must be true for update_domain_device_xml",
                retryable=False,
                details={"source": "libvirt"},
            )
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            dom.updateDeviceFlags(device_xml, flags)
        except Exception as exc:
            raise MCPError(
                code="DOMAIN_UPDATE_DEVICE_FAILED",
                message=f"Failed to update device for domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "status": "updated",
            "live": live,
            "config": config,
        }

    def set_autostart(self, uri: str, domain_ref: str, autostart: bool) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        dom.setAutostart(1 if autostart else 0)
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "autostart": autostart,
        }

    def lifecycle_action(self, uri: str, domain_ref: str, action: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)

        action_map = {
            "start_domain": dom.create,
            "shutdown_domain": dom.shutdown,
            "destroy_domain": dom.destroy,
            "reboot_domain": dom.reboot,
            "suspend_domain": dom.suspend,
            "resume_domain": dom.resume,
        }
        if action not in action_map:
            raise MCPError(code="INVALID_ACTION", message=f"Unsupported lifecycle action '{action}'")

        fn = action_map[action]
        if action == "reboot_domain":
            fn(0)
        else:
            fn()

        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "action": action,
            "status": "requested",
        }

    def list_networks(self, uri: str) -> list[dict[str, Any]]:
        conn = self._connect(uri)
        networks = conn.listAllNetworks()
        out = []
        for net in networks:
            out.append(
                {
                    "source": "libvirt",
                    "name": net.name(),
                    "uuid": net.UUIDString(),
                    "is_active": bool(net.isActive()),
                    "is_persistent": bool(net.isPersistent()),
                    "bridge_name": net.bridgeName() if hasattr(net, "bridgeName") else None,
                }
            )
        return out

    def list_storage_pools(self, uri: str) -> list[dict[str, Any]]:
        conn = self._connect(uri)
        pools = conn.listAllStoragePools()
        out = []
        for pool in pools:
            info = pool.info()
            out.append(
                {
                    "source": "libvirt",
                    "name": pool.name(),
                    "uuid": pool.UUIDString() if hasattr(pool, "UUIDString") else None,
                    "state": int(info[0]),
                    "capacity": int(info[1]),
                    "allocation": int(info[2]),
                    "available": int(info[3]),
                }
            )
        return out

    def get_storage_pool(self, uri: str, pool_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolLookupByName(pool_name)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_POOL_NOT_FOUND",
                message=f"Storage pool '{pool_name}' was not found",
                retryable=False,
                details={"pool_name": pool_name, "source": "libvirt", "cause": str(exc)},
            )

        info = pool.info()
        return {
            "source": "libvirt",
            "name": pool.name(),
            "uuid": pool.UUIDString() if hasattr(pool, "UUIDString") else None,
            "state": int(info[0]),
            "capacity": int(info[1]),
            "allocation": int(info[2]),
            "available": int(info[3]),
        }

    def list_storage_volumes(self, uri: str, pool_name: str) -> list[dict[str, Any]]:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolLookupByName(pool_name)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_POOL_NOT_FOUND",
                message=f"Storage pool '{pool_name}' was not found",
                retryable=False,
                details={"pool_name": pool_name, "source": "libvirt", "cause": str(exc)},
            )

        out: list[dict[str, Any]] = []
        for volume in pool.listAllVolumes():
            info = volume.info()
            out.append(
                {
                    "source": "libvirt",
                    "pool_name": pool_name,
                    "name": volume.name(),
                    "key": volume.key(),
                    "path": volume.path(),
                    "type": int(info[0]),
                    "capacity": int(info[1]),
                    "allocation": int(info[2]),
                }
            )
        return out

    def get_storage_volume(self, uri: str, pool_name: str, volume_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolLookupByName(pool_name)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_POOL_NOT_FOUND",
                message=f"Storage pool '{pool_name}' was not found",
                retryable=False,
                details={"pool_name": pool_name, "source": "libvirt", "cause": str(exc)},
            )

        try:
            volume = pool.storageVolLookupByName(volume_name)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_VOLUME_NOT_FOUND",
                message=f"Storage volume '{volume_name}' was not found in pool '{pool_name}'",
                retryable=False,
                details={"pool_name": pool_name, "volume_name": volume_name, "source": "libvirt", "cause": str(exc)},
            )

        info = volume.info()
        return {
            "source": "libvirt",
            "pool_name": pool_name,
            "name": volume.name(),
            "key": volume.key(),
            "path": volume.path(),
            "type": int(info[0]),
            "capacity": int(info[1]),
            "allocation": int(info[2]),
        }

    def get_network(self, uri: str, network_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            net = conn.networkLookupByName(network_name)
        except Exception as exc:
            raise MCPError(
                code="NETWORK_NOT_FOUND",
                message=f"Network '{network_name}' was not found",
                retryable=False,
                details={"network_name": network_name, "source": "libvirt", "cause": str(exc)},
            )

        return {
            "source": "libvirt",
            "name": net.name(),
            "uuid": net.UUIDString(),
            "is_active": bool(net.isActive()),
            "is_persistent": bool(net.isPersistent()),
            "bridge_name": net.bridgeName() if hasattr(net, "bridgeName") else None,
            "xml": net.XMLDesc(0),
        }

    def define_network_xml(self, uri: str, network_xml: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            net = conn.networkDefineXML(network_xml)
        except Exception as exc:
            raise MCPError(
                code="INVALID_NETWORK_XML",
                message="Failed to define network from XML",
                retryable=False,
                details={"source": "libvirt", "cause": str(exc)},
            )
        if net is None:
            raise MCPError(
                code="INVALID_NETWORK_XML",
                message="libvirt did not return a network after networkDefineXML",
                retryable=False,
                details={"source": "libvirt"},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "network_name": net.name(),
            "status": "defined",
        }

    def start_network(self, uri: str, network_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            net = conn.networkLookupByName(network_name)
            net.create()
        except Exception as exc:
            raise MCPError(
                code="NETWORK_START_FAILED",
                message=f"Failed to start network '{network_name}'",
                retryable=False,
                details={"network_name": network_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "network_name": network_name,
            "status": "started",
        }

    def destroy_network(self, uri: str, network_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            net = conn.networkLookupByName(network_name)
            net.destroy()
        except Exception as exc:
            raise MCPError(
                code="NETWORK_DESTROY_FAILED",
                message=f"Failed to destroy network '{network_name}'",
                retryable=False,
                details={"network_name": network_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "network_name": network_name,
            "status": "destroyed",
        }

    def undefine_network(self, uri: str, network_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            net = conn.networkLookupByName(network_name)
            net.undefine()
        except Exception as exc:
            raise MCPError(
                code="NETWORK_UNDEFINE_FAILED",
                message=f"Failed to undefine network '{network_name}'",
                retryable=False,
                details={"network_name": network_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "network_name": network_name,
            "status": "undefined",
        }

    def define_storage_pool_xml(self, uri: str, pool_xml: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolDefineXML(pool_xml, 0)
        except Exception as exc:
            raise MCPError(
                code="INVALID_STORAGE_POOL_XML",
                message="Failed to define storage pool from XML",
                retryable=False,
                details={"source": "libvirt", "cause": str(exc)},
            )
        if pool is None:
            raise MCPError(
                code="INVALID_STORAGE_POOL_XML",
                message="libvirt did not return a pool after storagePoolDefineXML",
                retryable=False,
                details={"source": "libvirt"},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool_name": pool.name(),
            "status": "defined",
        }

    def start_storage_pool(self, uri: str, pool_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolLookupByName(pool_name)
            pool.create(0)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_POOL_START_FAILED",
                message=f"Failed to start storage pool '{pool_name}'",
                retryable=False,
                details={"pool_name": pool_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool_name": pool_name,
            "status": "started",
        }

    def destroy_storage_pool(self, uri: str, pool_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolLookupByName(pool_name)
            pool.destroy()
        except Exception as exc:
            raise MCPError(
                code="STORAGE_POOL_DESTROY_FAILED",
                message=f"Failed to destroy storage pool '{pool_name}'",
                retryable=False,
                details={"pool_name": pool_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool_name": pool_name,
            "status": "destroyed",
        }

    def undefine_storage_pool(self, uri: str, pool_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolLookupByName(pool_name)
            pool.undefine()
        except Exception as exc:
            raise MCPError(
                code="STORAGE_POOL_UNDEFINE_FAILED",
                message=f"Failed to undefine storage pool '{pool_name}'",
                retryable=False,
                details={"pool_name": pool_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool_name": pool_name,
            "status": "undefined",
        }

    def create_storage_volume_xml(self, uri: str, pool_name: str, volume_xml: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolLookupByName(pool_name)
            if hasattr(pool, "storageVolCreateXML"):
                vol = pool.storageVolCreateXML(volume_xml, 0)
            else:
                vol = pool.createXML(volume_xml, 0)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_VOLUME_CREATE_FAILED",
                message=f"Failed to create storage volume in pool '{pool_name}'",
                retryable=False,
                details={"pool_name": pool_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool_name": pool_name,
            "volume_name": vol.name(),
            "status": "created",
        }

    def delete_storage_volume(self, uri: str, pool_name: str, volume_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolLookupByName(pool_name)
            vol = pool.storageVolLookupByName(volume_name)
            vol.delete(0)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_VOLUME_DELETE_FAILED",
                message=f"Failed to delete volume '{volume_name}' from pool '{pool_name}'",
                retryable=False,
                details={"pool_name": pool_name, "volume_name": volume_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool_name": pool_name,
            "volume_name": volume_name,
            "status": "deleted",
        }

    def list_domain_snapshots(self, uri: str, domain_ref: str) -> list[dict[str, Any]]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)

        out: list[dict[str, Any]] = []
        for snapshot in dom.listAllSnapshots(0):
            out.append(
                {
                    "source": "libvirt",
                    "name": snapshot.getName(),
                    "xml": snapshot.getXMLDesc(0),
                }
            )
        return out

    def create_domain_snapshot(self, uri: str, domain_ref: str, snapshot_xml: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            snap = dom.snapshotCreateXML(snapshot_xml, 0)
        except Exception as exc:
            raise MCPError(
                code="SNAPSHOT_CREATE_FAILED",
                message=f"Failed to create snapshot for domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "source": "libvirt", "cause": str(exc)},
            )

        return {
            "source": "libvirt",
            "domain_ref": domain_ref,
            "snapshot_name": snap.getName(),
            "status": "created",
        }

    def revert_domain_snapshot(self, uri: str, domain_ref: str, snapshot_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            snap = dom.snapshotLookupByName(snapshot_name, 0)
        except Exception as exc:
            raise MCPError(
                code="SNAPSHOT_NOT_FOUND",
                message=f"Snapshot '{snapshot_name}' was not found for domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "snapshot_name": snapshot_name, "source": "libvirt", "cause": str(exc)},
            )

        try:
            dom.revertToSnapshot(snap, 0)
        except Exception as exc:
            raise MCPError(
                code="SNAPSHOT_REVERT_FAILED",
                message=f"Failed to revert snapshot '{snapshot_name}' for domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "snapshot_name": snapshot_name, "source": "libvirt", "cause": str(exc)},
            )

        return {
            "source": "libvirt",
            "domain_ref": domain_ref,
            "snapshot_name": snapshot_name,
            "status": "reverted",
        }

    def delete_domain_snapshot(self, uri: str, domain_ref: str, snapshot_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            snap = dom.snapshotLookupByName(snapshot_name, 0)
        except Exception as exc:
            raise MCPError(
                code="SNAPSHOT_NOT_FOUND",
                message=f"Snapshot '{snapshot_name}' was not found for domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "snapshot_name": snapshot_name, "source": "libvirt", "cause": str(exc)},
            )

        try:
            snap.delete(0)
        except Exception as exc:
            raise MCPError(
                code="SNAPSHOT_DELETE_FAILED",
                message=f"Failed to delete snapshot '{snapshot_name}' for domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "snapshot_name": snapshot_name, "source": "libvirt", "cause": str(exc)},
            )

        return {
            "source": "libvirt",
            "domain_ref": domain_ref,
            "snapshot_name": snapshot_name,
            "status": "deleted",
        }

    # ------------------------------------------------------------------
    # Node devices
    # ------------------------------------------------------------------

    def list_node_devices(self, uri: str, capability: str | None = None) -> list[dict[str, Any]]:
        conn = self._connect(uri)
        try:
            devices = conn.listAllDevices(0)
        except Exception as exc:
            raise MCPError(
                code="NODE_DEVICE_LIST_FAILED",
                message="Failed to list node devices",
                retryable=False,
                details={"source": "libvirt", "cause": str(exc)},
            )
        out: list[dict[str, Any]] = []
        for dev in devices:
            try:
                name = dev.name()
                xml = dev.XMLDesc(0)
                summary = self._parse_node_device_xml(xml)
                if capability and summary.get("capability") != capability:
                    continue
                out.append({"source": "libvirt", "name": name, "xml_summary": summary})
            except Exception:
                continue
        return out

    def get_node_device(self, uri: str, device_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            dev = conn.nodeDeviceLookupByName(device_name)
        except Exception as exc:
            raise MCPError(
                code="NODE_DEVICE_NOT_FOUND",
                message=f"Node device '{device_name}' was not found",
                retryable=False,
                details={"device_name": device_name, "source": "libvirt", "cause": str(exc)},
            )
        xml = dev.XMLDesc(0)
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "device_name": device_name,
            "xml": xml,
            "xml_summary": self._parse_node_device_xml(xml),
        }

    def detach_node_device(self, uri: str, device_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            dev = conn.nodeDeviceLookupByName(device_name)
        except Exception as exc:
            raise MCPError(
                code="NODE_DEVICE_NOT_FOUND",
                message=f"Node device '{device_name}' was not found",
                retryable=False,
                details={"device_name": device_name, "source": "libvirt", "cause": str(exc)},
            )
        try:
            if hasattr(dev, "detachFlags"):
                dev.detachFlags(0, None, 0)
            else:
                dev.dettach()
        except Exception as exc:
            raise MCPError(
                code="NODE_DEVICE_DETACH_FAILED",
                message=f"Failed to detach node device '{device_name}'",
                retryable=False,
                details={"device_name": device_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "device_name": device_name,
            "status": "detached",
        }

    def reattach_node_device(self, uri: str, device_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            dev = conn.nodeDeviceLookupByName(device_name)
        except Exception as exc:
            raise MCPError(
                code="NODE_DEVICE_NOT_FOUND",
                message=f"Node device '{device_name}' was not found",
                retryable=False,
                details={"device_name": device_name, "source": "libvirt", "cause": str(exc)},
            )
        try:
            dev.reAttach()
        except Exception as exc:
            raise MCPError(
                code="NODE_DEVICE_REATTACH_FAILED",
                message=f"Failed to reattach node device '{device_name}'",
                retryable=False,
                details={"device_name": device_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "device_name": device_name,
            "status": "reattached",
        }

    def _parse_node_device_xml(self, xml: str) -> dict[str, Any]:
        try:
            root = ET.fromstring(xml)
        except Exception:
            return {}
        cap = root.find("capability")
        cap_type = cap.get("type") if cap is not None else None
        return {"capability": cap_type}

    # ------------------------------------------------------------------
    # Host network interfaces
    # ------------------------------------------------------------------

    def list_interfaces(self, uri: str) -> list[dict[str, Any]]:
        conn = self._connect(uri)
        try:
            ifaces = conn.listAllInterfaces(0)
        except Exception as exc:
            raise MCPError(
                code="INTERFACE_LIST_FAILED",
                message="Failed to list network interfaces",
                retryable=False,
                details={"source": "libvirt", "cause": str(exc)},
            )
        out: list[dict[str, Any]] = []
        for iface in ifaces:
            try:
                mac = iface.MACString() if hasattr(iface, "MACString") else None
                out.append({
                    "source": "libvirt",
                    "name": iface.name(),
                    "mac": mac,
                    "is_active": bool(iface.isActive()),
                })
            except Exception:
                continue
        return out

    def get_interface(self, uri: str, iface_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            iface = conn.interfaceLookupByName(iface_name)
        except Exception as exc:
            raise MCPError(
                code="INTERFACE_NOT_FOUND",
                message=f"Interface '{iface_name}' was not found",
                retryable=False,
                details={"iface_name": iface_name, "source": "libvirt", "cause": str(exc)},
            )
        mac = iface.MACString() if hasattr(iface, "MACString") else None
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "name": iface.name(),
            "mac": mac,
            "is_active": bool(iface.isActive()),
            "xml": iface.XMLDesc(0),
        }

    def define_interface_xml(self, uri: str, interface_xml: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            iface = conn.interfaceDefineXML(interface_xml, 0)
        except Exception as exc:
            raise MCPError(
                code="INVALID_INTERFACE_XML",
                message="Failed to define interface from XML",
                retryable=False,
                details={"source": "libvirt", "cause": str(exc)},
            )
        if iface is None:
            raise MCPError(
                code="INVALID_INTERFACE_XML",
                message="libvirt did not return an interface after interfaceDefineXML",
                retryable=False,
                details={"source": "libvirt"},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iface_name": iface.name(),
            "status": "defined",
        }

    def start_interface(self, uri: str, iface_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            iface = conn.interfaceLookupByName(iface_name)
            iface.create(0)
        except Exception as exc:
            raise MCPError(
                code="INTERFACE_START_FAILED",
                message=f"Failed to start interface '{iface_name}'",
                retryable=False,
                details={"iface_name": iface_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iface_name": iface_name,
            "status": "started",
        }

    def stop_interface(self, uri: str, iface_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            iface = conn.interfaceLookupByName(iface_name)
            iface.destroy(0)
        except Exception as exc:
            raise MCPError(
                code="INTERFACE_STOP_FAILED",
                message=f"Failed to stop interface '{iface_name}'",
                retryable=False,
                details={"iface_name": iface_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iface_name": iface_name,
            "status": "stopped",
        }

    def undefine_interface(self, uri: str, iface_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            iface = conn.interfaceLookupByName(iface_name)
            iface.undefine()
        except Exception as exc:
            raise MCPError(
                code="INTERFACE_UNDEFINE_FAILED",
                message=f"Failed to undefine interface '{iface_name}'",
                retryable=False,
                details={"iface_name": iface_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iface_name": iface_name,
            "status": "undefined",
        }

    # ------------------------------------------------------------------
    # Network filters
    # ------------------------------------------------------------------

    def list_nwfilters(self, uri: str) -> list[dict[str, Any]]:
        conn = self._connect(uri)
        try:
            filters = conn.listAllNWFilters(0)
        except Exception as exc:
            raise MCPError(
                code="NWFILTER_LIST_FAILED",
                message="Failed to list nwfilters",
                retryable=False,
                details={"source": "libvirt", "cause": str(exc)},
            )
        out: list[dict[str, Any]] = []
        for f in filters:
            try:
                out.append({"source": "libvirt", "name": f.name(), "uuid": f.UUIDString()})
            except Exception:
                continue
        return out

    def get_nwfilter(self, uri: str, filter_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            f = conn.nwfilterLookupByName(filter_name)
        except Exception as exc:
            raise MCPError(
                code="NWFILTER_NOT_FOUND",
                message=f"NWFilter '{filter_name}' was not found",
                retryable=False,
                details={"filter_name": filter_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "name": f.name(),
            "uuid": f.UUIDString(),
            "xml": f.XMLDesc(0),
        }

    def define_nwfilter_xml(self, uri: str, filter_xml: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            f = conn.nwfilterDefineXML(filter_xml)
        except Exception as exc:
            raise MCPError(
                code="INVALID_NWFILTER_XML",
                message="Failed to define nwfilter from XML",
                retryable=False,
                details={"source": "libvirt", "cause": str(exc)},
            )
        if f is None:
            raise MCPError(
                code="INVALID_NWFILTER_XML",
                message="libvirt did not return a filter after nwfilterDefineXML",
                retryable=False,
                details={"source": "libvirt"},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "filter_name": f.name(),
            "status": "defined",
        }

    def undefine_nwfilter(self, uri: str, filter_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            f = conn.nwfilterLookupByName(filter_name)
            f.undefine()
        except Exception as exc:
            raise MCPError(
                code="NWFILTER_UNDEFINE_FAILED",
                message=f"Failed to undefine nwfilter '{filter_name}'",
                retryable=False,
                details={"filter_name": filter_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "filter_name": filter_name,
            "status": "undefined",
        }

    # ------------------------------------------------------------------
    # Network DHCP leases
    # ------------------------------------------------------------------

    def get_network_dhcp_leases(self, uri: str, network_name: str) -> list[dict[str, Any]]:
        conn = self._connect(uri)
        try:
            net = conn.networkLookupByName(network_name)
        except Exception as exc:
            raise MCPError(
                code="NETWORK_NOT_FOUND",
                message=f"Network '{network_name}' was not found",
                retryable=False,
                details={"network_name": network_name, "source": "libvirt", "cause": str(exc)},
            )
        try:
            leases = net.DHCPLeases() if hasattr(net, "DHCPLeases") else []
        except Exception as exc:
            raise MCPError(
                code="DHCP_LEASES_FAILED",
                message=f"Failed to get DHCP leases for network '{network_name}'",
                retryable=False,
                details={"network_name": network_name, "source": "libvirt", "cause": str(exc)},
            )
        return [dict(lease) for lease in (leases or [])]

    # ------------------------------------------------------------------
    # Network autostart
    # ------------------------------------------------------------------

    def set_network_autostart(self, uri: str, network_name: str, autostart: bool) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            net = conn.networkLookupByName(network_name)
            net.setAutostart(1 if autostart else 0)
        except Exception as exc:
            raise MCPError(
                code="NETWORK_AUTOSTART_FAILED",
                message=f"Failed to set autostart for network '{network_name}'",
                retryable=False,
                details={"network_name": network_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "network_name": network_name,
            "autostart": autostart,
        }

    # ------------------------------------------------------------------
    # Block jobs
    # ------------------------------------------------------------------

    def block_pull(self, uri: str, domain_ref: str, disk: str, bandwidth: int = 0) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            dom.blockPull(disk, bandwidth, 0)
        except Exception as exc:
            raise MCPError(
                code="BLOCK_PULL_FAILED",
                message=f"Failed to start block pull for domain '{domain_ref}' disk '{disk}'",
                retryable=False,
                details={"domain_ref": domain_ref, "disk": disk, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "disk": disk,
            "status": "pull_started",
        }

    def block_commit(self, uri: str, domain_ref: str, disk: str, base: str | None = None, top: str | None = None, bandwidth: int = 0) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            dom.blockCommit(disk, base, top, bandwidth, 0)
        except Exception as exc:
            raise MCPError(
                code="BLOCK_COMMIT_FAILED",
                message=f"Failed to start block commit for domain '{domain_ref}' disk '{disk}'",
                retryable=False,
                details={"domain_ref": domain_ref, "disk": disk, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "disk": disk,
            "status": "commit_started",
        }

    def block_job_abort(self, uri: str, domain_ref: str, disk: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            dom.blockJobAbort(disk, 0)
        except Exception as exc:
            raise MCPError(
                code="BLOCK_JOB_ABORT_FAILED",
                message=f"Failed to abort block job for domain '{domain_ref}' disk '{disk}'",
                retryable=False,
                details={"domain_ref": domain_ref, "disk": disk, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "disk": disk,
            "status": "aborted",
        }

    def block_job_info(self, uri: str, domain_ref: str, disk: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            info = dom.blockJobInfo(disk, 0)
        except Exception as exc:
            raise MCPError(
                code="BLOCK_JOB_INFO_FAILED",
                message=f"Failed to get block job info for domain '{domain_ref}' disk '{disk}'",
                retryable=False,
                details={"domain_ref": domain_ref, "disk": disk, "source": "libvirt", "cause": str(exc)},
            )
        if not info:
            return {
                "source": "libvirt",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "domain_ref": domain_ref,
                "disk": disk,
                "status": "no_job",
            }
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "disk": disk,
            "status": "active",
            "job_info": dict(info),
        }

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------

    def list_domain_checkpoints(self, uri: str, domain_ref: str) -> list[dict[str, Any]]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            if not hasattr(dom, "listAllCheckpoints"):
                return []
            checkpoints = dom.listAllCheckpoints(0)
        except Exception as exc:
            raise MCPError(
                code="CHECKPOINT_LIST_FAILED",
                message=f"Failed to list checkpoints for domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "source": "libvirt", "cause": str(exc)},
            )
        out: list[dict[str, Any]] = []
        for cp in checkpoints:
            try:
                out.append({"source": "libvirt", "name": cp.getName(), "xml": cp.getXMLDesc(0)})
            except Exception:
                continue
        return out

    def create_domain_checkpoint(self, uri: str, domain_ref: str, checkpoint_xml: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            cp = dom.checkpointCreateXML(checkpoint_xml, 0)
        except Exception as exc:
            raise MCPError(
                code="CHECKPOINT_CREATE_FAILED",
                message=f"Failed to create checkpoint for domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "checkpoint_name": cp.getName() if cp is not None else None,
            "status": "created",
        }

    def delete_domain_checkpoint(self, uri: str, domain_ref: str, checkpoint_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            cp = dom.checkpointLookupByName(checkpoint_name, 0)
        except Exception as exc:
            raise MCPError(
                code="CHECKPOINT_NOT_FOUND",
                message=f"Checkpoint '{checkpoint_name}' was not found for domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "checkpoint_name": checkpoint_name, "source": "libvirt", "cause": str(exc)},
            )
        try:
            cp.delete(0)
        except Exception as exc:
            raise MCPError(
                code="CHECKPOINT_DELETE_FAILED",
                message=f"Failed to delete checkpoint '{checkpoint_name}' for domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "checkpoint_name": checkpoint_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "checkpoint_name": checkpoint_name,
            "status": "deleted",
        }

    # ------------------------------------------------------------------
    # Storage volume clone
    # ------------------------------------------------------------------

    def clone_storage_volume(self, uri: str, pool_name: str, volume_name: str, src_pool_name: str, src_volume_name: str, volume_xml: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            src_pool = conn.storagePoolLookupByName(src_pool_name)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_POOL_NOT_FOUND",
                message=f"Source storage pool '{src_pool_name}' was not found",
                retryable=False,
                details={"pool_name": src_pool_name, "source": "libvirt", "cause": str(exc)},
            )
        try:
            src_vol = src_pool.storageVolLookupByName(src_volume_name)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_VOLUME_NOT_FOUND",
                message=f"Source volume '{src_volume_name}' was not found in pool '{src_pool_name}'",
                retryable=False,
                details={"pool_name": src_pool_name, "volume_name": src_volume_name, "source": "libvirt", "cause": str(exc)},
            )
        try:
            dest_pool = conn.storagePoolLookupByName(pool_name)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_POOL_NOT_FOUND",
                message=f"Destination storage pool '{pool_name}' was not found",
                retryable=False,
                details={"pool_name": pool_name, "source": "libvirt", "cause": str(exc)},
            )
        try:
            if hasattr(dest_pool, "storageVolCreateXMLFrom"):
                vol = dest_pool.storageVolCreateXMLFrom(volume_xml, src_vol, 0)
            else:
                vol = dest_pool.createXMLFrom(volume_xml, src_vol, 0)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_VOLUME_CLONE_FAILED",
                message=f"Failed to clone volume '{src_volume_name}' to '{volume_name}'",
                retryable=False,
                details={"pool_name": pool_name, "volume_name": volume_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool_name": pool_name,
            "volume_name": vol.name(),
            "src_pool_name": src_pool_name,
            "src_volume_name": src_volume_name,
            "status": "cloned",
        }

    # ------------------------------------------------------------------
    # Storage pool autostart and refresh
    # ------------------------------------------------------------------

    def set_storage_pool_autostart(self, uri: str, pool_name: str, autostart: bool) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolLookupByName(pool_name)
            pool.setAutostart(1 if autostart else 0)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_POOL_AUTOSTART_FAILED",
                message=f"Failed to set autostart for storage pool '{pool_name}'",
                retryable=False,
                details={"pool_name": pool_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool_name": pool_name,
            "autostart": autostart,
        }

    def refresh_storage_pool(self, uri: str, pool_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolLookupByName(pool_name)
            pool.refresh(0)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_POOL_REFRESH_FAILED",
                message=f"Failed to refresh storage pool '{pool_name}'",
                retryable=False,
                details={"pool_name": pool_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool_name": pool_name,
            "status": "refreshed",
        }

    # ------------------------------------------------------------------
    # Domain capabilities
    # ------------------------------------------------------------------

    def get_domain_capabilities(
        self,
        uri: str,
        emulatorbin: str | None = None,
        arch: str | None = None,
        machine: str | None = None,
        virttype: str | None = None,
    ) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            xml = conn.getDomainCapabilities(emulatorbin, arch, machine, virttype, 0)
        except Exception as exc:
            raise MCPError(
                code="DOMAIN_CAPABILITIES_FAILED",
                message="Failed to get domain capabilities",
                retryable=False,
                details={"source": "libvirt", "cause": str(exc)},
            )
        summary = self._parse_domain_capabilities_xml(xml)
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "xml": xml,
            "summary": summary,
        }

    def _parse_domain_capabilities_xml(self, xml: str) -> dict[str, Any]:
        try:
            root = ET.fromstring(xml)
        except Exception:
            return {}
        arch = root.findtext("arch") or root.get("arch")
        machine = root.findtext("machine") or root.get("machine")
        domain = root.findtext("domain") or root.get("domain")
        return {"arch": arch, "machine": machine, "domain": domain}

    # ------------------------------------------------------------------
    # Domain vCPU and memory tuning
    # ------------------------------------------------------------------

    def set_vcpus(self, uri: str, domain_ref: str, vcpu_count: int, flags: int = 0) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            dom.setVcpusFlags(vcpu_count, flags)
        except Exception as exc:
            raise MCPError(
                code="VCPU_SET_FAILED",
                message=f"Failed to set vCPUs for domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "vcpu_count": vcpu_count, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "vcpu_count": vcpu_count,
            "status": "applied",
        }

    def set_memory(self, uri: str, domain_ref: str, memory_kb: int, flags: int = 0) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            dom.setMemoryFlags(memory_kb, flags)
        except Exception as exc:
            raise MCPError(
                code="MEMORY_SET_FAILED",
                message=f"Failed to set memory for domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "memory_kb": memory_kb, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "memory_kb": memory_kb,
            "status": "applied",
        }

    # ------------------------------------------------------------------
    # Domain statistics
    # ------------------------------------------------------------------

    def get_domain_stats(self, uri: str, domain_ref: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        block_stats: dict[str, Any] = {}
        interface_stats: dict[str, Any] = {}
        memory_stats: dict[str, Any] = {}
        cpu_stats: dict[str, Any] = {}
        try:
            bs = dom.blockStats(None)
            block_stats = {
                "rd_requests": bs[0], "rd_bytes": bs[1],
                "wr_requests": bs[2], "wr_bytes": bs[3], "errors": bs[4],
            }
        except Exception:
            pass
        try:
            is_ = dom.interfaceStats(None)
            interface_stats = {
                "rx_bytes": is_[0], "rx_packets": is_[1], "rx_errors": is_[2], "rx_drop": is_[3],
                "tx_bytes": is_[4], "tx_packets": is_[5], "tx_errors": is_[6], "tx_drop": is_[7],
            }
        except Exception:
            pass
        try:
            memory_stats = dom.memoryStats()
        except Exception:
            pass
        try:
            cs = dom.getCPUStats(True, 0)
            cpu_stats = cs[0] if cs else {}
        except Exception:
            pass
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "block_stats": block_stats,
            "interface_stats": interface_stats,
            "memory_stats": memory_stats,
            "cpu_stats": cpu_stats,
        }

    def get_domain_block_stats(self, uri: str, domain_ref: str, disk: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            bs = dom.blockStats(disk)
        except Exception as exc:
            raise MCPError(
                code="BLOCK_STATS_FAILED",
                message=f"Failed to get block stats for disk '{disk}' on domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "disk": disk, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "disk": disk,
            "rd_requests": bs[0],
            "rd_bytes": bs[1],
            "wr_requests": bs[2],
            "wr_bytes": bs[3],
            "errors": bs[4],
        }

    def get_domain_interface_stats(self, uri: str, domain_ref: str, interface: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            is_ = dom.interfaceStats(interface)
        except Exception as exc:
            raise MCPError(
                code="INTERFACE_STATS_FAILED",
                message=f"Failed to get interface stats for '{interface}' on domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "interface": interface, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "interface": interface,
            "rx_bytes": is_[0],
            "rx_packets": is_[1],
            "rx_errors": is_[2],
            "rx_drop": is_[3],
            "tx_bytes": is_[4],
            "tx_packets": is_[5],
            "tx_errors": is_[6],
            "tx_drop": is_[7],
        }

    def get_domain_memory_stats(self, uri: str, domain_ref: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            raw = dom.memoryStats()
            stats = {str(k): v for k, v in raw.items()}
        except Exception as exc:
            raise MCPError(
                code="MEMORY_STATS_FAILED",
                message=f"Failed to get memory stats for domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "stats": stats,
        }

    # ------------------------------------------------------------------
    # CPU pinning
    # ------------------------------------------------------------------

    def get_domain_vcpu_pin_info(self, uri: str, domain_ref: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            result = dom.vcpuPinInfo(0)
            pinmaps = [ba.hex() for ba in result]
            return {
                "source": "libvirt",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "domain_ref": domain_ref,
                "vcpu_count": len(result),
                "pinmaps": pinmaps,
            }
        except Exception as exc:
            return {
                "source": "libvirt",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "domain_ref": domain_ref,
                "vcpu_count": 0,
                "pinmaps": [],
                "error": str(exc),
            }

    def set_domain_vcpu_pin(self, uri: str, domain_ref: str, vcpu: int, cpumap: list[int]) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            flags = 3  # VIR_DOMAIN_VCPU_LIVE | VIR_DOMAIN_VCPU_CONFIG
            if libvirt is not None and hasattr(libvirt, "VIR_DOMAIN_VCPU_LIVE"):
                flags = libvirt.VIR_DOMAIN_VCPU_LIVE | libvirt.VIR_DOMAIN_VCPU_CONFIG
            dom.pinVcpuFlags(vcpu, bytearray(cpumap), flags)
        except Exception as exc:
            raise MCPError(
                code="VCPU_PIN_FAILED",
                message=f"Failed to pin vCPU {vcpu} for domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "vcpu": vcpu, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "vcpu": vcpu,
            "status": "pinned",
        }

    def get_domain_emulator_pin_info(self, uri: str, domain_ref: str) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            result = dom.emulatorPinInfo(0)
            return {
                "source": "libvirt",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "domain_ref": domain_ref,
                "pinmap": result.hex() if isinstance(result, (bytes, bytearray)) else str(result),
            }
        except Exception as exc:
            return {
                "source": "libvirt",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "domain_ref": domain_ref,
                "pinmap": None,
                "error": str(exc),
            }

    def set_domain_emulator_pin(self, uri: str, domain_ref: str, cpumap: list[int]) -> dict[str, Any]:
        conn = self._connect(uri)
        dom = self._lookup_domain(conn, domain_ref)
        try:
            dom.pinEmulator(bytearray(cpumap), 3)
        except Exception as exc:
            raise MCPError(
                code="EMULATOR_PIN_FAILED",
                message=f"Failed to pin emulator for domain '{domain_ref}'",
                retryable=False,
                details={"domain_ref": domain_ref, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "status": "pinned",
        }

    # ------------------------------------------------------------------
    # Storage volume resize and wipe
    # ------------------------------------------------------------------

    def resize_storage_volume(self, uri: str, pool_name: str, volume_name: str, capacity_bytes: int) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolLookupByName(pool_name)
            vol = pool.storageVolLookupByName(volume_name)
            vol.resize(capacity_bytes, 0)
        except MCPError:
            raise
        except Exception as exc:
            raise MCPError(
                code="STORAGE_VOLUME_RESIZE_FAILED",
                message=f"Failed to resize volume '{volume_name}' in pool '{pool_name}'",
                retryable=False,
                details={"pool_name": pool_name, "volume_name": volume_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool_name": pool_name,
            "volume_name": volume_name,
            "capacity_bytes": capacity_bytes,
            "status": "resized",
        }

    def wipe_storage_volume(self, uri: str, pool_name: str, volume_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolLookupByName(pool_name)
            vol = pool.storageVolLookupByName(volume_name)
            vol.wipe(0)
        except MCPError:
            raise
        except Exception as exc:
            raise MCPError(
                code="STORAGE_VOLUME_WIPE_FAILED",
                message=f"Failed to wipe volume '{volume_name}' in pool '{pool_name}'",
                retryable=False,
                details={"pool_name": pool_name, "volume_name": volume_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool_name": pool_name,
            "volume_name": volume_name,
            "status": "wiped",
        }

    def build_storage_pool(self, uri: str, pool_name: str) -> dict[str, Any]:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolLookupByName(pool_name)
            pool.build(0)
        except MCPError:
            raise
        except Exception as exc:
            raise MCPError(
                code="STORAGE_POOL_BUILD_FAILED",
                message=f"Failed to build storage pool '{pool_name}'",
                retryable=False,
                details={"pool_name": pool_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool_name": pool_name,
            "status": "built",
        }


    # ------------------------------------------------------------------
    # Storage volume XML and backing chain
    # ------------------------------------------------------------------

    def get_volume_xml(self, uri: str, pool_name: str, volume_name: str) -> dict:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolLookupByName(pool_name)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_POOL_NOT_FOUND",
                message=f"Storage pool '{pool_name}' was not found",
                retryable=False,
                details={"pool_name": pool_name, "source": "libvirt", "cause": str(exc)},
            )
        try:
            vol = pool.storageVolLookupByName(volume_name)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_VOLUME_NOT_FOUND",
                message=f"Storage volume '{volume_name}' was not found in pool '{pool_name}'",
                retryable=False,
                details={"pool_name": pool_name, "volume_name": volume_name, "source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool_name": pool_name,
            "volume_name": volume_name,
            "xml": vol.XMLDesc(0),
        }

    def get_volume_backing_chain(self, uri: str, pool_name: str, volume_name: str) -> dict:
        conn = self._connect(uri)
        try:
            pool = conn.storagePoolLookupByName(pool_name)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_POOL_NOT_FOUND",
                message=f"Storage pool '{pool_name}' was not found",
                retryable=False,
                details={"pool_name": pool_name, "source": "libvirt", "cause": str(exc)},
            )
        try:
            vol = pool.storageVolLookupByName(volume_name)
        except Exception as exc:
            raise MCPError(
                code="STORAGE_VOLUME_NOT_FOUND",
                message=f"Storage volume '{volume_name}' was not found in pool '{pool_name}'",
                retryable=False,
                details={"pool_name": pool_name, "volume_name": volume_name, "source": "libvirt", "cause": str(exc)},
            )

        chain: list[dict] = []

        def _parse_vol(v: Any, depth: int, pname: str, vname: str) -> None:
            try:
                xml = v.XMLDesc(0)
                root = ET.fromstring(xml)
            except Exception:
                chain.append({"depth": depth, "pool": pname, "name": vname, "resolved": False})
                return
            target_path = None
            target = root.find("target")
            if target is not None:
                path_el = target.find("path")
                if path_el is not None and path_el.text:
                    target_path = path_el.text.strip()
            fmt_el = None
            if target is not None:
                fmt_el = target.find("format")
            fmt = fmt_el.get("type") if fmt_el is not None else None
            chain.append({
                "depth": depth,
                "pool": pname,
                "name": vname,
                "path": target_path,
                "format": fmt,
                "resolved": True,
            })
            # Follow backingStore
            bs = root.find("backingStore")
            if bs is None:
                return
            bs_path_el = bs.find("path")
            if bs_path_el is None or not bs_path_el.text:
                return
            bs_path = bs_path_el.text.strip()
            try:
                backing_vol = conn.storageVolLookupByPath(bs_path)
                backing_pool_name = None
                try:
                    bpool_xml = backing_vol.storagePoolLookupByVolume().name() if hasattr(backing_vol, "storagePoolLookupByVolume") else None
                    backing_pool_name = bpool_xml
                except Exception:
                    pass
                _parse_vol(backing_vol, depth + 1, backing_pool_name or "unknown", backing_vol.name())
            except Exception:
                bs_fmt_el = bs.find("format")
                bs_fmt = bs_fmt_el.get("type") if bs_fmt_el is not None else None
                chain.append({"depth": depth + 1, "path": bs_path, "format": bs_fmt, "resolved": False})

        _parse_vol(vol, 0, pool_name, volume_name)
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool_name": pool_name,
            "volume_name": volume_name,
            "chain_depth": len(chain),
            "chain": chain,
        }

    # ------------------------------------------------------------------
    # Secrets
    # ------------------------------------------------------------------

    def list_secrets(self, uri: str) -> list:
        conn = self._connect(uri)
        try:
            secrets = conn.listAllSecrets()
        except Exception as exc:
            raise MCPError(
                code="SECRET_LIST_FAILED",
                message="Failed to list secrets",
                retryable=False,
                details={"source": "libvirt", "cause": str(exc)},
            )
        _usage_type_map = {0: "none", 1: "volume", 2: "ceph", 3: "iscsi", 4: "tls", 5: "vtpm"}
        out = []
        for s in secrets:
            usage_type_int = s.usageType() if hasattr(s, "usageType") else 0
            out.append({
                "source": "libvirt",
                "uuid": s.UUIDString(),
                "usage_type": _usage_type_map.get(usage_type_int, "unknown"),
                "usage_id": s.usageID() if hasattr(s, "usageID") else None,
            })
        return out

    def get_secret(self, uri: str, secret_ref: str) -> dict:
        conn = self._connect(uri)
        s = self._lookup_secret(conn, secret_ref)
        _usage_type_map = {0: "none", 1: "volume", 2: "ceph", 3: "iscsi", 4: "tls", 5: "vtpm"}
        usage_type_int = s.usageType() if hasattr(s, "usageType") else 0
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uuid": s.UUIDString(),
            "usage_type": _usage_type_map.get(usage_type_int, "unknown"),
            "usage_id": s.usageID() if hasattr(s, "usageID") else None,
            "xml": s.XMLDesc(0),
        }

    def define_secret_xml(self, uri: str, secret_xml: str) -> dict:
        conn = self._connect(uri)
        try:
            s = conn.secretDefineXML(secret_xml, 0)
        except Exception as exc:
            raise MCPError(
                code="INVALID_SECRET_XML",
                message="Failed to define secret from XML",
                retryable=False,
                details={"source": "libvirt", "cause": str(exc)},
            )
        if s is None:
            raise MCPError(
                code="INVALID_SECRET_XML",
                message="libvirt did not return a secret after secretDefineXML",
                retryable=False,
                details={"source": "libvirt"},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uuid": s.UUIDString(),
            "status": "defined",
        }

    def set_secret_value(self, uri: str, secret_ref: str, value_bytes: bytes) -> dict:
        conn = self._connect(uri)
        s = self._lookup_secret(conn, secret_ref)
        try:
            s.setValue(value_bytes)
        except Exception as exc:
            raise MCPError(
                code="SECRET_SET_VALUE_FAILED",
                message=f"Failed to set value for secret '{secret_ref}'",
                retryable=False,
                details={"source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uuid": s.UUIDString(),
            "status": "value_set",
        }

    def get_secret_value(self, uri: str, secret_ref: str) -> dict:
        import base64
        conn = self._connect(uri)
        s = self._lookup_secret(conn, secret_ref)
        try:
            value_bytes = s.value()
        except Exception as exc:
            raise MCPError(
                code="SECRET_GET_VALUE_FAILED",
                message=f"Failed to get value for secret '{secret_ref}'",
                retryable=False,
                details={"source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uuid": s.UUIDString(),
            "value_b64": base64.b64encode(value_bytes).decode("ascii") if value_bytes else None,
        }

    def undefine_secret(self, uri: str, secret_ref: str) -> dict:
        conn = self._connect(uri)
        s = self._lookup_secret(conn, secret_ref)
        try:
            s.undefine()
        except Exception as exc:
            raise MCPError(
                code="SECRET_UNDEFINE_FAILED",
                message=f"Failed to undefine secret '{secret_ref}'",
                retryable=False,
                details={"source": "libvirt", "cause": str(exc)},
            )
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uuid": secret_ref,
            "status": "undefined",
        }

    def _lookup_secret(self, conn: Any, secret_ref: str) -> Any:
        try:
            return conn.secretLookupByUUIDString(secret_ref)
        except Exception as exc:
            raise MCPError(
                code="SECRET_NOT_FOUND",
                message=f"Secret '{secret_ref}' was not found",
                retryable=False,
                details={"secret_ref": secret_ref, "source": "libvirt", "cause": str(exc)},
            )

    def _lookup_domain(self, conn: Any, domain_ref: str) -> Any:
        try:
            try:
                return conn.lookupByUUIDString(domain_ref)
            except Exception:
                return conn.lookupByName(domain_ref)
        except Exception as exc:
            raise MCPError(
                code="DOMAIN_NOT_FOUND",
                message=f"Domain '{domain_ref}' was not found",
                retryable=False,
                details={"domain_ref": domain_ref, "source": "libvirt", "cause": str(exc)},
            )

    def _domain_summary(self, dom: Any) -> dict[str, Any]:
        info = dom.info()
        state = _LIBVIRT_STATE.get(int(info[0]), "unknown")

        try:
            autostart = bool(dom.autostart())
        except Exception:
            autostart = False

        return {
            "source": "libvirt",
            "name": dom.name(),
            "uuid": dom.UUIDString(),
            "state": state,
            "is_active": bool(dom.isActive()),
            "memory_kb": int(info[2]),
            "max_memory_kb": int(info[1]),
            "vcpu_count": int(info[3]),
            "cpu_time_ns": int(info[4]),
            "autostart": autostart,
        }

    def _summarize_capabilities(self, capabilities_xml: str) -> dict[str, Any]:
        try:
            root = ET.fromstring(capabilities_xml)
        except Exception:
            return {"parse_error": "invalid_capabilities_xml"}

        arches: list[str] = []
        domain_types: set[str] = set()
        machine_samples: dict[str, list[str]] = {}
        machine_counts: dict[str, int] = {}

        for guest in root.findall("guest"):
            arch_node = guest.find("arch")
            if arch_node is None:
                continue

            arch_name = arch_node.get("name")
            if not arch_name:
                continue

            if arch_name not in arches:
                arches.append(arch_name)

            machine_nodes = arch_node.findall("machine")
            machine_counts[arch_name] = len(machine_nodes)

            seen: set[str] = set()
            samples: list[str] = []
            for machine in machine_nodes:
                name = (machine.text or "").strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                samples.append(name)
                if len(samples) >= 15:
                    break
            machine_samples[arch_name] = samples

            for domain in arch_node.findall("domain"):
                dtype = domain.get("type")
                if dtype:
                    domain_types.add(dtype)

        return {
            "guest_arches": arches,
            "guest_arch_count": len(arches),
            "domain_types": sorted(domain_types),
            "machine_counts_by_arch": machine_counts,
            "machine_samples_by_arch": machine_samples,
        }
