import pandas as pd

import pypsa

# %%
n = pypsa.Network()
n.snapshots = range(5)  # snapshots 0..4 (five periods)

# Add carrier definition
n.add("Carrier", "AC", color="lightblue")

# Add a single bus
n.add("Bus", "bus", carrier="AC")

# Add time-varying load with one low-demand valley (period index 3)
n.add("Load", "load", p_set=[50, 120, 50, 20, 50], bus="bus")

# Base-load generator: cheap marginal cost, inflexible, costly to cycle
n.add(
    "Generator",
    "base",
    bus="bus",
    p_nom=100,
    marginal_cost=20,
    p_min_pu=0.4,
    committable=True,  # Enable unit commitment
    start_up_cost=4000,
    shut_down_cost=2000,
)

# Peak generator: flexible but expensive
n.add(
    "Generator",
    "peak",
    bus="bus",
    p_nom=50,
    marginal_cost=70,
    p_min_pu=0.2,
    committable=True,  # Enable unit commitment
    start_up_cost=250,
)

# %%
n.optimize(
    linearized_unit_commitment=True,
)

# %%
prices = n.buses_t.marginal_price
prices

# %%
dispatch = n.generators_t.p
dispatch

# %%
status = n.generators_t.status
status

# %%
summary = pd.DataFrame(
    {
        "Load (MW)": n.loads_t.p_set["load"].values,
        "Base Gen (MW)": n.generators_t.p["base"].values,
        "Peak Gen (MW)": n.generators_t.p["peak"].values,
        "Total Gen (MW)": n.generators_t.p.sum(axis=1).values,
        "Base Status": n.generators_t.status["base"].values,
        "Peak Status": n.generators_t.status["peak"].values,
        "Price (€/MWh)": n.buses_t.marginal_price["bus"].values,
    }
)
summary.index.name = "Time Period"
summary

# %%
base = "base"
periods_low = [2, 3, 4]

su = float(n.generators.at[base, "start_up_cost"])
sd = float(n.generators.at[base, "shut_down_cost"])
cycle_cost = su + sd

mc = float(n.generators.at[base, "marginal_cost"])
gen_low = float(dispatch.loc[periods_low, base].sum())  # MWh over snapshots 2–4
op_cost = gen_low * mc

print("Why stay online?")
print("=" * 25)
print(f"Start-up cost:        {su:,.0f} €")
print(f"Shut-down cost:       {sd:,.0f} €")
print(f"Total cycling cost:   {cycle_cost:,.0f} €\n")

print(f"Output (snapshots 2-4): {gen_low:.1f} MWh")
print(f"Operational cost:       {op_cost:,.0f} €\n")

decision = "Stay online" if op_cost < cycle_cost else "Cycle off/on"
savings = abs(cycle_cost - op_cost)

print(f"Decision: {decision} is cheaper.")
print(f"Savings vs alternative: {savings:,.0f} €")
