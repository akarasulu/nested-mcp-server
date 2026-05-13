#!/usr/bin/env bash
set -euo pipefail

# Provision a dedicated libvirt test sandbox for MCP integration tests.
# This script is idempotent and intentionally scoped to mcp_test_* resources.

LIBVIRT_URI="${LIBVIRT_URI:-qemu:///system}"
TEST_PREFIX="${LIBVIRT_MCP_TEST_PREFIX:-mcp_test_}"
TEST_DOMAIN="${LIBVIRT_MCP_TEST_DOMAIN:-${LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN:-${TEST_PREFIX}dummy}}"
TEST_NETWORK="${LIBVIRT_MCP_TEST_NETWORK:-${TEST_PREFIX}network}"

VM_BASE_DIR="${LIBVIRT_MCP_TEST_VM_BASE_DIR:-$HOME/Local/Vms/KVM/deb13}"
VM_DIR="${LIBVIRT_MCP_TEST_VM_DIR:-$VM_BASE_DIR/$TEST_DOMAIN}"
VM_DISK_PATH="${LIBVIRT_MCP_TEST_VM_DISK_PATH:-$VM_DIR/vda.qcow2}"
VM_DISK_SIZE="${LIBVIRT_MCP_TEST_VM_DISK_SIZE:-2G}"
VM_USE_LINKED_CLONE="${LIBVIRT_MCP_TEST_VM_USE_LINKED_CLONE:-true}"
VM_PARENT_DISK_PATH="${LIBVIRT_MCP_TEST_VM_PARENT_DISK_PATH:-$VM_BASE_DIR/vda.qcow2}"
VM_RAM_MB="${LIBVIRT_MCP_TEST_VM_RAM_MB:-1024}"
VM_VCPUS="${LIBVIRT_MCP_TEST_VM_VCPUS:-2}"
VM_OS_VARIANT="${LIBVIRT_MCP_TEST_VM_OS_VARIANT:-generic}"

NET_BRIDGE="${LIBVIRT_MCP_TEST_NETWORK_BRIDGE:-virbr190}"
NET_CIDR="${LIBVIRT_MCP_TEST_NETWORK_CIDR:-192.168.190.0/24}"
NET_GW="${LIBVIRT_MCP_TEST_NETWORK_GW:-192.168.190.1}"
NET_DHCP_START="${LIBVIRT_MCP_TEST_NETWORK_DHCP_START:-192.168.190.100}"
NET_DHCP_END="${LIBVIRT_MCP_TEST_NETWORK_DHCP_END:-192.168.190.200}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command '$1' not found" >&2
    exit 1
  fi
}

if [[ ! "$TEST_DOMAIN" =~ ^mcp_test_ ]]; then
  echo "Error: test domain must start with mcp_test_ (got '$TEST_DOMAIN')" >&2
  exit 2
fi
if [[ ! "$TEST_NETWORK" =~ ^mcp_test_ ]]; then
  echo "Error: test network must start with mcp_test_ (got '$TEST_NETWORK')" >&2
  exit 2
fi

require_cmd virsh
require_cmd qemu-img

echo "==> Ensuring test network '$TEST_NETWORK' exists"
if ! virsh -c "$LIBVIRT_URI" net-info "$TEST_NETWORK" >/dev/null 2>&1; then
  net_xml="$(mktemp)"
  cat > "$net_xml" <<XML
<network>
  <name>${TEST_NETWORK}</name>
  <bridge name='${NET_BRIDGE}' stp='on' delay='0'/>
  <forward mode='nat'/>
  <ip address='${NET_GW}' netmask='255.255.255.0'>
    <dhcp>
      <range start='${NET_DHCP_START}' end='${NET_DHCP_END}'/>
    </dhcp>
  </ip>
</network>
XML
  virsh -c "$LIBVIRT_URI" net-define "$net_xml"
  rm -f "$net_xml"
else
  echo "Network already defined"
fi

virsh -c "$LIBVIRT_URI" net-autostart "$TEST_NETWORK" >/dev/null 2>&1 || true
virsh -c "$LIBVIRT_URI" net-start "$TEST_NETWORK" >/dev/null 2>&1 || true


echo "==> Ensuring test domain disk exists at '$VM_DISK_PATH'"
mkdir -p "$VM_DIR"
if [[ ! -f "$VM_DISK_PATH" ]]; then
  if [[ "${VM_USE_LINKED_CLONE,,}" == "true" ]] && [[ -f "$VM_PARENT_DISK_PATH" ]]; then
    if command -v realpath >/dev/null 2>&1; then
      backing_ref="$(realpath --relative-to="$VM_DIR" "$VM_PARENT_DISK_PATH")"
    else
      backing_ref="$VM_PARENT_DISK_PATH"
    fi
    echo "Creating linked-clone disk with backing file '$backing_ref'"
    qemu-img create -f qcow2 -F qcow2 -b "$backing_ref" "$VM_DISK_PATH" >/dev/null
  else
    if [[ "${VM_USE_LINKED_CLONE,,}" == "true" ]]; then
      echo "Warning: linked-clone requested but parent disk missing at '$VM_PARENT_DISK_PATH'; creating standalone qcow2" >&2
    fi
    qemu-img create -f qcow2 "$VM_DISK_PATH" "$VM_DISK_SIZE" >/dev/null
  fi
else
  echo "Disk already exists"
fi


echo "==> Ensuring test domain '$TEST_DOMAIN' is defined"
if ! virsh -c "$LIBVIRT_URI" dominfo "$TEST_DOMAIN" >/dev/null 2>&1; then
  domain_xml="$(mktemp)"
  cat > "$domain_xml" <<XML
<domain type='kvm'>
  <name>${TEST_DOMAIN}</name>
  <memory unit='MiB'>${VM_RAM_MB}</memory>
  <currentMemory unit='MiB'>${VM_RAM_MB}</currentMemory>
  <vcpu placement='static'>${VM_VCPUS}</vcpu>
  <os>
    <type arch='x86_64' machine='q35'>hvm</type>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
  </features>
  <cpu mode='host-model'/>
  <clock offset='utc'/>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='${VM_DISK_PATH}'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='network'>
      <source network='${TEST_NETWORK}'/>
      <model type='virtio'/>
    </interface>
    <graphics type='vnc' autoport='yes' listen='127.0.0.1'/>
    <console type='pty'/>
  </devices>
</domain>
XML
  virsh -c "$LIBVIRT_URI" define "$domain_xml"
  cp "$domain_xml" "$VM_DIR/definition.xml"
  rm -f "$domain_xml"
else
  echo "Domain already defined"
fi

echo
echo "MCP test sandbox is ready."
echo
cat <<ENV
Export these for integration testing:

  export LIBVIRT_MCP_RUN_INTEGRATION=1
  export LIBVIRT_MCP_TEST_PREFIX=${TEST_PREFIX}
  export LIBVIRT_MCP_TEST_DOMAIN=${TEST_DOMAIN}
  export LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN=${TEST_DOMAIN}
  export LIBVIRT_MCP_TEST_NETWORK=${TEST_NETWORK}
  export LIBVIRT_MCP_TEST_VM_USE_LINKED_CLONE=${VM_USE_LINKED_CLONE}
  export LIBVIRT_MCP_TEST_VM_PARENT_DISK_PATH=${VM_PARENT_DISK_PATH}

  export MCP_LIBVIRT_ALLOW_MUTATIONS=true
  export MCP_LIBVIRT_MUTATION_DOMAIN_ALLOWLIST=${TEST_DOMAIN}
  export MCP_LIBVIRT_ALLOW_DESTRUCTIVE=false
  export MCP_LIBVIRT_DESTRUCTIVE_DOMAIN_ALLOWLIST=${TEST_DOMAIN}

Optional coverage run:

  scripts/coverage_integration_first.sh
ENV
