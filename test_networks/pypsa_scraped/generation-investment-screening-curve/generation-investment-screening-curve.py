import numpy as np
import pandas as pd

import pypsa

# %%
generators = {
    "coal": {"m": 2, "c": 15},
    "gas": {"m": 12, "c": 10},
    "load-shedding": {"m": 1012, "c": 0},
}

# %%
x = np.linspace(0, 1, 101)
df = pd.DataFrame({k: v["c"] + x * v["m"] for k, v in generators.items()}, index=x)
df.plot(ylim=[0, 50], title="Screening Curve")

# %%
n = pypsa.Network()

num_snapshots = 1001
n.snapshots = np.linspace(0, 1, num_snapshots)
n.snapshot_weightings = n.snapshot_weightings / num_snapshots

n.add("Bus", name="bus")

n.add("Load", name="load", bus="bus", p_set=1000 - 1000 * n.snapshots.values)

for gen in generators:
    n.add(
        "Generator",
        name=gen,
        bus="bus",
        p_nom_extendable=True,
        marginal_cost=generators[gen]["m"],
        capital_cost=generators[gen]["c"],
    )

# %%
n.loads_t.p_set.plot.area(title="Load Duration Curve", ylabel="MW")

# %%
n.optimize()
n.objective

# %%
n.generators.p_nom_opt.round(2)

# %%
n.buses_t.marginal_price.plot(title="Price Duration Curve")

# %%
n.buses_t.marginal_price.round(2).sum(axis=1).value_counts()

# %%
n.generators_t.p.plot(ylim=[0, 600], title="Generation Dispatch")

# %%
weights = n.snapshot_weightings.objective
(
    n.generators.p_nom_opt * n.generators.capital_cost
    + weights @ n.generators_t.p * n.generators.marginal_cost
)

# %%
weights @ n.generators_t.p.mul(n.buses_t.marginal_price["bus"], axis=0)

# %%
n.generators.p_nom_extendable = False
n.generators.p_nom = n.generators.p_nom_opt

# %%
n.optimize()

# %%
n.buses_t.marginal_price.plot(title="Price Duration Curve")

# %%
n.buses_t.marginal_price.sum(axis=1).value_counts()

# %%
(
    n.generators.p_nom * n.generators.capital_cost
    + weights @ n.generators_t.p * n.generators.marginal_cost
)

# %%
weights @ n.generators_t.p.mul(n.buses_t.marginal_price["bus"], axis=0)
