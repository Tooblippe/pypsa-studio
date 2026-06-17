import matplotlib.pyplot as plt
import pandas as pd

import pypsa

# %%
n = pypsa.Network(snapshots=range(6))

n.add("Bus", "bus", carrier="electricity")
n.add("Carrier", "electricity")

# Load profile with zero demand in period 3 - forcing generator to turn off
load_profile = [300, 500, 400, 0, 200, 350]
n.add("Load", "load", bus="bus", p_set=load_profile)

# Add a generator that is BOTH committable AND extendable
n.add(
    "Generator",
    "gas_ccgt",
    bus="bus",
    p_nom_extendable=True,  # Can expand capacity
    committable=True,  # Can be turned on/off
    p_nom_max=1000,  # Maximum capacity that can be built
    p_min_pu=0.3,  # 30% minimum load when running
    marginal_cost=50,
    capital_cost=80_000,  # Cost per MW of capacity
    start_up_cost=500,  # Cost to start the unit
    shut_down_cost=200,  # Cost to shut down the unit
)

# %%
n.optimize(log_to_console=False)

# %%
print(f"Optimal capacity built: {n.generators.p_nom_opt['gas_ccgt']:.1f} MW")

# %%
# Show commitment status and dispatch
results = pd.DataFrame(
    {
        "Load": load_profile,
        "Status": n.generators_t.status["gas_ccgt"],
        "Dispatch": n.generators_t.p["gas_ccgt"],
    }
)
results

# %%
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)

# Plot dispatch vs load
ax1.plot(results.index, results["Load"], "o-", label="Load", color="red")
ax1.bar(
    results.index, results["Dispatch"], alpha=0.7, label="Dispatch", color="steelblue"
)
min_stable = n.generators.p_nom_opt["gas_ccgt"] * 0.3
ax1.axhline(
    y=min_stable,
    color="orange",
    linestyle="--",
    label=f"Min stable gen ({min_stable:.0f} MW)",
)
ax1.set_ylabel("Power [MW]")
ax1.legend()
ax1.set_title("Dispatch Profile")

# Plot commitment status
ax2.bar(results.index, results["Status"], color="green", alpha=0.7)
ax2.set_ylabel("Status (1=ON, 0=OFF)")
ax2.set_xlabel("Hour")
ax2.set_title("Commitment Status")
ax2.set_ylim(-0.1, 1.1)

plt.tight_layout()

# %%
n = pypsa.Network(snapshots=range(11))

n.add("Bus", "bus", carrier="electricity")
n.add("Carrier", "electricity")

# Load profile with low periods to trigger shut-downs
load_profile = [150, 200, 180, 500, 700, 650, 500, 180, 150, 500, 180]
n.add("Load", "load", bus="bus", p_set=load_profile)

# Fast-ramping peaker (expensive to build and run)
n.add(
    "Generator",
    "fast_peaker",
    bus="bus",
    p_nom_extendable=True,
    p_nom_max=800,
    marginal_cost=140,
    capital_cost=2000,
)

# Slow-ramping baseload with commitment
n.add(
    "Generator",
    "slow_baseload",
    bus="bus",
    p_nom_extendable=True,
    committable=True,
    p_nom_max=800,
    p_min_pu=0.6,
    marginal_cost=30,
    capital_cost=200,
    ramp_limit_up=0.6,  # Can ramp up 60% of capacity per hour
    ramp_limit_down=0.6,  # Can ramp down 60% of capacity per hour
    start_up_cost=800,
)

# %%
n.optimize(log_to_console=False)

# %%
print("Optimal Capacities:")
print(n.generators[["p_nom_opt", "ramp_limit_up", "ramp_limit_down"]])

print("\nCommitment status (slow_baseload):")
status = n.generators_t.status["slow_baseload"].round(0)
print(status)

# %%
# Check ramp rates are respected
dispatch = n.generators_t.p["slow_baseload"]
ramps = dispatch.diff().dropna()
p_nom = n.generators.p_nom_opt["slow_baseload"]
ramp_limit = n.generators.ramp_limit_up["slow_baseload"]

print(f"\nSlow baseload capacity: {p_nom:.1f} MW")
print(f"Max allowed ramp ({ramp_limit:.0%}): {p_nom * ramp_limit:.1f} MW/h")
print("\nActual ramps (MW/h):")
print(ramps)

# %%
n.generators_t.p

# %%
# Visualize dispatch and commitment with ramp constraints
fig, (ax1, ax2) = plt.subplots(
    2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
)

n.generators_t.p.plot.area(ax=ax1, alpha=0.7, linewidth=0)
ax1.plot(range(len(load_profile)), load_profile, "k--", linewidth=2, label="Load")
ax1.set_ylabel("Power [MW]")
ax1.set_title("Dispatch with Ramp Rate Constraints")
ax1.legend(loc="upper right")

status = n.generators_t.status["slow_baseload"].round(0)
ax2.step(status.index, status.values, where="mid", color="tab:green", linewidth=2)
ax2.set_ylabel("Status")
ax2.set_xlabel("Hour")
ax2.set_ylim(-0.1, 1.1)
ax2.set_yticks([0, 1])
ax2.set_yticklabels(["OFF", "ON"])

plt.tight_layout()

# %%
# The big-M value can be set via the committable_big_m parameter
# None means PyPSA will auto-infer from network peak load
print("By default, PyPSA auto-infers big-M from network peak load")

# %%
# You can set a custom big-M value using the committable_big_m parameter
n.optimize(committable_big_m=10000, log_to_console=False)
print("Optimization with custom big-M (10000) successful!")
