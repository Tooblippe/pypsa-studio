# PyPSA Network Builder V2

A Python Reflex application scaffold.

## Setup

```bash
uv sync
uv run reflex init
uv run reflex run
```

If you are not using `uv`, install Reflex with pip:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
reflex init
reflex run
```

The app lives in `pypsa_network_builder_v2/pypsa_network_builder_v2.py`.

## PyPSA Network Model Metadata

The dynamic PyPSA component model lives in
`pypsa_network_builder_v2/network_model/pypsa_components.py`.

```python
from pypsa_studio.network_model import (
    build_network_model,
    create_component_param_models,
    load_pypsa_loaded_network,
)

network_model = build_network_model()

print(network_model.all_components["buses"])
print(network_model.all_components["buses"].icon.path)
print(network_model.all_components["buses"].icon.svg)
print(network_model.all_components["buses"].attrs)
print(network_model.buses.attrs["v_nom"])
print(network_model.attrs("busss"))
print(network_model.all_attrs())
print(network_model.links.is_branch_component)
print(network_model.branch_components)

loaded_network = load_pypsa_loaded_network("network.nc")
print(loaded_network.current_values["buses"]["v_nom"])

param_models = create_component_param_models()
BusParams = param_models["buses"]
bus = BusParams(name="bus_1", v_nom=110)
```

Run the metadata extractor directly with:

```bash
python -m pypsa_network_builder_v2.network_model.pypsa_components
```

The Reflex app can load PyPSA networks from `.nc`, `.h5`, `.hdf5`, a `.zip`
containing a PyPSA CSV-folder export, or a selected CSV export directory.
Loaded component values are kept in a separate `PypsaLoadedNetwork` object and
shown in the displayed dropdowns.
