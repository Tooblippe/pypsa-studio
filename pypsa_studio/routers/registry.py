"""Discovery for in-package Python canvas routers."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path

from pypsa_studio.routers.base import RouterBase


def discover_python_routers() -> dict[str, RouterBase]:
    """Discover concrete RouterBase subclasses in the routers package."""
    routers: dict[str, RouterBase] = {}
    package_name = __package__ or "pypsa_network_builder_v2.routers"
    package_path = Path(__file__).parent

    for module_info in pkgutil.iter_modules([str(package_path)]):
        if module_info.name in {"base", "registry", "__init__"}:
            continue
        module = importlib.import_module(f"{package_name}.{module_info.name}")
        for _, router_class in inspect.getmembers(module, inspect.isclass):
            if router_class is RouterBase:
                continue
            if not issubclass(router_class, RouterBase):
                continue
            if inspect.isabstract(router_class):
                continue
            router = router_class()
            router_name = str(router.name).strip()
            if not router_name:
                raise ValueError(
                    f"{router_class.__name__} must define a non-empty name."
                )
            if router_name in routers:
                raise ValueError(f"Duplicate router name: {router_name}.")
            routers[router_name] = router

    return routers


def router_options(routers: dict[str, RouterBase]) -> list[dict[str, str]]:
    """Return router option metadata for the UI."""
    return [
        {
            "name": router.name,
            "label": router.label or router.name,
            "description": router.description,
        }
        for router in routers.values()
    ]
