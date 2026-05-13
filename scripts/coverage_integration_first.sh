#!/usr/bin/env bash
set -euo pipefail

# Runs integration coverage first to expose real hypervisor-path gaps before
# unit tests can inflate aggregate coverage.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
PYTEST_BASE=("$PYTHON_BIN" -m pytest tests/ --cov=src/libvirt_mcp_server)

if [[ "${LIBVIRT_MCP_RUN_INTEGRATION:-}" != "1" ]]; then
  echo "Error: set LIBVIRT_MCP_RUN_INTEGRATION=1"
  exit 2
fi

export LIBVIRT_MCP_TEST_DOMAIN="${LIBVIRT_MCP_TEST_DOMAIN:-${LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN:-}}"

if [[ -z "${LIBVIRT_MCP_TEST_DOMAIN}" ]]; then
  echo "Error: set LIBVIRT_MCP_TEST_DOMAIN (or LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN) to a dedicated test VM"
  exit 2
fi

echo "==> Integration-only coverage (baseline)"
"${PYTHON_BIN}" -m coverage erase
"${PYTEST_BASE[@]}" \
  -m integration \
  --cov-report=term-missing \
  --cov-report=xml:coverage.integration.xml \
  --cov-report=html:htmlcov-integration
cp .coverage .coverage.integration

echo "==> Unit-only append (combined report)"
"${PYTEST_BASE[@]}" \
  -m "not integration" \
  --cov-append \
  --cov-report=term-missing \
  --cov-report=xml:coverage.combined.xml \
  --cov-report=html:htmlcov-combined

echo
echo "Artifacts:"
echo "  integration data: .coverage.integration"
echo "  integration xml : coverage.integration.xml"
echo "  integration html: htmlcov-integration/"
echo "  combined xml    : coverage.combined.xml"
echo "  combined html   : htmlcov-combined/"
