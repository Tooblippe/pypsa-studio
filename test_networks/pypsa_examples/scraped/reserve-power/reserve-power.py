import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import pypsa

# %%
n_basic = pypsa.Network()
n_basic.add("Carrier", name="carrier1")
n_basic.add("Bus", name="bus1", carrier="carrier1")

# add generators with increasing marginal cost
n_basic.add("Generator", name="gen1", bus="bus1", p_nom=10, marginal_cost=1)
n_basic.add("Generator", name="gen2", bus="bus1", p_nom=10, marginal_cost=2)
n_basic.add("Generator", name="gen3", bus="bus1", p_nom=10, marginal_cost=3)
n_basic.add("Generator", name="gen4", bus="bus1", p_nom=10, marginal_cost=4)

# create 48 snapshots
snapshots = np.arange(1, 49)
n_basic.set_snapshots(snapshots)

# create load
load_max = 30
load_profile = np.sin(snapshots / 12 * np.pi) + 3.5
load_profile = load_profile / load_profile.max() * load_max
n_basic.add("Load", name="load1", bus="bus1", p_set=load_profile)

# %%
n_reserve = n_basic.copy()

# %%
n_basic.optimize()

# %%
n_basic.generators_t["p"].plot.area(lw=0).legend(
    loc="upper left", bbox_to_anchor=(1.0, 1.0)
)
plt.show()

# %%
n_reserve.optimize.create_model()
n_reserve.model

# %%
v_rp = n_reserve.model.add_variables(
    lower=0,
    coords=[n_reserve.snapshots, n_reserve.generators.index],
    name="Generator-p_reserve",
)
v_rp

# %%
reserve_req = 10

c_sum = n_reserve.model.add_constraints(
    v_rp.sum("name") >= reserve_req, name="GlobalConstraint-sum_of_reserves"
)
c_sum

# %%
a = 1

c_rpos = n_reserve.model.add_constraints(
    v_rp
    <= -n_reserve.model.variables["Generator-p"] + a * n_reserve.generators["p_nom"],
    name="Generator-reserve_upper_limit",
)
c_rpos

# %%
b = 0.7

c_rneg = n_reserve.model.add_constraints(
    v_rp <= b * n_reserve.model.variables["Generator-p"],
    name="Generator-reserve_lower_limit",
)
c_rneg

# %%
n_reserve.model

# %%
n_reserve.optimize.solve_model()

# %%
fig, axs = plt.subplots(1, 2, sharey=True, figsize=(10, 5))
n_reserve.generators_t["p"].plot.area(
    ax=axs[0], title="p", legend=False, ylabel="p [MW]"
)
n_reserve.generators_t["p_reserve"].plot.area(ax=axs[1], title="p_reserve")
plt.tight_layout()
plt.show()

# %%
n_reserve.generators_t["p_reserve"].mean().plot(
    kind="bar", ylabel="mean(p_reserve) [MW]"
)
plt.show()

# %%
fig, axs = plt.subplots(1, 2, sharex=True, sharey=True, figsize=(10, 4))
for i, (n, r) in enumerate([(n_basic, 0), (n_reserve, reserve_req)]):
    n.generators_t["p"].plot.area(
        ax=axs[i], ylabel="p [MW]", title=f"{r} MW reserve required", legend=False, lw=0
    )

plt.tight_layout()
plt.show()

# %%
data = pd.concat(
    [n.generators_t.get("p").mean() for n in [n_basic, n_reserve]],
    axis=1,
    keys=["0 MW", f"{reserve_req} MW"],
)
data.plot(kind="bar", ylabel="mean(p) [MW]")
plt.show()
