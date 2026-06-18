import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import pypsa

plt.style.use("bmh")

# %%
n = pypsa.examples.model_energy()
n.remove("Generator", "load shedding")


# %%
def get_price_duration(n: pypsa.Network, bus: str = "electricity") -> pd.Series:
    s = (
        n.buses_t.marginal_price[bus]
        .sort_values(ascending=False)
        .reset_index(drop=True)
    )
    s.index = np.arange(0, 100, 100 / len(s.index))
    return s


# %%
days = n.snapshots.normalize().to_series()
one_day_per_month = days.groupby(days.dt.to_period("M")).first().values
snapshots = n.snapshots[n.snapshots.normalize().isin(one_day_per_month)]
n.set_snapshots(snapshots)
n.snapshot_weightings[["objective", "generators"]] *= 5

# %%
n.remove("Load", "demand")
n.add("Load", "demand", bus="electricity", p_set=100)

# %%
n.optimize(solver_name="gurobi")

# %%
fig, ax = plt.subplots()
get_price_duration(n).plot(
    ax=ax,
    ylabel="Clearing Price (€/MWh)",
    xlabel="Fraction of Time (%)",
    label="default",
    legend=True,
)

# %%
capacities = n.statistics.optimal_capacity(round=2).to_frame("inelastic")
capacities

# %%
n.add(
    "Generator",
    "load-shedding",
    bus="electricity",
    carrier="load",
    marginal_cost=1000,
    p_nom=100,
)

# %%
n.optimize(solver_name="gurobi")

# %%
get_price_duration(n).plot(ax=ax, label="VOLL", legend=True)
fig

# %%
capacities["VOLL"] = n.statistics.optimal_capacity(round=2)
capacities

# %%
x = np.linspace(0, 100, 200)
plt.figure(figsize=(8, 4))
plt.plot(x, 2000 - 20 * x)
plt.xlabel("Demand (MW)")
plt.ylabel("Price (€/MWh)")

# %%
n.remove("Generator", "load-shedding")

n.add(
    "Generator",
    "load-shedding",
    bus="electricity",
    carrier="load",
    marginal_cost_quadratic=20 / 2,
    p_nom=100,
)

# %%
n.optimize(solver_name="gurobi")

# %%
get_price_duration(n).plot(ax=ax, label="linear-elastic", legend=True)
fig

# %%
capacities["linear-elastic"] = n.statistics.optimal_capacity(round=2)
capacities

# %%
# Parameters of linear demand curve
a, b = 2000, 20

# Set share of elastic demand, here 20%
share_elastic = 0.2

# Get total demand
D = n.loads.loc["demand", "p_set"]

# Set load-shedding parameters according to elasticity
n.generators.at["load-shedding", "p_nom_max"] = share_elastic * D
n.generators.at["load-shedding", "marginal_cost_quadratic"] = b / (2 * share_elastic)

# %%
plt.figure(figsize=(8, 4))
plt.plot(
    [D * (1 - share_elastic), D], [a, 0], marker="o", label="Linear elastic segment"
)
plt.vlines(
    D * (1 - share_elastic),
    ymin=a,
    ymax=a * 1.2,
    linestyles="dashed",
    label="Perfectly inelastic segment",
)
plt.xlim(left=0)
plt.ylim(top=a * 1.2)
plt.xlabel("Demand (MW)")
plt.ylabel("Price (€/MWh)")
plt.legend(loc="upper left")

# %%
n.optimize(solver_name="gurobi")

# %%
get_price_duration(n).plot(ax=ax, label="linear-elastic 20%", legend=True)
fig

# %%
plt.figure(figsize=(8, 4))
x = [0, 95, 100, 110]
y = [8000, 400, 200, 0]
plt.plot(x, y, marker="o", label="Piecewise linear approximation of log-log")
plt.xlim(left=0)
plt.ylim(a * -0.05, a * 1.2)
plt.xlabel("Demand (MW)")
plt.ylabel("Price (€/MWh)")
plt.legend(loc="upper left")

# %%
n.remove("Generator", "load-shedding")

# Add load-shedding generators to model segments from right to left (cheapest first)
p_nom = [10, 5, 95]

# Quadratic marginal costs
mc2 = 0.5 * np.array([20, 40, 80])

# Marginal costs (lower bound of each segment)
mc_right = 0
mc_middle = mc_right + 2 * mc2[0] * p_nom[0]
mc_left = mc_middle + 2 * mc2[1] * p_nom[1]

n.add(
    "Generator",
    name=["load-shedding-right", "load-shedding-middle", "load-shedding-left"],
    bus="electricity",
    carrier="load",
    p_nom=p_nom,
    marginal_cost_quadratic=mc2,
    marginal_cost=[mc_right, mc_middle, mc_left],
)

# %%
n.optimize(solver_name="gurobi")

# %%
get_price_duration(n).plot(ax=ax, label="log-log approximation", legend=True)
fig
