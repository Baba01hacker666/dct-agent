from dct.core.registry import Server, ServerRegistry
registry = ServerRegistry("./test.json")
registry.add("localhost", 11434, "local")
registry.add("10.0.0.5", 11434, "vps1", "VPS notes")
registry.add("openrouter.ai", 443, "or1", provider="openrouter", api_key="test_key")

registry.save()

with open("./test.json", "r") as f:
    print(f.read())
