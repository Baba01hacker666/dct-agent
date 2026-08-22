"""
dct.web
Web interface and streaming HTTP server for DCT Agent.
"""

__all__ = ["create_app", "run_server"]


def __getattr__(name):
    if name in ("create_app", "run_server"):
        from dct.web import server

        return getattr(server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
