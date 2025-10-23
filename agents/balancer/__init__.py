"""Balancer agent package.

Minimal FastAPI scaffold for MCP-style local dispatch tests.

Expose submodules lazily to avoid circular import during package initialization.

This allows tests to do `from agents.balancer import main` while preventing
`__init__` from importing `main` before the package is fully initialized
when `main` imports other submodules (like `tools`).
"""

from importlib import import_module
from typing import Any

__all__ = ["main", "tools"]


def __getattr__(name: str) -> Any:
	if name in __all__:
		module = import_module(f"{__name__}.{name}")
		globals()[name] = module
		return module
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
	return sorted(list(globals().keys()) + __all__)
