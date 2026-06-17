import pandas as pd

import pypsa
from pypsa.costs import annuity

# %%
YEAR = 2030
url = f"https://raw.githubusercontent.com/PyPSA/technology-data/master/outputs/costs_{YEAR}.csv"
costs = pd.read_csv(url, index_col=[0, 1])
costs.loc[costs.unit.str.contains("/kW"), "value"] *= 1e3
costs = costs.value.unstack().fillna({"discount rate": 0.07, "lifetime": 20, "FOM": 0})

# Let's also take a little more optimistic view on the costs of electrolysers
costs.loc["electrolysis", "investment"] = 500  # €/kW

# %%
a = costs.apply(lambda x: annuity(x["discount rate"], x["lifetime"]), axis=1)

# %%
costs["capital_cost"] = (a + costs["FOM"] / 100) * costs["investment"]

# %%
RESOLUTION = 4  # hours
url = "https://model.energy/data/time-series-ca2bcb9e843aeb286cd6295854c885b6.csv"  # South of Argentina
# url = "https://model.energy/data/time-series-57f7bbcb5c4821506de052e52d022b48.csv" # Namibia
ts = pd.read_csv(url, index_col=0, parse_dates=True)[::RESOLUTION]

# %%
ts.head(3)

# %%
n = pypsa.Network()
for carrier in ["electricity", "hydrogen", "co2", "methanol"]:
    n.add("Bus", carrier, carrier=carrier, unit="t/h" if carrier == "co2" else "MW")
n.set_snapshots(ts.index)
n.snapshot_weightings.loc[:, :] = RESOLUTION

# %%
carriers = {
    "wind": "dodgerblue",
    "solar": "gold",
    "hydrogen storage": "blueviolet",
    "battery storage 3h": "yellowgreen",
    "battery storage 6h": "yellowgreen",
    "electrolysis": "magenta",
    "turbine": "darkorange",
    "methanolisation": "cyan",
    "direct air capture": "coral",
    "co2 storage": "black",
    "methanol storage": "cadetblue",
    "electricity": "grey",
    "hydrogen": "grey",
    "co2": "grey",
    "methanol": "grey",
}
n.add("Carrier", carriers.keys(), color=carriers.values())

# %%
n.add(
    "Load",
    "demand",
    bus="methanol",
    p_set=1e6 / 8760,
)

# %%
n.add(
    "Generator",
    "wind",
    bus="electricity",
    carrier="wind",
    p_max_pu=ts.onwind,
    capital_cost=costs.at["onwind", "capital_cost"],
    p_nom_extendable=True,
)

# %%
n.add(
    "Generator",
    "solar",
    bus="electricity",
    carrier="solar",
    p_max_pu=ts.solar,
    capital_cost=costs.at["solar", "capital_cost"],
    p_nom_extendable=True,
)

# %%
for max_hours in [3, 6]:
    n.add(
        "StorageUnit",
        f"battery storage {max_hours}h",
        bus="electricity",
        carrier=f"battery storage {max_hours}h",
        max_hours=max_hours,
        capital_cost=costs.at["battery inverter", "capital_cost"]
        + max_hours * costs.at["battery storage", "capital_cost"],
        efficiency_store=costs.at["battery inverter", "efficiency"],
        efficiency_dispatch=costs.at["battery inverter", "efficiency"],
        p_nom_extendable=True,
        cyclic_state_of_charge=True,
    )

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
tech = "hydrogen storage tank type 1 including compressor"

n.add(
    "Store",
    "hydrogen storage",
    bus="hydrogen",
    carrier="hydrogen storage",
    capital_cost=costs.at[tech, "capital_cost"],
    e_nom_extendable=True,
    e_cyclic=True,
)

# %%
electricity_input = 2  # MWh/tCO2

n.add(
    "Link",
    "direct air capture",
    bus0="electricity",
    bus1="co2",
    carrier="direct air capture",
    p_nom_extendable=True,
    efficiency=1 / electricity_input,
    capital_cost=costs.at["direct air capture", "capital_cost"] / electricity_input,
)

# %%
n.add(
    "Store",
    "co2 storage",
    bus="co2",
    carrier="co2 storage",
    capital_cost=costs.at["CO2 storage tank", "capital_cost"],
    e_nom_extendable=True,
    e_cyclic=True,
)

# %%
eff_h2 = 1 / costs.at["methanolisation", "hydrogen-input"]

n.add(
    "Link",
    "methanolisation",
    bus0="hydrogen",
    bus1="methanol",
    bus2="electricity",
    bus3="co2",
    carrier="methanolisation",
    p_nom_extendable=True,
    capital_cost=costs.at["methanolisation", "capital_cost"] * eff_h2,
    efficiency=eff_h2,
    efficiency2=-costs.at["methanolisation", "electricity-input"] * eff_h2,
    efficiency3=-costs.at["methanolisation", "carbondioxide-input"] * eff_h2,
)

# %%
capital_cost = costs.at[
    "General liquid hydrocarbon storage (crude)", "capital_cost"
] / (15.6 * 1000 / 3600)

n.add(
    "Store",
    "methanol storage",
    bus="co2",
    carrier="methanol storage",
    capital_cost=capital_cost,
    e_nom_extendable=True,
    e_cyclic=True,
)

# %%
n.optimize()

# %%
n.statistics.capex().div(1e6).sort_values(ascending=False)  # mn€/a

# %%
n.statistics.capex().sum() / (8760 * n.loads.p_set.sum())

# %%
n.statistics.optimal_capacity()

# %%
n.statistics.capacity_factor() * 100

# %%
n.statistics.curtailment().div(1e6)

# %%
n.statistics.energy_balance.plot.area(linewidth=0, bus_carrier="electricity")

# %%
n.statistics.energy_balance.plot.area(linewidth=0, bus_carrier="hydrogen")

# %%
n.statistics.energy_balance.plot.area(linewidth=0, bus_carrier="co2")

# %%
n.statistics.energy_balance.plot.area(linewidth=0, bus_carrier="methanol")

# %%
n.add(
    "Generator",
    "biogenic co2",
    bus="co2",
    carrier="biogenic co2",
    p_nom=1000,  # non-binding
    marginal_cost=50,
)
n.add(
    "Carrier",
    "biogenic co2",
    color="forestgreen",
)
n.optimize()

# %%
(n.statistics.capex().sum() + n.statistics.opex().sum()) / 1e6  # €/MWh

# %%
n.statistics.energy_balance(bus_carrier="co2")

# %%
n.links.loc["electrolysis", "p_min_pu"] = 0.8
n.links.loc["methanolisation", "p_min_pu"] = 0.8
n.optimize()

# %%
(n.statistics.capex().sum() + n.statistics.opex().sum()) / 1e6  # €/MWh

# %%
n.statistics.optimal_capacity()
