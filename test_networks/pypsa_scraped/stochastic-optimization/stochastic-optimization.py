import matplotlib.pyplot as plt
import pandas as pd

import pypsa
from pypsa.costs import annuity

# %%
# Scenario definitions - Gas price uncertainty
SCENARIOS = ["low", "med", "high"]
GAS_PRICES = {"low": 40, "med": 70, "high": 100}  # EUR/MWh_th
PROB = {"low": 0.4, "med": 0.3, "high": 0.3}  # Scenario probabilities
BASE = "low"  # Base scenario for network construction

# System parameters
FREQ = "3h"  # Time resolution
LOAD_MW = 1  # Constant load (MW)

# Time series data URL
TS_URL = (
    "https://tubcloud.tu-berlin.de/s/pKttFadrbTKSJKF/download/time-series-lecture-2.csv"
)

# Load and process time series data
ts = pd.read_csv(TS_URL, index_col=0, parse_dates=True)
ts = ts.resample(FREQ).asfreq()  # Resample to 3-hour resolution


# Technology data: investment costs, efficiencies, marginal costs
TECH = {
    "solar": {"profile": "solar", "inv": 1e6, "m_cost": 0.01},
    "wind": {"profile": "onwind", "inv": 2e6, "m_cost": 0.02},
    "gas": {"inv": 7e5, "eff": 0.6},
    "lignite": {"inv": 1.3e6, "eff": 0.4, "m_cost": 130},
}

# Financial parameters
FOM, DR, LIFE = 3.0, 0.03, 25  # Fixed O&M (%), discount rate, lifetime (years)

# Calculate annualized capital costs
for cfg in TECH.values():
    cfg["fixed_cost"] = (annuity(DR, LIFE) + FOM / 100) * cfg["inv"]


COLOR_MAP = {
    "solar": "gold",
    "wind": "skyblue",
    "gas": "brown",
    "lignite": "black",
}


# %%
def build_network(gas_price: float) -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(ts.index)
    n.snapshot_weightings = pd.Series(int(FREQ[:-1]), index=ts.index)  # 3-hour weights

    # Add bus and load
    n.add("Bus", "DE")
    n.add("Load", "DE_load", bus="DE", p_set=LOAD_MW)

    # Add renewable generators (variable renewable energy)
    for tech in ["solar", "wind"]:
        cfg = TECH[tech]
        n.add(
            "Generator",
            tech,
            bus="DE",
            p_nom_extendable=True,
            p_max_pu=ts[cfg["profile"]],  # Renewable availability profile
            capital_cost=cfg["fixed_cost"],
            marginal_cost=cfg["m_cost"],
        )

    # Add conventional generators (dispatchable)
    for tech in ["gas", "lignite"]:
        cfg = TECH[tech]
        # Gas marginal cost depends on gas price and efficiency
        mc = (gas_price / cfg.get("eff")) if tech == "gas" else cfg["m_cost"]
        n.add(
            "Generator",
            tech,
            bus="DE",
            p_nom_extendable=True,
            efficiency=cfg.get("eff"),
            capital_cost=cfg["fixed_cost"],
            marginal_cost=mc,
        )
    return n


# %%
caps_det = pd.DataFrame(index=SCENARIOS, columns=TECH.keys())
objs_det = pd.Series(index=SCENARIOS)

for sc in SCENARIOS:
    n = build_network(GAS_PRICES[sc])
    n.optimize()
    caps_det.loc[sc] = n.generators.p_nom_opt
    objs_det.loc[sc] = n.objective

# %%
# Visualize deterministic results
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

colors = [COLOR_MAP.get(c, "gray") for c in caps_det.columns]
caps_det.plot(kind="bar", stacked=True, ax=ax1, color=colors)
ax1.set_title("Deterministic Capacity Mix by Scenario")
ax1.set_ylabel("Capacity (MW)")
ax1.legend(loc="upper left")

(objs_det / 1e6).plot(kind="bar", ax=ax2, color="steelblue")
ax2.set_title("Deterministic Total Costs by Scenario")
ax2.set_ylabel("Total Cost (M€/year)")

# %%
n_stoch = build_network(GAS_PRICES[BASE])
n_stoch.set_scenarios(PROB)

# %%
for sc in SCENARIOS:
    n_stoch.generators.loc[(sc, "gas"), "marginal_cost"] = (
        GAS_PRICES[sc] / n_stoch.generators.loc[(sc, "gas"), "efficiency"]
    )

# %%
n_stoch.optimize()

print(f"Total expected cost: {n_stoch.objective / 1e6:.3f} M€/year")

caps_api = n_stoch.generators.p_nom_opt.xs(BASE, level="scenario")
obj_api = n_stoch.objective

# %%
caps_comparison = caps_det.copy()
caps_comparison.loc["Stochastic"] = caps_api

objs_comparison = objs_det.copy()
objs_comparison.loc["Stochastic"] = obj_api

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5))

colors = [COLOR_MAP.get(c, "gray") for c in caps_comparison.columns]
caps_comparison.plot(kind="bar", stacked=True, ax=ax1, color=colors)
ax1.set_title("Capacity Mix: Deterministic vs. Stochastic")
ax1.set_ylabel("Capacity (MW)")
ax1.legend(loc="upper left")

(objs_comparison / 1e6).plot(kind="bar", ax=ax2, color="steelblue")
ax2.set_title("Total Cost: Deterministic vs. Stochastic")
ax2.set_ylabel("Total Cost (M€/year)")

# %%
# Wait-and-See (perfect information) expected cost
ws_cost = sum(objs_det[sc] * PROB[sc] for sc in SCENARIOS)
print(f"Wait-and-See (WS) cost: {ws_cost / 1e6:.3f} M€/year")

# %%
# Expected Value of Perfect Information
evpi = obj_api - ws_cost
print(f"EVPI (SP - WS): {evpi / 1e6:.3f} M€/year")

# %%
# Expected gas price
expected_gas_price = sum(GAS_PRICES[sc] * PROB[sc] for sc in SCENARIOS)
print(f"Expected gas price: {expected_gas_price:.1f} EUR/MWh_th")

# %%
# Report stochastic programming (SP) cost
print(f"Stochastic Prog (SP) cost: {obj_api / 1e6:.3f} M€/year")

# %%
# Solve deterministic problem with expected gas price (EEV solution)
n_eev = build_network(expected_gas_price)
n_eev.optimize()
eev_capacities = n_eev.generators.p_nom_opt

# Evaluate EEV capacities under each scenario
eev_costs = []
for sc in SCENARIOS:
    n_eval = build_network(GAS_PRICES[sc])
    for tech in TECH.keys():
        n_eval.generators.loc[tech, "p_nom_max"] = eev_capacities[tech]
        n_eval.generators.loc[tech, "p_nom_min"] = eev_capacities[tech]
    n_eval.optimize()
    eev_costs.append(n_eval.objective)

eev_expected_cost = sum(eev_costs[i] * PROB[sc] for i, sc in enumerate(SCENARIOS))
print(f"Expected Value (EEV) cost: {eev_expected_cost / 1e6:.3f} M€/year")

# %%
# Value of Stochastic Solution
vss = eev_expected_cost - obj_api
print(f"VSS (EEV - SP): {vss / 1e6:.3f} M€/year")

# %%
print("\nTheoretical Ordering Check:")
print(f"  WS ≤ SP: {ws_cost <= obj_api} ({ws_cost:.0f} ≤ {obj_api:.0f})")
print(
    f"  SP ≤ EEV: {obj_api <= eev_expected_cost} ({obj_api:.0f} ≤ {eev_expected_cost:.0f})"
)
print(f"  EVPI ≥ 0: {evpi >= 0} ({evpi:.0f} ≥ 0)")
print(f"  VSS ≥ 0: {vss >= 0} ({vss:.0f} ≥ 0)")

# %%
costs_voi = pd.Series(
    {
        "Wait-and-See\n(Perfect Info)": ws_cost,
        "Stochastic\nProgramming": obj_api,
        "Expected Value\n(Ignore Uncertainty)": eev_expected_cost,
    }
)


fig, ax1 = plt.subplots(figsize=(7, 5))

# Cost comparison
(costs_voi / 1e6).plot(kind="bar", ax=ax1, color=["green", "blue", "red"], alpha=0.7)
ax1.set_title("Value of Information: Cost Comparison", fontsize=14, fontweight="bold")
ax1.set_ylabel("Total Cost (M€/year)")
ax1.tick_params(axis="x", rotation=45)
ax1.grid(True, alpha=0.3)

# Add EVPI and VSS arrows
ax1.annotate(
    "",
    xy=(0, ws_cost / 1e6),
    xytext=(1, obj_api / 1e6),
    arrowprops={"arrowstyle": "<->", "color": "purple", "lw": 2},
)
ax1.text(
    0.5,
    (ws_cost + obj_api) / (2 * 1e6),
    "EVPI",
    color="purple",
    fontweight="bold",
    fontsize=10,
    ha="center",
)

ax1.annotate(
    "",
    xy=(1, obj_api / 1e6),
    xytext=(2, eev_expected_cost / 1e6),
    arrowprops={"arrowstyle": "<->", "color": "orange", "lw": 2},
)
ax1.text(
    1.5,
    (eev_expected_cost + obj_api) / (2 * 1e6),
    "VSS",
    color="orange",
    fontweight="bold",
    fontsize=10,
    ha="center",
)
