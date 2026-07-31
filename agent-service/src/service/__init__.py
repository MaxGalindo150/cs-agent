"""Agent Service — EigenCore Customer Support agent.

Package-level identity constants with a single source of truth. Ops surfaces
(health endpoint, structured logs) and tests all read the same values from here.

`__version__` is resolved from installed package metadata, so `pyproject.toml`
stays the single source of truth for the version. The literal fallback keeps
imports working when the tree is run without being installed (e.g. some tooling).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

SERVICE_NAME = "agent-service"

try:
    __version__ = version("agent-service")
except PackageNotFoundError:  # not installed (running straight from source)
    __version__ = "0.0.0+unknown"

__all__ = ["SERVICE_NAME", "__version__"]
