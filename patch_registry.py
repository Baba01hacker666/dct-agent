import re

with open('dct/core/registry.py', 'r') as f:
    content = f.read()

# Update __slots__
content = content.replace('"latency_ms",\n    )', '"latency_ms",\n        "provider",\n        "api_key",\n    )')

# Update __init__ arguments
init_old = """        version: str = "",
        latency_ms: int = -1,
    ):"""
init_new = """        version: str = "",
        latency_ms: int = -1,
        provider: str = "ollama",
        api_key: str = "",
    ):"""
content = content.replace(init_old, init_new)

# Update __init__ body
init_body_old = "        self.latency_ms = latency_ms"
init_body_new = """        self.latency_ms = latency_ms
        self.provider = provider
        self.api_key = api_key"""
content = content.replace(init_body_old, init_body_new)

# Update base_url
base_url_old = """    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}\""""
base_url_new = """    def base_url(self) -> str:
        if self.provider == "openrouter":
            return "https://openrouter.ai"
        return f"http://{self.host}:{self.port}\""""
content = content.replace(base_url_old, base_url_new)

# Update to_dict
to_dict_old = """            "version": self.version,
            "latency_ms": self.latency_ms,
        }"""
to_dict_new = """            "version": self.version,
            "latency_ms": self.latency_ms,
            "provider": self.provider,
            "api_key": self.api_key,
        }"""
content = content.replace(to_dict_old, to_dict_new)

# Update from_dict
from_dict_old = """            version=d.get("version", ""),
            latency_ms=d.get("latency_ms", -1),
        )"""
from_dict_new = """            version=d.get("version", ""),
            latency_ms=d.get("latency_ms", -1),
            provider=d.get("provider", "ollama"),
            api_key=d.get("api_key", ""),
        )"""
content = content.replace(from_dict_old, from_dict_new)

# Update ServerRegistry.add definition
add_old = """    def add(
        self, host: str, port: int, alias: str = "", note: str = ""
    ) -> Server:"""
add_new = """    def add(
        self, host: str, port: int, alias: str = "", note: str = "", provider: str = "ollama", api_key: str = ""
    ) -> Server:"""
content = content.replace(add_old, add_new)

# Update ServerRegistry.add deduplication
dedup_old = """            if s.host == host and s.port == port:
                s.alias = alias
                s.note = note or s.note
                self.save()
                return s"""
dedup_new = """            if s.host == host and s.port == port and s.provider == provider:
                s.alias = alias
                s.note = note or s.note
                s.api_key = api_key or s.api_key
                self.save()
                return s"""
content = content.replace(dedup_old, dedup_new)

# Update ServerRegistry.add instantiation
inst_old = "        srv = Server(alias=alias, host=host, port=port, note=note)"
inst_new = "        srv = Server(alias=alias, host=host, port=port, note=note, provider=provider, api_key=api_key)"
content = content.replace(inst_old, inst_new)


with open('dct/core/registry.py', 'w') as f:
    f.write(content)
