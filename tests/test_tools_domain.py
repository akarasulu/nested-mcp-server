import pytest

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.errors import MCPError
from libvirt_mcp_server.tools import domain_tools


class FakeLibvirtAdapter:
    def __init__(self):
        self.last = None

    def list_domains(self, uri, **kwargs):
        self.last = (uri, kwargs)
        return [{"name": "vm-a", "is_active": True}]

    def lifecycle_action(self, uri, domain_ref, action):
        self.last = (uri, domain_ref, action)
        return {
            "source": "libvirt",
            "domain_ref": domain_ref,
            "action": action,
            "status": "requested",
        }

    def set_autostart(self, uri, domain_ref, autostart):
        self.last = (uri, domain_ref, autostart)
        return {
            "source": "libvirt",
            "domain_ref": domain_ref,
            "autostart": autostart,
        }

    def define_domain_xml(self, uri, domain_xml):
        self.last = (uri, domain_xml)
        return {"source": "libvirt", "status": "defined", "domain_name": "mcp_test_dummy"}

    def undefine_domain(self, uri, domain_ref):
        self.last = (uri, domain_ref)
        return {"source": "libvirt", "status": "undefined", "domain_ref": domain_ref}


@pytest.fixture
def config():
    return ServerConfig.from_env()


def test_list_domains_includes_total_count(config):
    adapter = FakeLibvirtAdapter()
    result = domain_tools.list_domains(
        config,
        adapter,
        active_only=True,
        inactive_only=False,
        name_prefix="vm",
        hypervisor_ref=None,
    )

    assert result["total_count"] == 1
    assert result["items"][0]["name"] == "vm-a"


def test_lifecycle_blocked_when_mutations_disabled(config):
    adapter = FakeLibvirtAdapter()

    with pytest.raises(MCPError) as exc:
        domain_tools.lifecycle_action(
            config,
            adapter,
            tool_name="start_domain",
            domain_ref="vm1",
            hypervisor_ref=None,
        )

    assert exc.value.code == "MUTATION_DISABLED"


def test_lifecycle_invalid_action_when_mutations_enabled(config):
    adapter = FakeLibvirtAdapter()
    config.allow_mutations = True

    with pytest.raises(MCPError) as exc:
        domain_tools.lifecycle_action(
            config,
            adapter,
            tool_name="not_a_real_action",
            domain_ref="vm1",
            hypervisor_ref=None,
        )

    assert exc.value.code == "INVALID_ACTION"


def test_lifecycle_dry_run_payload(config):
    adapter = FakeLibvirtAdapter()
    config.allow_mutations = True

    result = domain_tools.lifecycle_action(
        config,
        adapter,
        tool_name="start_domain",
        domain_ref="vm1",
        hypervisor_ref=None,
        dry_run=True,
    )

    assert result["source"] == "libvirt"
    assert result["dry_run"] is True
    assert result["status"] == "approved"
    assert result["action"] == "start_domain"
    assert result["domain_ref"] == "vm1"


def test_destroy_blocked_when_not_allowlisted(config):
    adapter = FakeLibvirtAdapter()
    config.allow_mutations = True
    config.allow_destructive = False
    config.destructive_domain_allowlist = {"mcp_test_dummy"}

    with pytest.raises(MCPError) as exc:
        domain_tools.lifecycle_action(
            config,
            adapter,
            tool_name="destroy_domain",
            domain_ref="some_other_vm",
            hypervisor_ref=None,
        )

    assert exc.value.code == "DESTRUCTIVE_DISABLED"


def test_destroy_allowed_when_domain_allowlisted(config):
    adapter = FakeLibvirtAdapter()
    config.allow_mutations = True
    config.allow_destructive = False
    config.destructive_domain_allowlist = {"mcp_test_dummy"}

    result = domain_tools.lifecycle_action(
        config,
        adapter,
        tool_name="destroy_domain",
        domain_ref="mcp_test_dummy",
        hypervisor_ref=None,
    )

    assert result["action"] == "destroy_domain"
    assert result["domain_ref"] == "mcp_test_dummy"
    assert result["dry_run"] is False


def test_mutation_blocked_when_domain_not_allowlisted(config):
    adapter = FakeLibvirtAdapter()
    config.allow_mutations = True
    config.mutation_domain_allowlist = {"mcp_test_dummy"}

    with pytest.raises(MCPError) as exc:
        domain_tools.lifecycle_action(
            config,
            adapter,
            tool_name="start_domain",
            domain_ref="deb13",
            hypervisor_ref=None,
        )

    assert exc.value.code == "MUTATION_DOMAIN_DENIED"


def test_set_autostart_blocked_when_domain_not_allowlisted(config):
    adapter = FakeLibvirtAdapter()
    config.allow_mutations = True
    config.mutation_domain_allowlist = {"mcp_test_dummy"}

    with pytest.raises(MCPError) as exc:
        domain_tools.set_domain_autostart(
            config,
            adapter,
            domain_ref="deb13",
            hypervisor_ref=None,
            autostart=True,
        )

    assert exc.value.code == "MUTATION_DOMAIN_DENIED"


def test_set_autostart_returns_payload_when_allowed(config):
    adapter = FakeLibvirtAdapter()
    config.allow_mutations = True
    config.mutation_domain_allowlist = {"mcp_test_dummy"}

    result = domain_tools.set_domain_autostart(
        config,
        adapter,
        domain_ref="mcp_test_dummy",
        hypervisor_ref=None,
        autostart=False,
    )

    assert result["domain_ref"] == "mcp_test_dummy"
    assert result["autostart"] is False
    assert result["hypervisor_ref"] == "default"


def test_define_domain_xml_requires_test_prefix(config):
    adapter = FakeLibvirtAdapter()
    config.allow_mutations = True
    config.allow_define = True
    config.test_resource_prefix = "mcp_test_"

    xml = """
<domain type='kvm'>
  <name>prod_vm</name>
</domain>
"""

    with pytest.raises(MCPError) as exc:
        domain_tools.define_domain_xml(
            config,
            adapter,
            domain_xml=xml,
            hypervisor_ref=None,
        )

    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_define_domain_xml_allowed_for_test_prefix(config):
    adapter = FakeLibvirtAdapter()
    config.allow_mutations = True
    config.allow_define = True
    config.test_resource_prefix = "mcp_test_"

    xml = """
<domain type='kvm'>
  <name>mcp_test_dummy</name>
</domain>
"""

    result = domain_tools.define_domain_xml(
        config,
        adapter,
        domain_xml=xml,
        hypervisor_ref=None,
    )

    assert result["status"] == "defined"


def test_undefine_domain_requires_test_prefix(config):
    adapter = FakeLibvirtAdapter()
    config.allow_mutations = True
    config.test_resource_prefix = "mcp_test_"

    with pytest.raises(MCPError) as exc:
        domain_tools.undefine_domain(
            config,
            adapter,
            domain_ref="prod-vm",
            hypervisor_ref=None,
        )

    assert exc.value.code == "TEST_PREFIX_REQUIRED"
