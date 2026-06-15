import pypsa

# %%
n = pypsa.Network()

# %%
n.add("Bus", "zone_1")
n.add("Bus", "zone_2")
n.buses

# %%
n.add("Load", "load_1", bus="zone_1", p_set=500)
n.add("Load", "load_2", bus="zone_2", p_set=1500)
n.loads

# %%
n.add(
    "Generator",
    "gen_1",
    bus="zone_1",
    p_nom=2000,
    marginal_cost=10,
    marginal_cost_quadratic=0.005,
)
n.add(
    "Generator",
    "gen_2",
    bus="zone_2",
    p_nom=2000,
    marginal_cost=13,
    marginal_cost_quadratic=0.01,
)
n.generators

# %%
n.add("Line", "line_1", bus0="zone_1", bus1="zone_2", x=0.01, s_nom=400)
n.lines

# %%
n.optimize()

# %%
n.generators_t.p

# %%
n.buses_t.marginal_price

# %%
n.lines_t.p1

# %%
n.buses_t.marginal_price.eval("zone_2 - zone_1") * n.lines_t.p0["line_1"]
