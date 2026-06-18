import matplotlib.pyplot as plt
import pandas as pd

import pypsa

n = pypsa.Network()
n.add("Bus", "company")
n.add("Load", "demand", bus="company", p_set=25, carrier="load")
n.add("Generator", "grid", bus="company", p_nom=30, marginal_cost=150, carrier="grid")

# %%
p_max_pu = pd.read_csv(
    "https://model.energy/data/time-series-f17c3736a2719ce7da58484180d89e2d.csv",
    index_col=0,
    parse_dates=True,
)["onwind"]

start_date = "2011-03-01 00:00:00"
end_date = "2011-03-03 23:00:00"

p_max_pu_select = p_max_pu[start_date:end_date]
p_max_pu_select.plot(ylabel="Capacity Factor")

# %%
n.set_snapshots(p_max_pu_select.index)

# %%
n.add(
    "Generator",
    "onwind",
    bus="company",
    p_max_pu=p_max_pu_select,
    p_nom=200,
    carrier="onwind",
)

n.add(
    "StorageUnit",
    "battery",
    bus="company",
    p_nom=20,
    carrier="battery",
    efficiency_store=0.95,
    efficiency_dispatch=0.95,
    max_hours=8,
)

# %%
m = n.copy()

# %%
n.optimize()

# %%
n_rh_24_0 = m.copy()
n_rh_24_0.optimize.optimize_with_rolling_horizon(
    horizon=24, overlap=0, log_to_console=False
)

# %%
supply_comparison = pd.concat(
    {
        "Perfect Foresight": n.statistics.supply(),
        "Rolling Horizon": n_rh_24_0.statistics.supply(),
    },
    axis=1,
).round(2)
supply_comparison

# %%
fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True)

ax1.plot(
    n.snapshots,
    n.storage_units_t.state_of_charge.loc[n.snapshots],
    label="Perfect Foresight",
)
ax1.plot(
    n_rh_24_0.snapshots,
    n_rh_24_0.storage_units_t.state_of_charge.loc[n_rh_24_0.snapshots],
    label="Rolling Horizon (24, 0)",
)
ax1.set_ylabel("State of Charge (MWh)")
ax1.set_title("Battery State of Charge")
ax1.legend(loc="upper left")

ax2.plot(p_max_pu_select.index, p_max_pu_select.values)
ax2.set_ylabel("Capacity Factor")
ax2.set_title("Onshore Wind Capacity Factor")

# %%
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7))

# Top subplot - Perfect Foresight Network
n.statistics.energy_balance(groupby_time=False).droplevel(0).groupby(
    "carrier"
).sum().drop("load").T.plot(
    ax=ax1,
    title="Dispatch - Perfect Foresight",
)
ax1.axhline(y=25, color="k", linestyle="--", label="Load")
ax1.axhline(y=0, color="k", linestyle=":")
ax1.set_ylabel("MW")
ax1.legend(ncol=4)

# Bottom subplot - Rolling Horizon Network
n_rh_24_0.statistics.energy_balance(groupby_time=False).droplevel(0).groupby(
    "carrier"
).sum().drop("load").T.plot(
    ax=ax2,
    title="Dispatch - Rolling Horizon",
)
ax2.axhline(y=25, color="k", linestyle="--", label="Load")
ax2.axhline(y=0, color="k", linestyle=":")
ax2.set_ylabel("MW")
ax2.legend(ncol=4)

# %%
configs = [(12, 0), (24, 2), (28, 4), (36, 12), (48, 24)]
scenario_names = (
    ["Perfect Foresight"] + ["RH (24,0)"] + [f"RH ({h},{o})" for h, o in configs]
)

results = {}
results["Perfect Foresight"] = n
results["RH (24,0)"] = n_rh_24_0

for h, o in configs:
    name = f"RH ({h},{o})"
    n_temp = m.copy()
    n_temp.optimize.optimize_with_rolling_horizon(
        horizon=h, overlap=o, log_to_console=False
    )
    results[name] = n_temp

# %%
supply_comparison = pd.concat(
    [results[s].statistics.supply() for s in scenario_names], axis=1
)
supply_comparison.columns = scenario_names
supply_comparison

# %%
fig, ax = plt.subplots(figsize=(10, 6))

for i, s in enumerate(scenario_names):
    ax.plot(
        results[s].snapshots,
        results[s].storage_units_t.state_of_charge.loc[results[s].snapshots],
        label=s,
        ls="-" if i == 0 else "--",
    )

ax.legend()
ax.set_ylabel("State of Charge (MWh)")

# %%
opex_comparison = pd.concat(
    [results[s].statistics.opex() for s in scenario_names], axis=1
)
opex_comparison.columns = scenario_names
opex_comparison_diff = round(
    (opex_comparison - results["Perfect Foresight"].statistics.opex().iloc[0]) / 1e3, 2
)
opex_comparison_diff
