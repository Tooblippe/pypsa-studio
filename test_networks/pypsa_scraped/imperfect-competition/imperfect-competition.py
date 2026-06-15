import pandas as pd

# %%
# Cost parameters
DEMAND_INTERCEPT = 30  # a in P(d) = a - b*d  [EUR/MWh]
DEMAND_SLOPE = 4  # b in P(d) = a - b*d  [EUR/MWh per MW]
LINEAR_COST = 1  # linear cost coefficient  [EUR/MWh]
QUADRATIC_COST = 0.5  # quadratic cost coefficient  [EUR/MWh per MW]

# Capacities and demands
SOLAR_CAPACITY = 3.0  # [MW] installed solar capacity
SOLAR_CF = [0.8, 0.5, 0.1]  # capacity factors per snapshot
GAS_PLANT_CAPACITY = 8.0  # [MW] gas backup plant capacity
GAS_PRODUCER_CAPACITY = 5.0  # [MW] each gas producer's capacity
DEMAND_MAX = 10.0  # [MW] maximum demand quantity

# %%
def create_network():
    """Create the two-bus electricity + gas network.

    The network has 3 snapshots with decreasing solar output,
    creating increasing residual demand for gas backup.
    """
    n = pypsa.Network()
    n.set_snapshots(range(3))

    n.add("Bus", "electricity")
    n.add("Bus", "gas")

    # --- Electricity market ---

    # Solar: zero-cost renewable with time-varying capacity factor
    n.add(
        "Generator",
        "solar",
        bus="electricity",
        p_nom=SOLAR_CAPACITY,
        marginal_cost=0,
        p_max_pu=SOLAR_CF,
    )

    # Elastic demand: inverse demand curve P(d) = 30 - 4*d
    # Modelled as a sign=-1 generator ("demand bid"):
    #   Objective contribution: (-30)*d + 2*d^2
    #   FOC: -30 + 4*d = -lambda  (lambda = shadow price on bus)
    #   Hence: lambda = 30 - 4*d = P(d)
    n.add(
        "Generator",
        "elastic_demand",
        bus="electricity",
        sign=-1,
        p_nom=DEMAND_MAX,
        marginal_cost=-DEMAND_INTERCEPT,
        marginal_cost_quadratic=DEMAND_SLOPE / 2,
    )

    # --- Gas market ---

    # Two gas producers with identical convex cost C(q) = q + 0.5*q^2
    for i in [1, 2]:
        n.add(
            "Generator",
            f"gas_producer_{i}",
            bus="gas",
            p_nom=GAS_PRODUCER_CAPACITY,
            marginal_cost=LINEAR_COST,
            marginal_cost_quadratic=QUADRATIC_COST,
        )

    # --- Gas-to-electricity link (gas backup plant) ---
    # Converts gas to electricity 1:1 for simplicity.
    # The gas bus shadow price becomes the fuel cost of gas-fired power.
    n.add(
        "Link",
        "gas_plant",
        bus0="gas",
        bus1="electricity",
        p_nom=GAS_PLANT_CAPACITY,
        marginal_cost=0,
        efficiency=1.0,
    )

    return n

# %%
# Create the network
n = create_network()

# %%
n_a = create_network()
m_a = n_a.optimize.create_model()

# investigate the model structure
print(m_a)

# %%
# Problem A is the PyPSA unmodified cost min model
status_a, cond_a = n_a.optimize.solve_model(solver_name="highs")

print(f"\n{'=' * 60}")
print("  Problem A: Perfect Competition (cv = 0)")
print(f"{'=' * 60}")
print(f"  Status: {status_a} | {cond_a}")
print(f"  Objective: {n_a.objective:.2f}")

# %%
n_b = create_network()
m_b = n_b.optimize.create_model()

# Access gas producer dispatch variables from the linopy model
q1 = m_b["Generator-p"].sel(name="gas_producer_1")
q2 = m_b["Generator-p"].sel(name="gas_producer_2")

# Cournot game parameters
cv = 1  # conjectural variation: 1 = Cournot (best-response)
b = DEMAND_SLOPE  # inverse demand slope = 4

# Cournot markup: (b*cv/2) * q_i^2  for each producer, each snapshot
# This effectively raises each producer's marginal cost from (1+q) to (1+5q)
cournot_markup = (b * cv / 2) * (q1 * q1 + q2 * q2)

# Append markup to the PyPSA model's objective
m_b.objective = m_b.objective.expression + cournot_markup.sum()

# Solve
status_b, cond_b = n_b.optimize.solve_model(solver_name="highs")

print(f"\n{'=' * 60}")
print("  Problem B: Cournot-Nash Competition (cv = 1)")
print(f"{'=' * 60}")
print(f"  Status: {status_b} | {cond_b}")
print(f"  Objective: {n_b.objective:.2f}")

# %%
def production_cost(q):
    """True production cost: C(q) = q + 0.5*q^2"""
    return LINEAR_COST * q + QUADRATIC_COST * q**2


def analyse_economics(n, label):
    """Compute economic metrics for a solved network."""
    q1 = n.generators_t.p["gas_producer_1"].values
    q2 = n.generators_t.p["gas_producer_2"].values
    p_gas = n.buses_t.marginal_price["gas"].values
    p_elec = n.buses_t.marginal_price["electricity"].values
    demand = n.generators_t.p["elastic_demand"].values

    # Production costs
    cost1 = production_cost(q1)
    cost2 = production_cost(q2)

    # Revenue = price * quantity
    rev1 = p_gas * q1
    rev2 = p_gas * q2

    # Profit = revenue - cost
    profit1 = rev1 - cost1
    profit2 = rev2 - cost2

    # Consumer expenditure (what electricity consumers pay)
    consumer_exp = p_elec * demand

    # Consumer surplus: integral under demand curve minus expenditure
    # integral_0^d P(x)dx = a*d - (b/2)*d^2
    consumer_surplus = (
        DEMAND_INTERCEPT * demand - (DEMAND_SLOPE / 2) * demand**2 - consumer_exp
    )

    return {
        "label": label,
        "q1": q1,
        "q2": q2,
        "demand": demand,
        "p_gas": p_gas,
        "p_elec": p_elec,
        "cost1": cost1,
        "cost2": cost2,
        "profit1": profit1,
        "profit2": profit2,
        "total_producer_profit": (profit1 + profit2).sum(),
        "total_production_cost": (cost1 + cost2).sum(),
        "total_consumer_expenditure": consumer_exp.sum(),
        "total_consumer_surplus": consumer_surplus.sum(),
    }


econ_a = analyse_economics(n_a, "A: Competitive")
econ_b = analyse_economics(n_b, "B: Cournot")

print(f"{'=' * 70}")
print("  ECONOMIC ANALYSIS (Totals)")
print(f"{'=' * 70}")

for econ in [econ_a, econ_b]:
    print(f"\n  --- {econ['label']} ---")
    print(f"    Total gas production cost:    {econ['total_production_cost']:.2f}")
    print(f"    Total producer profit:        {econ['total_producer_profit']:.2f}")
    print(f"    Total consumer expenditure:   {econ['total_consumer_expenditure']:.2f}")
    print(f"    Total consumer surplus:       {econ['total_consumer_surplus']:.2f}")

# %%
# --- Decomposition of welfare loss ---

# Welfare = Consumer surplus + Producer surplus (profit)
welfare_a = econ_a["total_consumer_surplus"] + econ_a["total_producer_profit"]
welfare_b = econ_b["total_consumer_surplus"] + econ_b["total_producer_profit"]

welfare_loss = welfare_a - welfare_b  # positive = welfare decreased
revenue_increase = econ_b["total_producer_profit"] - econ_a["total_producer_profit"]
consumer_loss = econ_a["total_consumer_surplus"] - econ_b["total_consumer_surplus"]
deadweight_loss = welfare_loss

# Cost increase to electricity system = consumer expenditure increase
cost_increase = (
    econ_b["total_consumer_expenditure"] - econ_a["total_consumer_expenditure"]
)

print(f"\n  Competitive total welfare:      {welfare_a:.2f}")
print(f"  Cournot total welfare:          {welfare_b:.2f}")
print(f"  Welfare loss (DWL):             {deadweight_loss:.2f}")

print(f"\n  Producer profit (competitive):  {econ_a['total_producer_profit']:.2f}")
print(f"  Producer profit (Cournot):      {econ_b['total_producer_profit']:.2f}")
print(f"  Oligopolist revenue increase:   {revenue_increase:.2f}")

print(f"\n  Consumer surplus (competitive): {econ_a['total_consumer_surplus']:.2f}")
print(f"  Consumer surplus (Cournot):     {econ_b['total_consumer_surplus']:.2f}")
print(f"  Consumer surplus loss:          {consumer_loss:.2f}")

print(f"\n  Consumer expenditure increase:  {cost_increase:.2f}")

print("\n  Decomposition of consumer surplus loss:")
print(f"    = Revenue transfer to producers: {revenue_increase:.2f}")
print(f"    + Deadweight loss:               {deadweight_loss:.2f}")
print(f"    = Total consumer loss:           {revenue_increase + deadweight_loss:.2f}")
print(f"    (actual consumer loss:           {consumer_loss:.2f})")

# %%
# --- Side-by-side summary table ---

summary = pd.DataFrame(
    {
        "A: Competitive": {
            "Gas price (avg)": econ_a["p_gas"].mean(),
            "Elec price (avg)": econ_a["p_elec"].mean(),
            "Gas output (total)": (econ_a["q1"] + econ_a["q2"]).sum(),
            "Demand (total)": econ_a["demand"].sum(),
            "Production cost": econ_a["total_production_cost"],
            "Consumer expenditure": econ_a["total_consumer_expenditure"],
            "Producer profit": econ_a["total_producer_profit"],
            "Consumer surplus": econ_a["total_consumer_surplus"],
            "Total welfare": welfare_a,
        },
        "B: Cournot": {
            "Gas price (avg)": econ_b["p_gas"].mean(),
            "Elec price (avg)": econ_b["p_elec"].mean(),
            "Gas output (total)": (econ_b["q1"] + econ_b["q2"]).sum(),
            "Demand (total)": econ_b["demand"].sum(),
            "Production cost": econ_b["total_production_cost"],
            "Consumer expenditure": econ_b["total_consumer_expenditure"],
            "Producer profit": econ_b["total_producer_profit"],
            "Consumer surplus": econ_b["total_consumer_surplus"],
            "Total welfare": welfare_b,
        },
    }
)
summary["Delta (B-A)"] = summary["B: Cournot"] - summary["A: Competitive"]
summary.style.format("{:.2f}")
