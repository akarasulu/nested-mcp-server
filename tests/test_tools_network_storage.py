import pytest

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.errors import MCPError
from libvirt_mcp_server.tools import network_tools, storage_tools


class FakeLibvirtAdapter:
    def __init__(self):
        self.last = None

    def define_network_xml(self, uri, network_xml):
        self.last = ("define_network_xml", uri, network_xml)
        return {"source": "libvirt", "status": "defined"}

    def start_network(self, uri, network_name):
        self.last = ("start_network", uri, network_name)
        return {"source": "libvirt", "status": "started", "network_name": network_name}

    def define_storage_pool_xml(self, uri, pool_xml):
        self.last = ("define_storage_pool_xml", uri, pool_xml)
        return {"source": "libvirt", "status": "defined"}

    def create_storage_volume_xml(self, uri, pool_name, volume_xml):
        self.last = ("create_storage_volume_xml", uri, pool_name, volume_xml)
        return {"source": "libvirt", "status": "created", "pool_name": pool_name}


@pytest.fixture
def config():
    cfg = ServerConfig.from_env()
    cfg.allow_mutations = True
    cfg.allow_define = True
    cfg.test_resource_prefix = "mcp_test_"
    return cfg


def test_define_network_xml_requires_test_prefix(config):
    adapter = FakeLibvirtAdapter()

    with pytest.raises(MCPError) as exc:
        network_tools.define_network_xml(
            config,
            adapter,
            network_xml="<network><name>prod-net</name></network>",
            hypervisor_ref=None,
        )

    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_start_network_allows_test_prefix(config):
    adapter = FakeLibvirtAdapter()

    result = network_tools.start_network(
        config,
        adapter,
        network_name="mcp_test_net",
        hypervisor_ref=None,
    )

    assert result["status"] == "started"
    assert result["network_name"] == "mcp_test_net"


def test_define_storage_pool_xml_requires_test_prefix(config):
    adapter = FakeLibvirtAdapter()

    pool_xml = """
<pool type='dir'>
  <name>prod_pool</name>
  <target><path>/tmp/prod_pool</path></target>
</pool>
"""

    with pytest.raises(MCPError) as exc:
        storage_tools.define_storage_pool_xml(
            config,
            adapter,
            pool_xml=pool_xml,
            hypervisor_ref=None,
        )

    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_create_storage_volume_xml_requires_prefixed_pool_and_volume(config):
    adapter = FakeLibvirtAdapter()

    volume_xml = """
<volume>
  <name>mcp_test_vol.qcow2</name>
  <capacity unit='bytes'>1048576</capacity>
  <target><format type='qcow2'/></target>
</volume>
"""

    with pytest.raises(MCPError) as exc:
        storage_tools.create_storage_volume_xml(
            config,
            adapter,
            pool_name="non_test_pool",
            volume_xml=volume_xml,
            hypervisor_ref=None,
        )

    assert exc.value.code == "TEST_PREFIX_REQUIRED"


def test_create_storage_volume_xml_allows_prefixed_names(config):
    adapter = FakeLibvirtAdapter()

    volume_xml = """
<volume>
  <name>mcp_test_vol.qcow2</name>
  <capacity unit='bytes'>1048576</capacity>
  <target><format type='qcow2'/></target>
</volume>
"""

    result = storage_tools.create_storage_volume_xml(
        config,
        adapter,
        pool_name="mcp_test_pool",
        volume_xml=volume_xml,
        hypervisor_ref=None,
    )

    assert result["status"] == "created"
    assert result["pool_name"] == "mcp_test_pool"


def test_create_linked_clone_volume_rejects_absolute_backing_when_relative_required(config):
    adapter = FakeLibvirtAdapter()

    with pytest.raises(MCPError) as exc:
        storage_tools.create_linked_clone_volume(
            config,
            adapter,
            pool_name="mcp_test_pool",
            volume_name="mcp_test_child.qcow2",
            backing_file="/var/lib/libvirt/images/vda.qcow2",
            capacity_bytes=1048576,
            format="qcow2",
            backing_format="qcow2",
            relative_backing=True,
            hypervisor_ref=None,
        )

    assert exc.value.code == "INVALID_BACKING_PATH"


def test_create_linked_clone_volume_allows_relative_backing(config):
    adapter = FakeLibvirtAdapter()

    result = storage_tools.create_linked_clone_volume(
        config,
        adapter,
        pool_name="mcp_test_pool",
        volume_name="mcp_test_child.qcow2",
        backing_file="../vda.qcow2",
        capacity_bytes=1048576,
        format="qcow2",
        backing_format="qcow2",
        relative_backing=True,
        hypervisor_ref=None,
    )

    assert result["status"] == "created"
    assert result["pool_name"] == "mcp_test_pool"
    assert result["backing_file"] == "../vda.qcow2"
    assert result["relative_backing"] is True
    assert "<backingStore>" in adapter.last[3]
    assert "../vda.qcow2" in adapter.last[3]
