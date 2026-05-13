#!/usr/bin/env bash
set -euo pipefail

# Teardown for the mcp_test sandbox created by mcp_test_setup.sh.

LIBVIRT_URI="${LIBVIRT_URI:-qemu:///system}"
TEST_PREFIX="${LIBVIRT_MCP_TEST_PREFIX:-mcp_test_}"
TEST_DOMAIN="${LIBVIRT_MCP_TEST_DOMAIN:-${LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN:-${TEST_PREFIX}dummy}}"
TEST_NETWORK="${LIBVIRT_MCP_TEST_NETWORK:-${TEST_PREFIX}network}"

VM_BASE_DIR="${LIBVIRT_MCP_TEST_VM_BASE_DIR:-$HOME/Local/Vms/KVM/deb13}"
VM_DIR="${LIBVIRT_MCP_TEST_VM_DIR:-$VM_BASE_DIR/$TEST_DOMAIN}"
DELETE_DISK="${LIBVIRT_MCP_TEST_DELETE_DISK:-0}"

if [[ ! "$TEST_DOMAIN" =~ ^mcp_test_ ]]; then
  echo "Refusing teardown: TEST_DOMAIN does not start with mcp_test_: '$TEST_DOMAIN'" >&2
  exit 2
fi
if [[ ! "$TEST_NETWORK" =~ ^mcp_test_ ]]; then
  echo "Refusing teardown: TEST_NETWORK does not start with mcp_test_: '$TEST_NETWORK'" >&2
  exit 2
fi

echo "==> Tearing down domain '$TEST_DOMAIN'"
virsh -c "$LIBVIRT_URI" destroy "$TEST_DOMAIN" >/dev/null 2>&1 || true
virsh -c "$LIBVIRT_URI" undefine "$TEST_DOMAIN" >/dev/null 2>&1 || true

echo "==> Tearing down network '$TEST_NETWORK'"
virsh -c "$LIBVIRT_URI" net-destroy "$TEST_NETWORK" >/dev/null 2>&1 || true
virsh -c "$LIBVIRT_URI" net-undefine "$TEST_NETWORK" >/dev/null 2>&1 || true

if [[ "$DELETE_DISK" == "1" ]]; then
  echo "==> Removing VM dir '$VM_DIR'"
  rm -rf "$VM_DIR"
else
  echo "Disk cleanup skipped (set LIBVIRT_MCP_TEST_DELETE_DISK=1 to remove '$VM_DIR')"
fi

echo "Teardown complete."
