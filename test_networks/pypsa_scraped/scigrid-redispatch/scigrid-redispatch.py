import cartopy.crs as ccrs
import matplotlib.pyplot as plt

import pypsa

# %%
o = pypsa.examples.scigrid_de()
o.lines.s_max_pu = 0.7
o.lines.loc[["316", "527", "602"], "s_nom"] = 1715
o.set_snapshots([o.snapshots[12]])

# %%
n = o.copy()  # for redispatch model
m = o.copy()  # for market model

# %%
o.plot();

# %%
o.optimize()

# %%
zones = (n.buses.y > 51).map(lambda x: "North" if x else "South")

# %%
for c in m.components:
    if c.name not in m.one_port_components:
        continue
    c.static.bus = c.static.bus.map(zones)

for c in m.components:
    if c.name not in m.branch_components:
        continue
    c.static.bus0 = c.static.bus0.map(zones)
    c.static.bus1 = c.static.bus1.map(zones)
    internal = c.static.bus0 == c.static.bus1
    m.remove(c.name, c.static.loc[internal].index)

m.remove("Bus", m.buses.index)
m.add("Bus", ["North", "South"]);

# %%
m.optimize()

# %%
m.buses_t.marginal_price

# %%
p = m.generators_t.p / m.generators.p_nom
n.generators_t.p_min_pu = p
n.generators_t.p_max_pu = p

# %%
g_up = n.generators.copy()
g_down = n.generators.copy()

g_up.index = g_up.index.map(lambda x: x + " ramp up")
g_down.index = g_down.index.map(lambda x: x + " ramp down")

up = (
    m.get_switchable_as_dense("Generator", "p_max_pu") * m.generators.p_nom
    - m.generators_t.p
).clip(0) / m.generators.p_nom
down = -m.generators_t.p / m.generators.p_nom

up.columns = up.columns.map(lambda x: x + " ramp up")
down.columns = down.columns.map(lambda x: x + " ramp down")

n.add("Generator", g_up.index, p_max_pu=up, **g_up.drop("p_max_pu", axis=1))

n.add(
    "Generator",
    g_down.index,
    p_min_pu=down,
    p_max_pu=0,
    **g_down.drop(["p_max_pu", "p_min_pu"], axis=1),
);

# %%
n.optimize()

# %%
fig, axs = plt.subplots(
    1, 3, figsize=(20, 10), subplot_kw={"projection": ccrs.AlbersEqualArea()}
)

market = (
    n.generators_t.p[m.generators.index]
    .T.squeeze()
    .groupby(n.generators.bus)
    .sum()
    .div(2e4)
)
n.plot(ax=axs[0], bus_size=market, title="2 bidding zones market simulation")

redispatch_up = (
    n.generators_t.p.filter(like="ramp up")
    .T.squeeze()
    .groupby(n.generators.bus)
    .sum()
    .div(2e4)
)
n.plot(ax=axs[1], bus_size=redispatch_up, bus_color="blue", title="Redispatch: ramp up")

redispatch_down = (
    n.generators_t.p.filter(like="ramp down")
    .T.squeeze()
    .groupby(n.generators.bus)
    .sum()
    .div(-2e4)
)
n.plot(
    ax=axs[2],
    bus_size=redispatch_down,
    bus_color="red",
    title="Redispatch: ramp down / curtail",
);

# %%
grouper = n.generators.index.str.split(" ramp", expand=True).get_level_values(0)

n.generators_t.p.T.groupby(grouper).sum().squeeze()

# %%
n.generators.loc[n.generators.index.str.contains("ramp up"), "marginal_cost"] *= 2

# %%
n.generators.loc[n.generators.index.str.contains("ramp down"), "marginal_cost"] *= -0.5

# %%
n.optimize()
