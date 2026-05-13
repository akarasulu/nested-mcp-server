from libvirt_mcp_server.config import ServerConfig


def test_config_parses_named_hypervisors(monkeypatch):
    monkeypatch.setenv("LIBVIRT_URIS", "default=qemu:///system,edge=qemu+ssh://root@edge/system")
    monkeypatch.setenv("MCP_QMP_ALLOWLIST", "query-status,query-version,*")

    cfg = ServerConfig.from_env()

    assert cfg.hypervisors["default"] == "qemu:///system"
    assert cfg.hypervisors["edge"] == "qemu+ssh://root@edge/system"
    assert "*" in cfg.qmp_allowlist


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("LIBVIRT_URIS", raising=False)
    monkeypatch.delenv("LIBVIRT_URI", raising=False)

    cfg = ServerConfig.from_env()

    assert cfg.libvirt_uri == "qemu:///system"
    assert cfg.hypervisors["default"] == "qemu:///system"
    assert cfg.allow_mutations is False
    assert cfg.mutation_domain_allowlist == set()
    assert cfg.allow_destructive is False
    assert cfg.destructive_domain_allowlist == set()
    assert cfg.allow_qmp is True
    assert "blockdev-backup" in cfg.qmp_mutation_allowlist
    assert "nbd-server-start" in cfg.qmp_mutation_allowlist
    assert cfg.qmp_event_retention_days == 30
    assert cfg.qmp_event_retention_max_records == 100000
    assert cfg.actor_policy_enabled() is False
    assert cfg.is_tool_allowed_for_actor("unknown", "destroy_domain") is True


def test_config_parses_destructive_domain_allowlist(monkeypatch):
    monkeypatch.setenv("MCP_LIBVIRT_DESTRUCTIVE_DOMAIN_ALLOWLIST", "mcp_test_dummy,mcp_test_other")

    cfg = ServerConfig.from_env()

    assert cfg.destructive_domain_allowlist == {"mcp_test_dummy", "mcp_test_other"}


def test_config_parses_mutation_domain_allowlist(monkeypatch):
    monkeypatch.setenv("MCP_LIBVIRT_MUTATION_DOMAIN_ALLOWLIST", "mcp_test_dummy,mcp_test_other")

    cfg = ServerConfig.from_env()

    assert cfg.mutation_domain_allowlist == {"mcp_test_dummy", "mcp_test_other"}


def test_config_parses_actor_role_policy(monkeypatch):
    monkeypatch.setenv("MCP_ACTOR_ROLES", "alice=admin;bob=viewer")
    monkeypatch.setenv("MCP_DEFAULT_ACTOR_ROLES", "viewer")
    monkeypatch.setenv("MCP_ROLE_TOOL_ALLOWLIST", "admin=*;viewer=host_info,get_*,list_*")

    cfg = ServerConfig.from_env()

    assert cfg.actor_policy_enabled() is True
    assert cfg.roles_for_actor("alice") == {"admin"}
    assert cfg.roles_for_actor("nobody") == {"viewer"}
    assert cfg.is_tool_allowed_for_actor("alice", "destroy_domain") is True
    assert cfg.is_tool_allowed_for_actor("bob", "get_domain") is True
    assert cfg.is_tool_allowed_for_actor("bob", "destroy_domain") is False
