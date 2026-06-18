import matplotlib.pyplot as plt
import pandas as pd

import pypsa

plt.style.use("bmh")

# %%
n = pypsa.Network(
    "https://tubcloud.tu-berlin.de/s/pzytNg9gtkgPpXc/download/network-cem.nc"
)
n

# %%
n.remove("StorageUnit", "hydrogen storage underground")

# %%
n.add("Bus", "hydrogen")

# %%
n.add(
    "Link",
    "electrolysis",
    bus0="electricity",
    bus1="hydrogen",
    carrier="electrolysis",
    p_nom_extendable=True,
    efficiency=0.7,
    capital_cost=50e3,  # €/MW/a
)

# %%
n.add(
    "Link",
    "fuel cell",
    bus0="hydrogen",
    bus1="electricity",
    carrier="fuel cell",
    p_nom_extendable=True,
    efficiency=0.5,
    capital_cost=120e3,  # €/MW/a
)

# %%
n.add(
    "Store",
    "hydrogen storage",
    bus="hydrogen",
    carrier="hydrogen storage",
    capital_cost=140,  # €/MWh/a
    e_nom_extendable=True,
    e_cyclic=True,  # cyclic state of charge
)

# %%
p_set = n.loads_t.p_set["demand"].mean()

n.add("Load", "hydrogen demand", bus="hydrogen", carrier="hydrogen", p_set=p_set)  # MW

p_set

# %%
n.add("Bus", "heat")

url = "https://tubcloud.tu-berlin.de/s/mSkHERH8fJCKNXx/download/heat-load-example.csv"
p_set = pd.read_csv(url, index_col=0, parse_dates=True).squeeze()

n.add("Load", "heat demand", carrier="heat", bus="heat", p_set=p_set)

n.loads_t.p_set.div(1e3).plot(figsize=(12, 4), ylabel="GW")


# %%
def cop(t_source, t_sink=55):
    delta_t = t_sink - t_source
    return 6.81 - 0.121 * delta_t + 0.000630 * delta_t**2


url = "https://tubcloud.tu-berlin.de/s/S4jRAQMP5Te96jW/download/ninja_weather_country_DE_merra-2_population_weighted.csv"
temp = pd.read_csv(url, skiprows=2, index_col=0, parse_dates=True).loc[
    "2015", "temperature"
][::4]

cop(temp).plot(figsize=(10, 2), ylabel="COP")

# %%
plt.scatter(temp, cop(temp))
plt.xlabel("temperature [°C]")
plt.ylabel("COP [-]")

# %%
n.add(
    "Link",
    "heat pump",
    carrier="heat pump",
    bus0="electricity",
    bus1="heat",
    efficiency=cop(temp),
    p_nom_extendable=True,
    capital_cost=3e5,  # €/MWe/a
)

# %%
n.add(
    "Link",
    "resistive heater",
    carrier="resistive heater",
    bus0="electricity",
    bus1="heat",
    efficiency=0.9,
    capital_cost=1e4,  # €/MWe/a
    p_nom_extendable=True,
)

# %%
n.remove("GlobalConstraint", "CO2Limit")

# %%
n.add("Bus", "gas", carrier="gas")

# %%
n.add(
    "Store",
    "gas storage",
    carrier="gas storage",
    e_initial=100e6,  # MWh
    e_nom=100e6,  # MWh
    bus="gas",
    marginal_cost=150,  # €/MWh_th
)

# %%
n.remove("Generator", "OCGT")

# %%
n.add(
    "Link",
    "OCGT",
    bus0="gas",
    bus1="electricity",
    carrier="OCGT",
    p_nom_extendable=True,
    capital_cost=20000,  # €/MW/a
    efficiency=0.4,
)

# %%
n.add(
    "Link",
    "CHP",
    bus0="gas",
    bus1="electricity",
    bus2="heat",
    carrier="CHP",
    p_nom_extendable=True,
    capital_cost=40000,
    efficiency=0.4,
    efficiency2=0.4,
)

# %%
n.add("Bus", "EV", carrier="EV")

# %%
url = "https://tubcloud.tu-berlin.de/s/9r5bMSbzzQiqG7H/download/electric-vehicle-profile-example.csv"
p_set = pd.read_csv(url, index_col=0, parse_dates=True).squeeze()

n.add("Load", "EVa demand", bus="EV", carrier="EV demand", p_set=p_set)

p_set.loc["2015-01-01"].div(1e3).plot(figsize=(4, 4), ylabel="GW")

# %%
n.loads_t.p_set.div(1e3).plot(figsize=(10, 3), ylabel="GW")
plt.axhline(
    n.loads.loc["hydrogen demand", "p_set"] / 1e3, label="hydrogen demand", color="m"
)
plt.legend()

# %%
url = "https://tubcloud.tu-berlin.de/s/E3PBWPfYaWwCq7a/download/electric-vehicle-availability-example.csv"
availability_profile = pd.read_csv(url, index_col=0, parse_dates=True).squeeze()

availability_profile.loc["2015-01-01"].plot(ylim=(0, 1))

# %%
number_cars = 40e6  #  number of EV cars
bev_charger_rate = 0.011  # 3-phase EV charger with 11 kW
p_nom = number_cars * bev_charger_rate

n.add(
    "Link",
    "EV charger",
    bus0="electricity",
    bus1="EV",
    p_nom=p_nom,
    carrier="EV charger",
    p_max_pu=availability_profile,
    efficiency=0.9,
)

# %%
n.add(
    "Link",
    "V2G",
    bus0="EV",
    bus1="electricity",
    p_nom=p_nom,
    carrier="V2G",
    p_max_pu=availability_profile,
    efficiency=0.9,
)

# %%
bev_energy = 0.05  # average battery size of EV in MWh
bev_dsm_participants = 0.5  # share of cars that do smart charging

e_nom = number_cars * bev_energy * bev_dsm_participants

url = "https://tubcloud.tu-berlin.de/s/K62yACBRTrxLTia/download/dsm-profile-example.csv"
dsm_profile = (
    pd.read_csv(url, index_col=0, parse_dates=True).squeeze().shift(2, fill_value=0)
)

dsm_profile.loc["2015-01-01"].plot(figsize=(5, 2), ylim=(0, 1))

# %%
n.add(
    "Store",
    "EV DSM",
    bus="EV",
    carrier="EV battery",
    e_cyclic=True,  # state of charge at beginning = state of charge at the end
    e_nom=e_nom,
    e_min_pu=dsm_profile.loc[n.snapshots],
)

# %%
n.optimize()

# %%
n.statistics()

# %%
n.statistics.capex().div(1e9).sort_values().dropna().plot.bar(
    ylabel="bn€/a", cmap="tab20c", figsize=(7, 3)
)
