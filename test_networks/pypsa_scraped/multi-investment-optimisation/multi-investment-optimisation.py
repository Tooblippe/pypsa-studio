import numpy as np
import pandas as pd

import pypsa

rng = np.random.default_rng()  # Create a random number generator

# %%
n = pypsa.Network()
years = [2020, 2030, 2040, 2050]
freq = 24

snapshots = pd.DatetimeIndex([])
for year in years:
    period = pd.date_range(
        start=f"{year}-01-01 00:00",
        freq=f"{freq}h",
        periods=8760 // freq,
    )
    snapshots = snapshots.append(period)

# convert to multiindex and assign to network
n.snapshots = pd.MultiIndex.from_arrays([snapshots.year, snapshots])
n.investment_periods = years

n.snapshot_weightings

# %%
n.investment_periods

# %%
n.investment_period_weightings["years"] = list(np.diff(years)) + [10]

r = 0.01
T = 0
for period, nyears in n.investment_period_weightings.years.items():
    discounts = [(1 / (1 + r) ** t) for t in range(T, T + nyears)]
    n.investment_period_weightings.at[period, "objective"] = sum(discounts)
    T += nyears
n.investment_period_weightings

# %%
for i in range(3):
    n.add("Bus", f"bus {i}")

# add three lines in a ring
n.add(
    "Line",
    "line 0->1",
    bus0="bus 0",
    bus1="bus 1",
)

n.add(
    "Line",
    "line 1->2",
    bus0="bus 1",
    bus1="bus 2",
    capital_cost=10,
    build_year=2030,
)

n.add(
    "Line",
    "line 2->0",
    bus0="bus 2",
    bus1="bus 0",
)

n.lines["x"] = 0.0001
n.lines["s_nom_extendable"] = True

n.lines

# %%
# add some generators
p_nom_max = pd.Series(
    (rng.uniform() for sn in range(len(n.snapshots))),
    index=n.snapshots,
    name="generator ext 2020",
)

# renewable (can operate 2020, 2030)
n.add(
    "Generator",
    "generator ext 0 2020",
    bus="bus 0",
    p_nom=50,
    build_year=2020,
    lifetime=20,
    marginal_cost=2,
    capital_cost=1,
    p_max_pu=p_nom_max,
    carrier="solar",
    p_nom_extendable=True,
)

# can operate 2040, 2050
n.add(
    "Generator",
    "generator ext 0 2040",
    bus="bus 0",
    p_nom=50,
    build_year=2040,
    lifetime=11,
    marginal_cost=25,
    capital_cost=10,
    carrier="OCGT",
    p_nom_extendable=True,
)

# can operate in 2040
n.add(
    "Generator",
    "generator fix 1 2040",
    bus="bus 1",
    p_nom=50,
    build_year=2040,
    lifetime=10,
    carrier="CCGT",
    marginal_cost=20,
    capital_cost=1,
)

n.generators

# %%
n.add(
    "StorageUnit",
    "storageunit non-cyclic 2030",
    bus="bus 2",
    p_nom=0,
    capital_cost=2,
    build_year=2030,
    lifetime=21,
    cyclic_state_of_charge=False,
    p_nom_extendable=False,
)

n.add(
    "StorageUnit",
    "storageunit periodic 2020",
    bus="bus 2",
    p_nom=0,
    capital_cost=1,
    build_year=2020,
    lifetime=21,
    cyclic_state_of_charge=True,
    cyclic_state_of_charge_per_period=True,
    p_nom_extendable=True,
)

n.storage_units

# %%
load_var = pd.Series(
    100 * rng.random(size=len(n.snapshots)), index=n.snapshots, name="load"
)
n.add("Load", "load 2", bus="bus 2", p_set=load_var)

load_fix = pd.Series(75, index=n.snapshots, name="load")
n.add("Load", "load 1", bus="bus 1", p_set=load_fix)

n.loads_t.p_set.head()

# %%
n.optimize(multi_investment_periods=True)

# %%
c = "Generator"
df = pd.concat(
    {
        period: n.components[c].get_active_assets(period)
        * n.components[c].static.p_nom_opt
        for period in n.investment_periods
    },
    axis=1,
)
df.T.plot.bar(
    stacked=True,
    edgecolor="white",
    width=1,
    ylabel="Capacity (MW)",
    xlabel="Investment Period",
    rot=0,
)

# %%
df = n.generators_t.p.sum(axis=0).T.div(1e3)
df.T.plot.bar(
    stacked=True,
    edgecolor="white",
    width=1,
    ylabel="Generation (GWh)",
    xlabel="Investment Period",
    rot=0,
)
