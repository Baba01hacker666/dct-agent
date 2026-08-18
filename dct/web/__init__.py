"""
dct.web
Web interface and streaming HTTP server for DCT Agent.
"""

from dct.web.server import create_app, run_server

__all__ = ["create_app", "run_server"]
