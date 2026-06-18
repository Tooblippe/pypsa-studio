"""Build Pydantic models from PyPSA component metadata.

Run this module to inspect the component metadata schema:

    python -m pypsa_network_builder_v2.network_model.pypsa_components
"""

import json
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd
import pypsa
from pydantic import BaseModel, ConfigDict, Field, create_model

DEFAULT_COMPONENTS = (
    "buses",
    "links",
    "loads",
    "stores",
    "storage_units",
)

ICONS_DIR = Path(__file__).parent / "icons"


class Icon(BaseModel):
    """Icon metadata for a network component."""

    name: str
    path: str | None = None
    svg: str | None = None
    media_type: str = "image/svg+xml"


class ComponentAttribute(BaseModel):
    """A single PyPSA component attribute definition."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    pypsa_type: str | None = None
    python_type: str | None = None
    dtype: str | None = None
    unit: str | None = None
    default: Any = None
    description: str | None = None
    status: str | None = None
    static: bool | None = None
    varying: bool | None = None
    required: bool = False


class ComponentType(BaseModel):
    """Metadata and generated parameter model for one PyPSA component type."""

    component: str
    pypsa_name: str
    component_class: str
    params_model_name: str
    icon: Icon
    is_branch_component: bool = False
    is_one_port_component: bool = False
    is_controllable_one_port_component: bool = False
    attrs: dict[str, ComponentAttribute]

    def formatted_attrs(self) -> list[dict[str, Any]]:
        """Return this component's attrs formatted for display or UI tables."""
        return [
            {
                "name": attr.name,
                "type": attr.pypsa_type,
                "python_type": attr.python_type,
                "dtype": attr.dtype,
                "unit": attr.unit,
                "default": attr.default,
                "required": attr.required,
                "static": attr.static,
                "varying": attr.varying,
                "description": attr.description,
            }
            for attr in self.attrs.values()
        ]


class PypsaNetworkModel(BaseModel):
    """Pydantic description of the PyPSA network components used by this app."""

    all_components: dict[str, ComponentType] = Field(default_factory=dict)
    branch_components: list[str] = Field(default_factory=list)
    one_port_components: list[str] = Field(default_factory=list)
    controllable_one_port_components: list[str] = Field(default_factory=list)

    @property
    def components(self) -> dict[str, ComponentType]:
        """Compatibility accessor for all built component models."""
        return self.all_components

    def _resolve_component_key(self, key: str) -> str:
        """Resolve aliases and PyPSA names to component list names."""
        normalized_key = key.strip()
        lower_key = normalized_key.lower()
        common_names = {
            "bus": "buses",
            "buss": "buses",
            "busss": "buses",
            "busses": "buses",
        }

        if lower_key in common_names:
            return common_names[lower_key]
        if normalized_key in self.all_components:
            return normalized_key
        if lower_key in self.all_components:
            return lower_key

        for component_name, component in self.all_components.items():
            if component.pypsa_name == normalized_key:
                return component_name
            if component.pypsa_name.lower() == lower_key:
                return component_name

        raise KeyError(key)

    def component(self, key: str) -> ComponentType:
        """Return a component by list name, for example ``buses``, or PyPSA name, for example ``Bus``."""
        return self.all_components[self._resolve_component_key(key)]

    def attrs(self, component: str) -> list[dict[str, Any]]:
        """Return component attributes formatted for display or UI tables."""
        return self.component(component).formatted_attrs()

    def all_attrs(self) -> dict[str, list[dict[str, Any]]]:
        """Return attrs for every extracted component keyed by component list name."""
        return {
            component_name: component.formatted_attrs()
            for component_name, component in self.all_components.items()
        }

    @property
    def buses(self) -> ComponentType:
        """Return bus component metadata."""
        return self.component("buses")

    @property
    def busses(self) -> ComponentType:
        """Compatibility accessor for the common misspelling of ``buses``."""
        return self.buses

    @property
    def links(self) -> ComponentType:
        """Return link component metadata."""
        return self.component("links")

    @property
    def loads(self) -> ComponentType:
        """Return load component metadata."""
        return self.component("loads")

    @property
    def stores(self) -> ComponentType:
        """Return store component metadata."""
        return self.component("stores")

    @property
    def storage_units(self) -> ComponentType:
        """Return storage unit component metadata."""
        return self.component("storage_units")


def _clean_value(value: Any) -> Any:
    """Convert pandas/numpy metadata values into JSON/Pydantic friendly values."""
    if value is pd.NA:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except TypeError, ValueError:
            pass
    if isinstance(value, type):
        return f"{value.__module__}.{value.__qualname__}"
    return value


def _python_type_from_row(row: pd.Series) -> type[Any]:
    """Infer a Python type from a PyPSA component attribute row."""
    py_type = row.get("typ")
    if py_type in {str, int, float, bool}:
        return py_type

    pypsa_type = str(row.get("type", "")).lower()
    if "float" in pypsa_type or "series" in pypsa_type:
        return float
    if "integer" in pypsa_type or "int" in pypsa_type:
        return int
    if "boolean" in pypsa_type or "bool" in pypsa_type:
        return bool
    if "string" in pypsa_type:
        return str
    return Any


def _model_name(pypsa_name: str) -> str:
    """Return the generated Pydantic model name for a PyPSA component."""
    return f"{pypsa_name}Params"


def _icon_file(component_name: str) -> Path:
    """Return the expected SVG icon file path for a component."""
    return ICONS_DIR / f"{component_name}.svg"


def _icon_path(component_name: str) -> str:
    """Return the icon file path as a string."""
    return str(_icon_file(component_name))


def _icon_svg(component_name: str) -> str | None:
    """Read the component SVG icon if it exists."""
    icon_file = _icon_file(component_name)
    if not icon_file.exists():
        return None
    return icon_file.read_text(encoding="utf-8").strip()


def _component_icon(component_name: str, pypsa_name: str) -> Icon:
    """Build icon metadata for a component."""
    return Icon(
        name=pypsa_name,
        path=_icon_path(component_name),
        svg=_icon_svg(component_name),
    )


def _component_defaults(component: Any) -> pd.DataFrame:
    """Return the PyPSA defaults table for a component collection."""
    if hasattr(component, "defaults"):
        return component.defaults
    return component.attrs


def _component_refs(
    network: pypsa.Network,
    component_refs: Iterable[str] | None,
) -> list[str]:
    """Return component list names or PyPSA names to extract.

    ``network.all_components`` is a set property, not a method. Calling it as
    ``network.all_components()`` raises ``TypeError: 'set' object is not callable``.
    """
    if component_refs is not None:
        return list(component_refs)

    return sorted(network.all_components)


def _get_component(network: pypsa.Network, component_ref: str) -> Any:
    """Get a PyPSA component collection by list name or PyPSA name."""
    return network.components[component_ref]


def _component_list_names(
    network: pypsa.Network, component_names: Iterable[str]
) -> list[str]:
    """Return sorted component list names for PyPSA component names."""
    return sorted(network.components[name].list_name for name in component_names)


def _component_attribute(name: str, row: pd.Series) -> ComponentAttribute:
    """Create app metadata for one PyPSA component attribute row."""
    default = _clean_value(row.get("default"))
    status = _clean_value(row.get("status"))
    required = "required" in str(status).lower()
    py_type = row.get("typ")

    return ComponentAttribute(
        name=name,
        pypsa_type=_clean_value(row.get("type")),
        python_type=_clean_value(py_type),
        dtype=str(row.get("dtype")) if row.get("dtype") is not None else None,
        unit=_clean_value(row.get("unit")),
        default=default,
        description=_clean_value(row.get("description")),
        status=status,
        static=_clean_value(row.get("static")),
        varying=_clean_value(row.get("varying")),
        required=required,
    )


def create_component_param_model(component: Any) -> type[BaseModel]:
    """Create a Pydantic params class for a PyPSA component collection."""
    fields: dict[str, tuple[type[Any], Any]] = {}

    for attr_name, row in _component_defaults(component).iterrows():
        python_type = _python_type_from_row(row)
        attribute = _component_attribute(str(attr_name), row)
        default = ... if attribute.required else attribute.default
        if default is None and not attribute.required:
            python_type = python_type | None

        fields[str(attr_name)] = (
            python_type,
            Field(
                default,
                description=attribute.description,
                json_schema_extra={
                    "pypsa_type": attribute.pypsa_type,
                    "unit": attribute.unit,
                    "status": attribute.status,
                    "static": attribute.static,
                    "varying": attribute.varying,
                },
            ),
        )

    return create_model(_model_name(component.name), __base__=BaseModel, **fields)


def create_component_param_models(
    component_refs: Iterable[str] | None = None,
    network: pypsa.Network | None = None,
) -> dict[str, type[BaseModel]]:
    """Create Pydantic params classes keyed by PyPSA component list name.

    If ``component_refs`` is omitted, every component from ``network.all_components``
    is extracted.
    """
    network = network or pypsa.Network()
    models: dict[str, type[BaseModel]] = {}
    for component_ref in _component_refs(network, component_refs):
        component = _get_component(network, component_ref)
        models[component.list_name] = create_component_param_model(component)
    return models


def build_network_model(
    component_refs: Iterable[str] | None = None,
    network: pypsa.Network | None = None,
) -> PypsaNetworkModel:
    """Extract PyPSA component metadata into a Pydantic model.

    If ``component_refs`` is omitted, every component from ``network.all_components``
    is extracted. Pass component list names or PyPSA names to limit the result, for example
    ``["buses", "links"]`` or ``["Bus", "Link"]``.
    """
    network = network or pypsa.Network()
    components: dict[str, ComponentType] = {}
    branch_components = set(network.branch_components)
    one_port_components = set(network.one_port_components)
    controllable_one_port_components = set(network.controllable_one_port_components)

    for component_ref in _component_refs(network, component_refs):
        component = _get_component(network, component_ref)
        attrs = {
            str(attr_name): _component_attribute(str(attr_name), row)
            for attr_name, row in _component_defaults(component).iterrows()
        }
        components[component.list_name] = ComponentType(
            component=component.list_name,
            pypsa_name=component.name,
            component_class=f"{type(component).__module__}.{type(component).__qualname__}",
            params_model_name=_model_name(component.name),
            icon=_component_icon(component.list_name, component.name),
            is_branch_component=component.name in branch_components,
            is_one_port_component=component.name in one_port_components,
            is_controllable_one_port_component=component.name
            in controllable_one_port_components,
            attrs=attrs,
        )

    return PypsaNetworkModel(
        all_components=components,
        branch_components=_component_list_names(network, branch_components),
        one_port_components=_component_list_names(network, one_port_components),
        controllable_one_port_components=_component_list_names(
            network,
            controllable_one_port_components,
        ),
    )


def main() -> None:
    """Print the extracted model metadata as JSON."""
    model = build_network_model()
    print(json.dumps(model.model_dump(), indent=2, default=str))


if __name__ == "__main__":
    main()
