import logging

import matplotlib.pyplot as plt
import pandas as pd

import pypsa

pypsa.options.params.optimize.solver_name = "gurobi"
logging.getLogger("gurobipy").setLevel(logging.ERROR)
logging.getLogger("linopy").setLevel(logging.ERROR)

# %%
n = pypsa.examples.model_energy()

n.remove("Generator", "load shedding")
n.remove("StorageUnit", "battery storage")

n.generators.loc[["solar", "wind"], "p_nom"] = 30_000, 20_000
n.generators.p_nom_extendable = False

n.links.loc[["electrolysis", "turbine"], "p_nom"] = 10_000, 20_000
n.links.p_nom_extendable = False

n.stores.loc["hydrogen storage", ["e_nom", "e_initial"]] = 2_000_000, 500_000
n.stores.e_nom_extendable = False
n.stores.e_cyclic = False

n.add("Carrier", "gas", color="darkorange")
n.add(
    "Generator",
    "gas",
    bus="electricity",
    p_nom=40_000,
    marginal_cost=80,
    marginal_cost_quadratic=0.01,
    carrier="gas",
)

# %%
n.optimize(assign_all_duals=True, log_to_console=False)

# %%
obj = n.statistics.opex(components="Generator").sum() / 1e6
obj

# %%
n.buses_t.marginal_price["electricity"].resample("D").mean().plot(
    figsize=(6, 2), ylabel="€/MWh", xlabel=""
)

# %%
pdc = (
    n.buses_t.marginal_price["electricity"]
    .sort_values(ascending=False)
    .reset_index(drop=True)
)
pdc.plot(figsize=(5, 3), ylabel="€/MWh", xlabel="snapshots", xlim=(0, 8760 / 3))

# %%
msv = n.buses_t.marginal_price["hydrogen"]
msv.plot(figsize=(6, 2), ylim=(0, 100), ylabel="€/MWh", xlabel="")

# %%
soc = n.stores_t.e.div(1e3).squeeze()
soc.plot(figsize=(6, 2), ylabel="GWh", xlabel="", legend=False)

# %%
n.model.solver_model = None
n2 = n.copy()

n2.optimize.optimize_with_rolling_horizon(
    assign_all_duals=True,
    horizon=120,
    overlap=0,
    log_to_console=False,
)

# %%
obj2 = n2.statistics.opex(components="Generator").sum() / 1e6
obj2

# %%
pdc2 = (
    n2.buses_t.marginal_price["electricity"]
    .sort_values(ascending=False)
    .reset_index(drop=True)
)
pdc2.plot(figsize=(5, 3), ylabel="€/MWh", xlabel="snapshots", xlim=(0, 8760 / 3))

# %%
soc2 = n2.stores_t.e.div(1e3).squeeze()
soc2.plot(figsize=(6, 2), ylabel="GWh", xlabel="", legend=False)

# %%
n3 = n.copy()

n3.stores_t.marginal_cost["hydrogen storage"] = msv

n3.optimize.optimize_with_rolling_horizon(
    assign_all_duals=True,
    horizon=120,
    overlap=0,
    log_to_console=False,
)

# %%
obj3 = n3.statistics.opex(components="Generator").sum() / 1e6
obj3

# %%
pdc3 = (
    n3.buses_t.marginal_price["electricity"]
    .sort_values(ascending=False)
    .reset_index(drop=True)
)
pdc3.plot(figsize=(5, 3), ylabel="€/MWh", xlabel="snapshots", xlim=(0, 8760 / 3))

# %%
soc3 = n3.stores_t.e.div(1e3).squeeze()
soc3.plot(figsize=(6, 2), ylabel="GWh", xlabel="", legend=False)

# %%
n4 = n.copy()
n4.stores_t.marginal_cost["hydrogen storage"] = msv.mean()

n4.optimize.optimize_with_rolling_horizon(
    assign_all_duals=True,
    horizon=120,
    overlap=0,
    log_to_console=False,
)

# %%
obj4 = n4.statistics.opex(components="Generator").sum() / 1e6
obj4

# %%
pdc4 = (
    n4.buses_t.marginal_price["electricity"]
    .sort_values(ascending=False)
    .reset_index(drop=True)
)

# %%
soc4 = n4.stores_t.e.div(1e3).squeeze()
soc4.plot(figsize=(6, 2), ylabel="GWh", xlabel="", legend=False)

# %%
pd.Series(
    {
        "perfect foresight": obj,
        "rolling horizon": obj2,
        "rolling horizon + water values": obj3,
        "rolling horizon + avg. water values": obj4,
    }
).round(3)

# %%
ax = pd.concat(
    {
        "perfect foresight": pdc,
        "rolling horizon": pdc2,
        "rolling horizon + water values": pdc3,
        "rolling horizon + avg. water values": pdc4,
    },
    axis=1,
).plot(figsize=(5, 3), ylabel="€/MWh", xlabel="snapshots", xlim=(0, 8760 / 3))
for line in ax.lines[-3:]:
    line.set_linestyle(":")

# %%
ax = pd.concat(
    {
        "perfect foresight": soc,
        "rolling horizon": soc2,
        "rolling horizon + water values": soc3,
        "rolling horizon + avg. water values": soc4,
    },
    axis=1,
).plot(figsize=(6, 2), ylabel="GWh", xlabel="")
for line in ax.lines[-3:]:
    line.set_linestyle(":")

plt.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
