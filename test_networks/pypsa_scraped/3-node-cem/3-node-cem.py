import cartopy.crs as ccrs
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import pypsa
from pypsa.costs import annuity

RESOLUTION = 3  # 3-hourly

# %%
n = pypsa.Network()

REGIONS = pd.Index(["VIC", "SA", "NSW"])
LAT = [-37.81, -34.93, -33.87]
LON = [145.01, 138.63, 151.20]
n.add("Bus", REGIONS, x=LON, y=LAT)

# %%
CARRIERS = {
    "solar": "gold",
    "wind": "steelblue",
    "load shedding": "indianred",
    "battery charger": "lightgreen",
    "battery discharger": "lightgreen",
    "battery storage": "grey",
    "battery": "grey",
    "electrolysis": "violet",
    "turbine": "violet",
    "hydrogen storage": "orchid",
    "hydrogen": "orchid",
    "AC": "black",
    "HVDC": "lightseagreen",
    "load": "slategrey",
}

n.add(
    "Carrier",
    CARRIERS.keys(),
    color=CARRIERS.values(),
)

# %%
url = "https://tubcloud.tu-berlin.de/s/oPQbAebrciFBZP2/download/australia-example-p_max_pu.csv"
p_max_pu = pd.read_csv(url, index_col=0, parse_dates=True, header=[0, 1])
display(p_max_pu.head(3))

url = "https://tubcloud.tu-berlin.de/s/8C6d7z3HxE7yZi9/download/australia-example-p_set.csv"
p_set = pd.read_csv(url, index_col=0, parse_dates=True)
display(p_set.head(3))

n.set_snapshots(p_max_pu.index)

# %%
n.add("Load", REGIONS, suffix=" load", bus=REGIONS, p_set=p_set, carrier="load")

# %%
p_max_pu_wind = p_max_pu.xs("onwind", level=1, axis=1).rename(
    columns=lambda s: s + " wind"
)

n.add(
    "Generator",
    p_max_pu_wind.columns,
    bus=REGIONS,
    p_max_pu=p_max_pu_wind,
    p_nom_extendable=True,
    capital_cost=annuity(0.05, 30) * 2_000_000,
    marginal_cost=0.5,
    carrier="wind",
)

p_max_pu_solar = p_max_pu.xs("solar", level=1, axis=1).rename(
    columns=lambda s: s + " solar"
)

n.add(
    "Generator",
    p_max_pu_solar.columns,
    bus=REGIONS,
    p_max_pu=p_max_pu_solar,
    p_nom_extendable=True,
    capital_cost=annuity(0.05, 30) * 700_000,
    carrier="solar",
)

# %%
n.add(
    "Generator",
    REGIONS,
    suffix=" load shedding",
    bus=REGIONS,
    p_nom=p_set.max(),
    marginal_cost=3000,
    carrier="load shedding",
)

# %%
n.set_snapshots(n.snapshots[::RESOLUTION])
n.snapshot_weightings.loc[:, :] = RESOLUTION

n.optimize(solver_name="gurobi")

# %%
display(n.statistics.energy_balance().div(1e6).round(2).sort_values())  # TWh

average_cost = (
    (n.statistics.capex().sum() + n.statistics.opex().sum())
    / n.loads_t.p_set.sum().sum()
    / RESOLUTION
)

display(f"Average cost: {average_cost:.2f} AUD/MWh")

# %%
# Create an empty figure with a Cartopy projection
crs = ccrs.PlateCarree()
fig, ax = plt.subplots(figsize=(10, 6), subplot_kw={"projection": crs})

# Use the energy balance statistics to prepare the bus sizes and plot the network
bus_size = n.statistics.energy_balance(groupby=["bus", "carrier"]).droplevel(
    "component"
)
n.plot(ax=ax, bus_size=bus_size / 4e7, margin=0.75, bus_split_circle=True)

# Load the shapefiles and add them to the plot colored by average LMP
prices = n.buses_t.marginal_price.mean()
gdf = gpd.read_file(
    "https://tubcloud.tu-berlin.de/s/4n9PegitETESBGR/download/australia-example-shapes.geojson"
).set_index("index")
gdf.to_crs(crs).plot(ax=ax, column=prices, cmap="RdYlGn_r", vmin=90, vmax=240)

# Add a legend for the LMP color scale
norm = plt.Normalize(vmin=90, vmax=240)
sm = plt.cm.ScalarMappable(cmap="RdYlGn_r", norm=norm)
fig.colorbar(sm, ax=ax, label="LMP [AUD/MWh]", shrink=0.4)

# %%
n.add("Bus", REGIONS, suffix=" hydrogen", carrier="hydrogen", x=LON, y=LAT)

n.add(
    "Link",
    REGIONS,
    suffix=" electrolysis",
    bus0=REGIONS,
    bus1=pd.Index(REGIONS) + " hydrogen",
    carrier="electrolysis",
    p_nom_extendable=True,
    efficiency=0.7,
    capital_cost=annuity(0.05, 25) * 2_500_000,
)

n.add(
    "Link",
    REGIONS,
    suffix=" turbine",
    bus0=pd.Index(REGIONS) + " hydrogen",
    bus1=REGIONS,
    carrier="turbine",
    p_nom_extendable=True,
    efficiency=0.4,
    capital_cost=annuity(0.05, 25) * 2_000_000,
)

n.add(
    "Store",
    REGIONS,
    suffix=" hydrogen storage",
    bus=pd.Index(REGIONS) + " hydrogen",
    carrier="hydrogen storage",
    capital_cost=annuity(0.05, 30) * 80,
    e_nom_extendable=True,
    e_cyclic=True,
)

n.add("Bus", REGIONS, suffix=" battery", carrier="battery", x=LON, y=LAT)

n.add(
    "Link",
    REGIONS,
    suffix=" battery charger",
    bus0=REGIONS,
    bus1=REGIONS + " battery",
    carrier="battery charger",
    p_nom_extendable=True,
    efficiency=0.95,
    capital_cost=annuity(0.05, 10) * 300_000,
)

n.add(
    "Link",
    REGIONS,
    suffix=" battery discharger",
    bus0=REGIONS + " battery",
    bus1=REGIONS,
    carrier="battery discharger",
    p_nom_extendable=True,
    efficiency=0.95,
)

n.add(
    "Store",
    REGIONS,
    suffix=" battery storage",
    bus=REGIONS + " battery",
    carrier="battery storage",
    capital_cost=annuity(0.05, 25) * 250_000,
    e_nom_extendable=True,
    e_cyclic=True,
)


# %%
def battery_constraint(n: pypsa.Network, sns: pd.Index) -> None:
    """Constraint to ensure that the nominal capacity of battery chargers and dischargers are in a fixed ratio."""
    dischargers_i = n.links[n.links.index.str.contains(" discharger")].index
    chargers_i = n.links[n.links.index.str.contains(" charger")].index

    eff = n.links.efficiency[dischargers_i].values
    lhs = n.model["Link-p_nom"].loc[chargers_i]
    rhs = n.model["Link-p_nom"].loc[dischargers_i] * eff

    n.model.add_constraints(lhs == rhs, name="Link-charger_ratio")


n.optimize(extra_functionality=battery_constraint, solver_name="gurobi")

# %%
display(
    n.statistics.energy_balance(bus_carrier="AC").div(1e6).round(2).sort_values()
)  # TWh

average_cost = (
    (n.statistics.capex().sum() + n.statistics.opex().sum())
    / n.loads_t.p_set.sum().sum()
    / RESOLUTION
)

print(f"Average cost: {average_cost:.2f} AUD/MWh")

# %%
bus_size = (
    n.statistics.energy_balance(groupby=["bus", "carrier"])
    .droplevel("component")
    .loc[REGIONS]
)

n.plot(bus_size=bus_size / 4e7, margin=0.75, bus_split_circle=True)

# %%
pdc = (
    n.buses_t.marginal_price["VIC"].sort_values(ascending=False).reset_index(drop=True)
)
pdc.index = np.arange(0, 100, 100 / len(pdc.index))
pdc.plot(
    ylim=[0, 1000], xlim=[0, 100], xlabel="Share of time [%]", ylabel="Price [AUD/MWh]"
)

# %%
connections = [
    ("VIC", "NSW", 700),  # km
    ("VIC", "SA", 650),  # km
    ("NSW", "SA", 1150),  # km
]

for bus0, bus1, length in connections:
    n.add(
        "Link",
        f"{bus0}-{bus1}",
        bus0=bus0,
        bus1=bus1,
        carrier="HVDC",
        p_nom_extendable=True,
        capital_cost=annuity(0.05, 40) * 1_000 * length,
        p_min_pu=-1,  # bidirectional
    )

# %%
n.optimize(extra_functionality=battery_constraint, solver_name="gurobi")

# %%
display(
    n.statistics.energy_balance(bus_carrier="AC").div(1e6).round(2).sort_values()
)  # TWh

average_cost = (
    (n.statistics.capex().sum() + n.statistics.opex().sum())
    / n.loads_t.p_set.sum().sum()
    / RESOLUTION
)

display(f"Average cost: {average_cost:.2f} AUD/MWh")

# %%
bus_size = (
    n.statistics.energy_balance(bus_carrier="AC", groupby=["bus", "carrier"])
    .droplevel("component")
    .loc[REGIONS]
    .drop("HVDC", level="carrier")
)

link_flow = n.links_t.p0.mean()[n.links.carrier == "HVDC"]

link_width = n.links.p_nom_opt[n.links.carrier == "HVDC"]

link_loading = n.links_t.p0.abs().mean()[n.links.carrier == "HVDC"] / link_width

n.plot(
    bus_size=bus_size / 4e7,
    margin=0.75,
    bus_split_circle=True,
    link_flow=link_flow / 50,
    link_width=link_width / 1e3,
    link_color=link_loading,
)

# %%
n.links.query("carrier == 'HVDC'").p_nom_opt.round(2)

# %%
n.links_t.p0.loc[:, n.links.carrier == "HVDC"].rolling("7d").mean().plot(
    ylim=[-2500, 2500], grid=True
)

# %%
n.stores_t.e.filter(like="hydrogen").sum(axis=1).div(1e6).plot(
    ylabel="Hydrogen storage [TWh]", grid=True
)

# %%
n.statistics.energy_balance.iplot.area(bus_carrier="AC")
