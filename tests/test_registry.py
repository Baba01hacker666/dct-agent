from dct.core.registry import Server, ServerRegistry


def test_server_dict_serialization():
    s = Server("or1", "openrouter.ai", 443, provider="openrouter", api_key="sk-test")
    d = s.to_dict()
    assert d["provider"] == "openrouter"
    assert d["api_key"] == "sk-test"
    assert d["host"] == "openrouter.ai"

    s2 = Server.from_dict(d)
    assert s2.provider == "openrouter"
    assert s2.api_key == "sk-test"
    assert s2.base_url() == "https://openrouter.ai"


def test_registry_add_openrouter(tmp_path):
    reg_path = tmp_path / "servers.json"
    reg = ServerRegistry(str(reg_path))
    reg.add("openrouter.ai", 443, "or1", provider="openrouter", api_key="sk-test")

    assert len(reg.servers) == 1
    assert reg.servers[0].provider == "openrouter"

    # Reload from disk
    reg2 = ServerRegistry(str(reg_path))
    assert len(reg2.servers) == 1
    assert reg2.servers[0].provider == "openrouter"
    assert reg2.servers[0].api_key == "sk-test"
