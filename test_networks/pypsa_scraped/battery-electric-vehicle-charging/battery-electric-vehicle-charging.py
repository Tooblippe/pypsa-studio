import matplotlib.pyplot as plt
import pandas as pd

import pypsa

# %%
index = pd.date_range("2016-01-01 00:00", "2016-01-01 23:00", freq="h")

# %%
bev_usage = pd.Series([0] * 7 + [9] * 2 + [0] * 8 + [9] * 2 + [0] * 5, index)

# %%
pv_pu = pd.Series(
    [0.0] * 7
    + [0.2, 0.4, 0.6, 0.75, 0.85, 0.9, 0.85, 0.75, 0.6, 0.4, 0.2, 0.1]
    + [0.0] * 5,
    index,
)

# %%
charger_p_max_pu = pd.Series(0, index=index)
charger_p_max_pu["2016-01-01 09:00":"2016-01-01 16:00"] = 1

# %%
df = pd.concat({"BEV": bev_usage, "PV": pv_pu, "Charger": charger_p_max_pu}, axis=1)
df.plot.area(subplots=True)

# %%
n = pypsa.Network()
n.set_snapshots(index)

n.add("Bus", "place of work")

n.add("Bus", "car battery")

n.add(
    "Generator",
    "PV panel",
    bus="place of work",
    p_nom_extendable=True,
    p_max_pu=pv_pu,
    capital_cost=1000,  # dummy cost value
)

n.add("Load", "driving", bus="car battery", p_set=bev_usage)

n.add(
    "Link",
    "charger",
    bus0="place of work",
    bus1="car battery",
    p_nom=120,
    p_max_pu=charger_p_max_pu,
    efficiency=0.9,
)

n.add("Store", "battery", bus="car battery", e_cyclic=True, e_nom=100)

# %%
n.optimize()
print("Objective:", n.objective)

# %%
n.generators.p_nom_opt["PV panel"]

# %%
n.generators_t.p.plot.area()

# %%
df = pd.DataFrame({attr: n.stores_t[attr]["battery"] for attr in ["p", "e"]})
df.plot(grid=True, ylim=(-10, 40))
plt.legend(labels=["Energy output", "State of charge"])

# %%
(n.generators_t.p.loc[:, "PV panel"].sum() - n.loads_t.p.loc[:, "driving"].sum())

# %%
n.links_t.p0.plot.area()
