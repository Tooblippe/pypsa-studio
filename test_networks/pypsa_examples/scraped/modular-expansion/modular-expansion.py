import pypsa
from pypsa.costs import annuity

n = pypsa.examples.model_energy()

n.add(
    "Generator",
    "nuclear",
    bus="electricity",
    p_nom_extendable=True,
    marginal_cost=15,
    capital_cost=annuity(0.07, 50) * 8_000_000,
    p_min_pu=0.7,
    ramp_limit_up=0.03,
    ramp_limit_down=0.03,
)

n.optimize(solver_name="gurobi")

n.generators.p_nom_opt

# %%
n.generators.loc["nuclear", "p_nom_mod"] = 1000
n.generators.loc["nuclear", "p_nom_max"] = 10000
n.optimize(solver_name="gurobi")
n.generators.p_nom_opt

# %%
n.generators_t.p.loc["2019-01"].plot(figsize=(6, 3))
