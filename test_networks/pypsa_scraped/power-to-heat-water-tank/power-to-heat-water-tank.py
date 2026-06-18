import pandas as pd

import pypsa

n = pypsa.Network()
n.set_snapshots(pd.date_range("2025-01-01 00:00", "2025-01-01 03:00", freq="H"))

n.add("Bus", "power", carrier="AC")
n.add("Bus", "heat", carrier="heat")

n.add(
    "Generator",
    "wind turbine",
    bus="power",
    carrier="wind",
    p_nom_extendable=True,
    p_max_pu=[0.0, 0.2, 0.7, 0.4],
    capital_cost=500,
)

n.add("Load", "heat demand", bus="heat", p_set=20)

# %%
n.add(
    "Link",
    "heat pump",
    bus0="power",
    bus1="heat",
    efficiency=[2.5, 3.0, 3.2, 3.0],
    capital_cost=1000,
    p_nom_extendable=True,
)

# %%
n.add(
    "Store",
    "water tank",
    bus="heat",
    e_cyclic=True,
    e_nom=100,
    standing_loss=0.01,
)

# %%
n.optimize()

# %%
pd.DataFrame({attr: n.stores_t[attr]["water tank"] for attr in ["p", "e"]}).round(3)

# %%
pd.DataFrame({attr: n.links_t[attr]["heat pump"] for attr in ["p0", "p1"]}).round(3)
