"""Base classes and serializable data contracts for Python canvas routers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypedDict


class RouterNetwork(TypedDict):
    """Serializable canvas network passed to and returned from Python routers."""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    diagram_model: dict[str, Any]
    metadata: dict[str, Any]


class RouterBase(ABC):
    """Base class for Python routers that transform a canvas network."""

    name: str = ""
    label: str = ""
    description: str = ""

    @abstractmethod
    def route(self, network: RouterNetwork) -> RouterNetwork:
        """Return a routed copy of the canvas network."""
