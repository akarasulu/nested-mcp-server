#!/usr/bin/env bash
set -euo pipefail

# Safe local integration runner for nested-mcp-server.
# Provisions mcp_test_* resources, runs both integration suites, and optionally tears down.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x scripts/mcp_test_setup.sh ]]; then
  echo "Error: scripts/mcp_test_setup.sh is missing or not executable" >&2
  exit 1
fi

if [[ ! -x scripts/mcp_test_teardown.sh ]]; then
  echo "Error: scripts/mcp_test_teardown.sh is missing or not executable" >&2
  exit 1
fi

TEST_PREFIX="${LIBVIRT_MCP_TEST_PREFIX:-mcp_test_}"
TEST_DOMAIN="${LIBVIRT_MCP_TEST_DOMAIN:-${LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN:-${TEST_PREFIX}dummy}}"
TEST_NETWORK="${LIBVIRT_MCP_TEST_NETWORK:-${TEST_PREFIX}network}"

if [[ ! "$TEST_DOMAIN" =~ ^mcp_test_ ]]; then
  echo "Refusing to run: test domain must start with mcp_test_ (got '$TEST_DOMAIN')" >&2
  exit 2
fi
if [[ ! "$TEST_NETWORK" =~ ^mcp_test_ ]]; then
  echo "Refusing to run: test network must start with mcp_test_ (got '$TEST_NETWORK')" >&2
  exit 2
fi

# Integration test gates and safe policy defaults.
export LIBVIRT_MCP_RUN_INTEGRATION=1
export LIBVIRT_MCP_TEST_PREFIX="$TEST_PREFIX"
export LIBVIRT_MCP_TEST_DOMAIN="$TEST_DOMAIN"
export LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN="$TEST_DOMAIN"
export LIBVIRT_MCP_TEST_NETWORK="$TEST_NETWORK"

export MCP_LIBVIRT_ALLOW_MUTATIONS="${MCP_LIBVIRT_ALLOW_MUTATIONS:-true}"
export MCP_LIBVIRT_MUTATION_DOMAIN_ALLOWLIST="${MCP_LIBVIRT_MUTATION_DOMAIN_ALLOWLIST:-$TEST_DOMAIN}"
export MCP_LIBVIRT_ALLOW_DESTRUCTIVE="${MCP_LIBVIRT_ALLOW_DESTRUCTIVE:-false}"
export MCP_LIBVIRT_DESTRUCTIVE_DOMAIN_ALLOWLIST="${MCP_LIBVIRT_DESTRUCTIVE_DOMAIN_ALLOWLIST:-$TEST_DOMAIN}"

AUTO_TEARDOWN="${LIBVIRT_MCP_AUTO_TEARDOWN:-1}"

echo "==> Provisioning test sandbox"
scripts/mcp_test_setup.sh

echo "==> Running integration suites"
.venv/bin/python -m pytest \
  tests/test_integration_local_hypervisor.py \
  tests/test_integration_runtime_paths.py \
  -q

if [[ "$AUTO_TEARDOWN" == "1" ]]; then
  echo "==> Tearing down test sandbox"
  scripts/mcp_test_teardown.sh
else
  echo "Auto teardown disabled (LIBVIRT_MCP_AUTO_TEARDOWN=$AUTO_TEARDOWN)."
  echo "Run scripts/mcp_test_teardown.sh when done."
fi

echo "Integration run complete."
