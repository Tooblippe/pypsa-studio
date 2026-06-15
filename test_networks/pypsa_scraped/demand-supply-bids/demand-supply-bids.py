import matplotlib.pyplot as plt
import numpy as np

import pypsa

plt.style.use("bmh")

# %%
supply_bids = {
    "qty": [120, 100, 50, 60, 70, 60, 50],
    "price": [0, 15, 20, 36, 60, 150, 200],
}

demand_bids = {
    "qty": [250, 80, 20, 40, 60],
    "price": [200, 90, 75, 65, 24],
}

# %%
plt.figure(figsize=(8, 4))
plt.step(
    np.cumsum([0] + supply_bids["qty"]),
    supply_bids["price"][:1] + supply_bids["price"],
    label="Supply",
)
plt.step(
    np.cumsum([0] + demand_bids["qty"]),
    demand_bids["price"][:1] + demand_bids["price"],
    label="Demand",
)
plt.xlabel("Quantity (MW)")
plt.ylabel("Price (EUR/MWh)")
plt.legend()

# %%
n = pypsa.Network()
n.add("Bus", "single-node")

# Add supply bids
n.add(
    "Generator",
    name=[f"supply_{i}" for i in range(len(supply_bids["qty"]))],
    bus="single-node",
    marginal_cost=supply_bids["price"],
    p_nom=supply_bids["qty"],
)

# Add demand bids
n.add(
    "Generator",
    name=[f"demand_{i}" for i in range(len(demand_bids["qty"]))],
    bus="single-node",
    p_nom=demand_bids["qty"],
    marginal_cost=[-p for p in demand_bids["price"]],
    sign=-1,
)

# %%
n.optimize()

# %%
# Show objective function
display(n.model.objective)

# %%
# Show nodal power balance constraint
n.model.constraints["Bus-nodal_balance"]

# %%
# Show maximum and minimum power output constraints for all bids
display(n.model.constraints["Generator-fix-p-upper"])
display(n.model.constraints["Generator-fix-p-lower"])

# %%
n.buses_t.marginal_price

# %%
n.generators_t.p

# %%
supply_bids["zone"] = ["north", "south", "north", "north", "south", "north", "south"]
demand_bids["zone"] = ["south", "north", "north", "south", "south"]

# %%
plt.figure(figsize=(8, 4))

for zone, linestyle in zip(["north", "south"], ["-", "--"]):
    s_idx = [i for i, z in enumerate(supply_bids["zone"]) if z == zone]
    d_idx = [i for i, z in enumerate(demand_bids["zone"]) if z == zone]

    s_qty = [supply_bids["qty"][i] for i in s_idx]
    s_price = [supply_bids["price"][i] for i in s_idx]
    d_qty = [demand_bids["qty"][i] for i in d_idx]
    d_price = [demand_bids["price"][i] for i in d_idx]

    plt.step(
        np.cumsum([0] + s_qty),
        [s_price[0]] + s_price,
        label=f"Supply ({zone})",
        color="C0",
        linestyle=linestyle,
    )
    plt.step(
        np.cumsum([0] + d_qty),
        [d_price[0]] + d_price,
        label=f"Demand ({zone})",
        color="C1",
        linestyle=linestyle,
    )

plt.xlabel("Quantity (MW)")
plt.ylabel("Price (EUR/MWh)")
plt.legend()
plt.tight_layout()

# %%
n2 = pypsa.Network()

n2.add("Bus", "north")
n2.add("Bus", "south")

n2.add(
    "Generator",
    name=[f"supply_{i}" for i in range(len(supply_bids["qty"]))],
    bus=supply_bids["zone"],
    marginal_cost=supply_bids["price"],
    p_nom=supply_bids["qty"],
)
n2.add(
    "Generator",
    name=[f"demand_{i}" for i in range(len(demand_bids["qty"]))],
    bus=demand_bids["zone"],
    p_nom=demand_bids["qty"],
    marginal_cost=[-p for p in demand_bids["price"]],
    sign=-1,
)

# %%
n2.optimize()

# %%
n2.buses_t.marginal_price

# %%
display(n.objective)
display(n2.objective)

# %%
n2.add("Line", "line", bus0="north", bus1="south", s_nom=100)
n2.optimize()

# %%
display(n2.objective)
display(n2.buses_t.marginal_price)
