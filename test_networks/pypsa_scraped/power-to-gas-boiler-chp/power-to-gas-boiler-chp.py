import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import pypsa

# %%
nom_r = 1.0
c_m = 0.75
c_v = 0.15

# %%
fig, ax = plt.subplots()

t = 0.01
ph = np.arange(0, 1.0001, t)

ax.plot(ph, c_m * ph, color="k")
ax.set_xlabel("P_heat_out")
ax.set_ylabel("P_elec_out")
ax.grid(True)

ax.set_xlim([0, 1.1])
ax.set_ylim([0, 1.1])
ax.text(0.1, 0.7, "Allowed output", color="gray")
ax.plot(ph, 1 - c_v * ph, color="k")

for i in range(1, 10):
    k = 0.1 * i
    x = np.arange(0, k / (c_m + c_v), t)
    ax.plot(x, k - c_v * x, color="orange", linestyle="--", linewidth=0.75)

ax.text(0.05, 0.41, "iso-fuel-lines", color="orange", rotation=-7)
ax.fill_between(ph, c_m * ph, 1 - c_v * ph, facecolor="#ddd")

# %%
n = pypsa.Network()
n.set_snapshots(pd.date_range("2025-01-01 00:00", "2025-01-01 03:00", freq="h"))

n.add("Bus", "0 power", carrier="AC")
n.add("Bus", "0 gas", carrier="gas")

n.add("Carrier", ["wind", "gas"])

n.add(
    "Generator",
    "wind turbine",
    bus="0 power",
    carrier="wind",
    p_nom_extendable=True,
    p_max_pu=[0.0, 0.2, 0.7, 0.4],
    capital_cost=1000,
)

n.add("Load", "load", bus="0 power", p_set=5)

n.add(
    "Link",
    "power-to-gas",
    bus0="0 power",
    bus1="0 gas",
    efficiency=0.6,
    capital_cost=1000,
    p_nom_extendable=True,
)

n.add(
    "Link",
    "generator",
    bus0="0 gas",
    bus1="0 power",
    efficiency=0.468,
    capital_cost=400,
    p_nom_extendable=True,
)

n.add("Store", "gas depot", bus="0 gas", e_cyclic=True, e_nom=1000)

# %%
n.add("Bus", "0 heat", carrier="heat")

n.add("Carrier", "heat")

n.add("Load", "heat load", bus="0 heat", p_set=10)

n.add(
    "Link",
    "boiler",
    bus0="0 gas",
    bus1="0 heat",
    efficiency=0.9,
    capital_cost=300,
    p_nom_extendable=True,
)

n.add("Store", "water tank", bus="0 heat", e_cyclic=True, e_nom_extendable=True)

# %%
# Guarantees ISO fuel lines, i.e. fuel consumption p_b0 + p_g0 = constant along p_g1 + c_v p_b1 = constant (b=boiler, g=generator)
n.links.at["boiler", "efficiency"] = n.links.at["generator", "efficiency"] / c_v
boiler_eff = float(n.links.at["boiler", "efficiency"])
generator_eff = float(n.links.at["generator", "efficiency"])

m = n.optimize.create_model()

p = m.variables["Link-p"]
p_nom = m.variables["Link-p_nom"]

# Guarantees heat output and electric output nominal powers are proportional
m.add_constraints(
    generator_eff * nom_r * p_nom.loc["generator"] - boiler_eff * p_nom.loc["boiler"]
    == 0,
    name="heat-power output proportionality",
)

# Guarantees c_m p_b1 <= p_g1
m.add_constraints(
    p.loc[:, "boiler"] * c_m * boiler_eff - p.loc[:, "generator"] * generator_eff <= 0,
    name="backpressure",
)

# Guarantees p_g1 +c_v p_b1 <= p_g1_nom
m.add_constraints(
    p.loc[:, "boiler"] + p.loc[:, "generator"] - p_nom.loc["generator"] <= 0,
    name="top_iso_fuel_line",
)

n.optimize.solve_model(log_to_console=False)

# %%
n.objective

# %%
n.links.p_nom_opt

# %%
display(4 * 10 / 3 / float(n.links.at["boiler", "efficiency"]))
display(28.490028 * 0.15)

# %%
n.links_t.p0.round(2)

# %%
n.links_t.p1.round(2)

# %%
pd.DataFrame({attr: n.stores_t[attr]["gas depot"] for attr in ["p", "e"]}).round(2)

# %%
pd.DataFrame({attr: n.stores_t[attr]["water tank"] for attr in ["p", "e"]}).round(2)

# %%
pd.DataFrame({attr: n.links_t[attr]["boiler"] for attr in ["p0", "p1"]}).round(2)

# %%
eta_elec = n.links.at["generator", "efficiency"]

r = 1 / c_m

# P_h = r*P_e
(1 + r) / ((1 / eta_elec) * (1 + c_v * r))
