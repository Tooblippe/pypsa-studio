from numpy import pi

import pypsa

n = pypsa.Network()

n.add("Bus", ["zone_1", "zone_2", "zone_3"], v_nom=11)

# %%
n.add(
    "Load",
    ["load_1", "load_2", "load_3"],
    bus=["zone_1", "zone_2", "zone_3"],
    p_set=[50, 60, 300],
)

n.add(
    "Generator",
    ["gen_A", "gen_B", "gen_C", "gen_D"],
    bus=["zone_1", "zone_1", "zone_2", "zone_3"],
    p_nom=[140, 285, 90, 85],
    marginal_cost=[7.5, 6, 14, 10],
)

n.add(
    "Line",
    ["line_1", "line_2", "line_3"],
    bus0=["zone_1", "zone_1", "zone_2"],
    bus1=["zone_2", "zone_3", "zone_3"],
    s_nom=[126, 250, 130],
    x=[0.02, 0.02, 0.01],
    r=0.01,
)

n.optimize()

# %%
n.model

# %%
n.model.constraints["Bus-nodal_balance"]

# %%
display(n.buses_t.marginal_price)
display(n.generators_t.p)
display(n.lines_t.p0)

# %%
n.optimize.fix_optimal_dispatch()

display(n.generators_t.p_set)
display(n.generators.control)

n.pf()

# %%
display(n.generators_t.p)
display(n.generators_t.q)
display(n.lines_t.q0)
display((n.lines_t.p0 + n.lines_t.p1).sum().sum())  # active power losses

# %%
n.buses_t.v_ang * 180 / pi
