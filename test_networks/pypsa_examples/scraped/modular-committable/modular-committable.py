import matplotlib.pyplot as plt
import pandas as pd

import pypsa

# %%
n = pypsa.Network(snapshots=range(4))

n.add("Bus", "bus", carrier="electricity")
n.add("Carrier", "electricity")

# Variable load pattern - requires different numbers of modules
load_profile = [4000, 6000, 5000, 800]
n.add("Load", "load", bus="bus", p_set=load_profile)

# Add a modular, committable, extendable generator
# Capacity must be built in 200 MW modules
n.add(
    "Generator",
    "modular_gas",
    bus="bus",
    p_nom_extendable=True,
    committable=True,
    p_nom_mod=200,  # Must build in 200 MW increments
    p_nom_max=10000,
    p_min_pu=0.1,  # 10% minimum load per committed module
    marginal_cost=1,
    capital_cost=1,
    stand_by_cost=1,  # Penalize keeping modules online unnecessarily
)

# %%
n.optimize(log_to_console=False)

# %%
p_nom_opt = n.generators.p_nom_opt["modular_gas"]
p_nom_mod = n.generators.p_nom_mod["modular_gas"]
n_modules = p_nom_opt / p_nom_mod

print(f"Optimal capacity: {p_nom_opt:.0f} MW")
print(f"Module size: {p_nom_mod:.0f} MW")
print(f"Number of modules built: {n_modules:.0f}")

# %%
# Verify the capacity is indeed a multiple of the module size
assert abs(n_modules - round(n_modules)) < 1e-6, (
    "Capacity should be a multiple of module size!"
)
print("Capacity is correctly constrained to module size multiples.")

# %%
# The status variable now represents number of committed modules
results = pd.DataFrame(
    {
        "Load": load_profile,
        "Modules Committed": n.generators_t.status["modular_gas"].astype(int),
        "Dispatch": n.generators_t.p["modular_gas"],
    }
)
results

# %%
# Visualize modules committed vs load
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)

# Dispatch
ax1.bar(
    results.index, results["Dispatch"], alpha=0.7, color="steelblue", label="Dispatch"
)
ax1.plot(results.index, results["Load"], "ro-", label="Load")
ax1.set_ylabel("Power [MW]")
ax1.set_title("Dispatch vs Load")
ax1.legend()

# Modules committed
ax2.bar(results.index, results["Modules Committed"], color="green", alpha=0.7)
ax2.axhline(
    y=n_modules,
    color="red",
    linestyle="--",
    label=f"Total modules built ({int(n_modules)})",
)
ax2.set_ylabel("Modules Committed")
ax2.set_xlabel("Hour")
ax2.set_title("Module Commitment Schedule")
ax2.legend()

plt.tight_layout()

# %%
n = pypsa.Network(snapshots=range(4))

n.add("Bus", "zone_A", carrier="electricity")
n.add("Bus", "zone_B", carrier="electricity")
n.add("Carrier", "electricity")

# Cheap generation in zone A
n.add("Generator", "gen_A", bus="zone_A", p_nom=1000, marginal_cost=20)

# Load in zone B
load_B = [300, 500, 400, 150]
n.add("Load", "load_B", bus="zone_B", p_set=load_B)

# Expensive backup in zone B
n.add("Generator", "gen_B", bus="zone_B", p_nom=600, marginal_cost=100)

# Committable + extendable + modular interconnector
n.add(
    "Link",
    "interconnector",
    bus0="zone_A",
    bus1="zone_B",
    p_nom_extendable=True,
    committable=True,
    p_nom_mod=150,  # 150 MW modules (e.g., HVDC cables)
    p_nom_max=600,
    p_min_pu=0.2,  # Minimum flow when active
    marginal_cost=5,
    capital_cost=300,
    start_up_cost=50,
)

# %%
n.optimize(log_to_console=False)

# %%
p_nom_opt = n.links.p_nom_opt["interconnector"]
p_nom_mod = n.links.p_nom_mod["interconnector"]
print(f"Optimal interconnector capacity: {p_nom_opt:.0f} MW")
print(f"Number of {p_nom_mod:.0f} MW modules: {p_nom_opt / p_nom_mod:.0f}")

# %%
# Verify n_mod variable exists for modular link
print(
    f"n_mod variable value: {n.model.variables['Link-n_mod'].solution.loc['interconnector']}"
)

# %%
pd.DataFrame(
    {
        "Load_B": load_B,
        "Link_Status": n.links_t.status["interconnector"],
        "Link_Flow": n.links_t.p0["interconnector"],
        "Gen_B_Dispatch": n.generators_t.p["gen_B"],
    }
)

# %%
n = pypsa.Network(snapshots=range(6))

n.add("Bus", "bus", carrier="electricity")
n.add("Carrier", "electricity")
# Load that varies significantly
load_profile = [500, 1000, 600, 200, 800, 400]
n.add("Load", "load", bus="bus", p_set=load_profile)

n.add(
    "Generator",
    "modular_plant",
    bus="bus",
    p_nom_extendable=True,
    committable=True,
    p_nom_mod=100,  # 100 MW modules
    p_nom_max=2000,
    p_min_pu=0.4,  # 20% minimum load per module
    marginal_cost=30,
    capital_cost=100,
    start_up_cost=10,  # Significant start-up cost per module
    shut_down_cost=5,  # Shut-down cost per module
)

# %%
n.optimize(log_to_console=False)

# %%
p_nom_opt = n.generators.p_nom_opt["modular_plant"]
p_nom_mod = n.generators.p_nom_mod["modular_plant"]
n_modules_built = int(p_nom_opt / p_nom_mod)

print(f"Total capacity built: {p_nom_opt:.0f} MW ({n_modules_built} modules)")

# %%
# Examine commitment dynamics
results = pd.DataFrame(
    {
        "Load": load_profile,
        "Modules_Committed": n.generators_t.status["modular_plant"].astype(int),
        "Dispatch": n.generators_t.p["modular_plant"].round(1),
        "Start_ups": n.generators_t.start_up["modular_plant"].astype(int),
        "Shut_downs": n.generators_t.shut_down["modular_plant"].astype(int),
    }
)
results

# %%
# Calculate costs
gen = n.generators.loc["modular_plant"]
total_startup_cost = results["Start_ups"].sum() * gen.start_up_cost
total_shutdown_cost = results["Shut_downs"].sum() * gen.shut_down_cost

print(f"Total start-up cost: {total_startup_cost:.0f}")
print(f"Total shut-down cost: {total_shutdown_cost:.0f}")

# %%
# Visualize commitment schedule with start-ups and shut-downs
fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)

# Dispatch vs Load
axes[0].bar(
    results.index, results["Dispatch"], alpha=0.7, color="steelblue", label="Dispatch"
)
axes[0].plot(results.index, results["Load"], "ro-", label="Load")
axes[0].set_ylabel("Power [MW]")
axes[0].set_title("Dispatch vs Load")
axes[0].legend()

# Modules committed
axes[1].bar(results.index, results["Modules_Committed"], color="green", alpha=0.7)
axes[1].axhline(
    y=n_modules_built,
    color="red",
    linestyle="--",
    label=f"Total built ({n_modules_built})",
)
axes[1].set_ylabel("Modules Online")
axes[1].set_title("Module Commitment")
axes[1].legend()

# Start-ups and shut-downs
x = results.index
width = 0.35
axes[2].bar(
    x - width / 2, results["Start_ups"], width, label="Start-ups", color="orange"
)
axes[2].bar(
    x + width / 2, results["Shut_downs"], width, label="Shut-downs", color="purple"
)
axes[2].set_ylabel("Number of Modules")
axes[2].set_xlabel("Hour")
axes[2].set_title("Module Start-ups and Shut-downs")
axes[2].legend()

plt.tight_layout()
