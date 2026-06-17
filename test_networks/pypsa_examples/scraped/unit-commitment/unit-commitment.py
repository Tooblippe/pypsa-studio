import pandas as pd

import pypsa

# %%
nu = pypsa.Network(snapshots=range(4))

nu.add("Bus", "bus")

nu.add(
    "Generator",
    "coal",
    bus="bus",
    committable=True,
    p_min_pu=0.3,
    marginal_cost=20,
    p_nom=10_000,
)

nu.add(
    "Generator",
    "gas",
    bus="bus",
    committable=True,
    marginal_cost=70,
    p_min_pu=0.1,
    p_nom=1_000,
)

nu.add("Load", "load", bus="bus", p_set=[4_000, 6_000, 5_000, 800])

# %%
nu.optimize()

# %%
nu.generators_t.status

# %%
nu.generators_t.p

# %%
nu = pypsa.Network(snapshots=range(4))

nu.add("Bus", "bus")

nu.add(
    "Generator",
    "coal",
    bus="bus",
    committable=True,
    p_min_pu=0.3,
    marginal_cost=20,
    p_nom=10000,
)

nu.add(
    "Generator",
    "gas",
    bus="bus",
    committable=True,
    stand_by_cost=50,
    marginal_cost=70,
    p_min_pu=0.1,
    up_time_before=0,
    min_up_time=3,
    p_nom=1_000,
)

nu.add("Load", "load", bus="bus", p_set=[4_000, 800, 5_000, 3_000])

# %%
nu.optimize()

# %%
nu.generators_t.status

# %%
nu.objective

# %%
nu.generators_t.p

# %%
nu = pypsa.Network(snapshots=range(4))

nu.add("Bus", "bus")

nu.add(
    "Generator",
    "coal",
    bus="bus",
    committable=True,
    p_min_pu=0.3,
    marginal_cost=20,
    min_down_time=2,
    down_time_before=1,
    p_nom=10_000,
)

nu.add(
    "Generator",
    "gas",
    bus="bus",
    committable=True,
    marginal_cost=70,
    p_min_pu=0.1,
    p_nom=4_000,
)

nu.add("Load", "load", bus="bus", p_set=[3_000, 800, 3_000, 8_000])

# %%
nu.optimize()

# %%
nu.objective

# %%
nu.generators_t.status

# %%
nu.generators_t.p

# %%
nu = pypsa.Network(snapshots=range(4))

nu.add("Bus", "bus")

nu.add(
    "Generator",
    "coal",
    bus="bus",
    committable=True,
    p_min_pu=0.3,
    marginal_cost=20,
    min_down_time=2,
    start_up_cost=5_000,
    p_nom=10_000,
)

nu.add(
    "Generator",
    "gas",
    bus="bus",
    committable=True,
    marginal_cost=70,
    p_min_pu=0.1,
    shut_down_cost=25,
    p_nom=4_000,
)

nu.add("Load", "load", bus="bus", p_set=[3_000, 800, 3_000, 8_000])

# %%
nu.optimize()

# %%
nu.objective

# %%
nu.generators_t.status

# %%
nu.generators_t.p

# %%
nu = pypsa.Network(snapshots=range(6))

nu.add("Bus", "bus")

nu.add(
    "Generator",
    "coal",
    bus="bus",
    marginal_cost=20,
    ramp_limit_up=0.1,
    ramp_limit_down=0.2,
    p_nom=10_000,
)

nu.add("Generator", "gas", bus="bus", marginal_cost=70, p_nom=4_000)

nu.add("Load", "load", bus="bus", p_set=[4_000, 7_000, 7_000, 7_000, 7_000, 3_000])

# %%
nu.optimize()

# %%
nu.generators_t.p

# %%
nu = pypsa.Network(snapshots=range(6))

nu.add("Bus", "bus")

nu.add(
    "Generator",
    "coal",
    bus="bus",
    marginal_cost=20,
    ramp_limit_up=0.1,
    ramp_limit_down=0.2,
    p_nom_extendable=True,
    capital_cost=1e2,
)

nu.add("Generator", "gas", bus="bus", marginal_cost=70, p_nom=4000)

nu.add("Load", "load", bus="bus", p_set=[4000, 7000, 7000, 7000, 7000, 3000])

# %%
nu.optimize()

# %%
nu.generators.p_nom_opt

# %%
nu.generators_t.p

# %%
nu = pypsa.Network(snapshots=range(7))

nu.add("Bus", "bus")

# Can get bad interactions if SU > RU and p_min_pu; similarly if SD > RD
nu.add(
    "Generator",
    "coal",
    bus="bus",
    marginal_cost=20,
    committable=True,
    p_min_pu=0.05,
    initial_status=0,
    ramp_limit_start_up=0.1,
    ramp_limit_up=0.2,
    ramp_limit_down=0.25,
    ramp_limit_shut_down=0.15,
    p_nom=10_000,
)

nu.add("Generator", "gas", bus="bus", marginal_cost=70, p_nom=10_000)

nu.add("Load", "load", bus="bus", p_set=[0, 200, 7_000, 7_000, 7_000, 2_000, 0])

# %%
nu.optimize()

# %%
nu.generators_t.p

# %%
nu.generators_t.status

# %%
sets_of_snapshots = 6
p_set = [4_000, 5_000, 700, 800, 4_000]

nu = pypsa.Network(snapshots=range(len(p_set) * sets_of_snapshots))

nu.add("Bus", "bus")

nu.add(
    "Generator",
    "coal",
    bus="bus",
    committable=True,
    p_min_pu=0.3,
    marginal_cost=20,
    min_down_time=2,
    min_up_time=3,
    up_time_before=1,
    ramp_limit_up=1,
    ramp_limit_down=1,
    ramp_limit_start_up=1,
    ramp_limit_shut_down=1,
    shut_down_cost=150,
    start_up_cost=200,
    p_nom=10_000,
)

nu.add(
    "Generator",
    "gas",
    bus="bus",
    committable=True,
    marginal_cost=70,
    p_min_pu=0.1,
    up_time_before=2,
    min_up_time=3,
    shut_down_cost=20,
    start_up_cost=50,
    p_nom=1_000,
)

nu.add("Load", "load", bus="bus", p_set=p_set * sets_of_snapshots)

# %%
overlap = 2
for i in range(sets_of_snapshots):
    snapshots = nu.snapshots[i * len(p_set) : (i + 1) * len(p_set) + overlap]
    nu.optimize(snapshots=snapshots)

# %%
pd.concat(
    {"Active": nu.generators_t.status.astype(bool), "Output": nu.generators_t.p}, axis=1
)
