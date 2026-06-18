import numpy as np
import pandas as pd

import pypsa
from pypsa.costs import annuity

n = pypsa.Network()

n.add("Bus", "seville")

n.add("Load", "demand", bus="seville", p_set=100)

n.add("Generator", "grid", bus="seville", p_nom=100, marginal_cost=120, carrier="grid")

# %%
p_max_pu = pd.read_csv(
    "https://model.energy/data/time-series-f17c3736a2719ce7da58484180d89e2d.csv",
    index_col=0,
    parse_dates=True,
)["solar"]
p_max_pu[7:15]

# %%
n.set_snapshots(p_max_pu.index)
len(n.snapshots)

# %%
n.add(
    "Generator",
    "solar",
    bus="seville",
    p_max_pu=p_max_pu,
    capital_cost=annuity(0.05, 25) * 400_000,
    p_nom_extendable=True,
    carrier="solar",
)

# %%
cc_inverter = annuity(0.05, 25) * 170_000
cc_storage = annuity(0.05, 25) * 150_000

n.add(
    "StorageUnit",
    "battery",
    bus="seville",
    capital_cost=cc_inverter + 4 * cc_storage,
    p_nom_extendable=True,
    carrier="battery",
    efficiency_store=np.sqrt(0.9),
    efficiency_dispatch=np.sqrt(0.9),
    max_hours=4,
)

# %%
n.optimize()

# %%
display(n.generators.p_nom_opt)
display(n.storage_units.p_nom_opt)

# %%
n.statistics.optimal_capacity()

# %%
totex = {"opex": n.statistics.opex(), "capex": n.statistics.capex()}
pd.concat(totex, axis=1).div(1e6).round(2)  # M€/a

# %%
(n.statistics.capex().sum() + n.statistics.opex().sum()) / 100 / 8760  # €/MWh

# %%
n.statistics.energy_balance().div(1e3)  # GWh

# %%
n.storage_units_t.state_of_charge.loc["2011-01"].plot(backend="plotly")

# %%
n.add(
    "Carrier",
    ["grid", "solar", "battery", "AC"],
    color=["blue", "yellow", "green", "k"],
)

n.statistics.energy_balance.iplot()

# %%
n.export_to_excel("data-centre-investment.xlsx")
n.export_to_netcdf("data-centre-investment.nc")

o = pypsa.Network("data-centre-investment.nc")
