import pandas as pd

import pypsa

# %%
YEAR = 2030
url = f"https://raw.githubusercontent.com/PyPSA/technology-data/master/outputs/costs_{YEAR}.csv"
costs = pd.read_csv(url, index_col=[0, 1])
costs.loc[costs.unit.str.contains("/kW"), "value"] *= 1e3
costs = costs.value.unstack().fillna({"discount rate": 0.07, "lifetime": 20, "FOM": 0})

# %%
costs["marginal_cost"] = costs["VOM"] + costs["fuel"] / costs["efficiency"]

# %%
from pypsa.costs import annuity

# %%
a = costs.apply(lambda x: annuity(x["discount rate"], x["lifetime"]), axis=1)

# %%
costs["capital_cost"] = (a + costs["FOM"] / 100) * costs["investment"]

# %%
RESOLUTION = 3  # hours
url = "https://tubcloud.tu-berlin.de/s/9toBssWEdaLgHzq/download/time-series.csv"
ts = pd.read_csv(url, index_col=0, parse_dates=True)[::RESOLUTION]

# %%
ts.head(3)

# %%
n = pypsa.Network()
n.add("Bus", "electricity", carrier="electricity")
n.set_snapshots(ts.index)

# %%
n.snapshot_weightings.loc[:, :] = RESOLUTION

# %%
carriers = [
    "wind",
    "solar",
    "hydrogen storage",
    "battery storage",
    "load shedding",
    "electrolysis",
    "turbine",
    "electricity",
    "hydrogen",
]
colors = [
    "dodgerblue",
    "gold",
    "black",
    "yellowgreen",
    "darkorange",
    "magenta",
    "red",
    "grey",
    "grey",
]
n.add("Carrier", carriers, color=colors)

# %%
n.add(
    "Load",
    "demand",
    bus="electricity",
    p_set=ts.load_mw,
)

# %%
n.add(
    "Generator",
    "load shedding",
    bus="electricity",
    carrier="load shedding",
    marginal_cost=2000,
    p_nom=ts.load_mw.max(),
)

# %%
n.add(
    "Generator",
    "wind",
    bus="electricity",
    carrier="wind",
    p_max_pu=ts.wind_pu,
    capital_cost=costs.at["onwind", "capital_cost"],
    marginal_cost=costs.at["onwind", "marginal_cost"],
    p_nom_extendable=True,
)

# %%
n.add(
    "Generator",
    "solar",
    bus="electricity",
    carrier="solar",
    p_max_pu=ts.pv_pu,
    capital_cost=costs.at["solar", "capital_cost"],
    marginal_cost=costs.at["solar", "marginal_cost"],
    p_nom_extendable=True,
)

# %%
n.add(
    "StorageUnit",
    "battery storage",
    bus="electricity",
    carrier="battery storage",
    max_hours=3,
    capital_cost=costs.at["battery inverter", "capital_cost"]
    + 3 * costs.at["battery storage", "capital_cost"],
    efficiency_store=costs.at["battery inverter", "efficiency"],
    efficiency_dispatch=costs.at["battery inverter", "efficiency"],
    p_nom_extendable=True,
    cyclic_state_of_charge=True,
)

# %%
n.add("Bus", "hydrogen", carrier="hydrogen")

# %%
n.add(
    "Link",
    "electrolysis",
    bus0="electricity",
    bus1="hydrogen",
    carrier="electrolysis",
    p_nom_extendable=True,
    efficiency=costs.at["electrolysis", "efficiency"],
    capital_cost=costs.at["electrolysis", "capital_cost"],
)

# %%
n.add(
    "Link",
    "turbine",
    bus0="hydrogen",
    bus1="electricity",
    carrier="turbine",
    p_nom_extendable=True,
    efficiency=costs.at["OCGT", "efficiency"],
    capital_cost=costs.at["OCGT", "capital_cost"] / costs.at["OCGT", "efficiency"],
)

# %%
n.add(
    "Store",
    "hydrogen storage",
    bus="hydrogen",
    carrier="hydrogen storage",
    capital_cost=costs.at["hydrogen storage underground", "capital_cost"],
    e_nom_extendable=True,
    e_cyclic=True,
)

# %%
n.optimize()

# %%
tsc = (
    pd.concat([n.statistics.capex(), n.statistics.opex()], axis=1).sum(axis=1).div(1e9)
)
tsc

# %%
tsc.sum()

# %%
n.statistics.optimal_capacity().div(1e3)

# %%
n.statistics.energy_balance(bus_carrier="electricity").sort_values().div(1e6)

# %%
n.statistics.energy_balance.plot.area(linewidth=0, bus_carrier="electricity")

# %%
n.buses_t.marginal_price.plot(figsize=(7, 2))
