import pandas as pd

import pypsa
from pypsa.costs import annuity

temp = pypsa.examples.model_energy()
temp.remove("Generator", "load shedding")
n = temp.copy()

INVESTMENT_PERIODS = [2025, 2035, 2045]

# %%
# Assume 5 GW of wind and solar capacity each, built in 2015
n.generators.loc[:, ["build_year", "p_nom", "p_nom_extendable"]] = 2015, 5_000, False

# all other storage components need to be removed
n.remove("Link", n.links.index)
n.remove("StorageUnit", n.storage_units.index)
n.remove("Store", n.stores.index)

for year in INVESTMENT_PERIODS:
    n.add(
        "Generator",
        temp.generators.index + f"-{year}",
        build_year=year,
        p_max_pu=temp.generators_t.p_max_pu.rename(
            columns=lambda s: s + f"-{year}"
        ).loc[:, ::-1],
        **temp.generators.rename(index=lambda s: s + f"-{year}").drop(
            columns=["build_year", "p_max_pu"]
        ),
    )

    n.add(
        "Link",
        temp.links.index,
        suffix=f"-{year}",
        build_year=year,
        **temp.links.rename(index=lambda s: s + f"-{year}").drop(
            columns=["build_year"]
        ),
    )

    n.add(
        "StorageUnit",
        temp.storage_units.index,
        suffix=f"-{year}",
        build_year=year,
        **temp.storage_units.rename(index=lambda s: s + f"-{year}").drop(
            columns=["build_year"]
        ),
    )

    n.add(
        "Store",
        temp.stores.index,
        suffix=f"-{year}",
        build_year=year,
        **temp.stores.rename(index=lambda s: s + f"-{year}").drop(
            columns=["build_year"]
        ),
    )

# %%
n.generators.loc["solar-2035", "capital_cost"] *= 0.9
n.generators.loc["solar-2045", "capital_cost"] *= 0.85

n.storage_units.loc["battery storage-2035", "capital_cost"] *= 0.9
n.storage_units.loc["battery storage-2045", "capital_cost"] *= 0.85

n.generators_t.p_max_pu.loc[:, "wind-2035"] *= 1.1
n.generators_t.p_max_pu.loc[:, "wind-2045"] *= 1.15

# %%
n.add(
    "Carrier",
    ["coal", "gas"],
    color=["gray", "lightcoral"],
    co2_emissions=[0.336, 0.198],
)

n.add(
    "Generator",
    "coal",
    carrier="coal",
    bus="electricity",
    p_nom=4_000,
    p_nom_extendable=False,
    build_year=1990,
    lifetime=40,
    capital_cost=annuity(0.07, 40) * 4_000_000,
    efficiency=0.35,
    marginal_cost=30,
)

n.add(
    "Generator",
    "gas",
    carrier="gas",
    bus="electricity",
    p_nom=6_000,
    p_nom_extendable=False,
    build_year=2005,
    lifetime=35,
    capital_cost=annuity(0.07, 35) * 800_000,
    efficiency=0.5,
    marginal_cost=60,
)

n.add(
    "Generator",
    "gas-2035",
    carrier="gas",
    bus="electricity",
    p_nom_extendable=True,
    build_year=2035,
    lifetime=35,
    capital_cost=annuity(0.07, 35) * 900_000,
    efficiency=0.55,
    marginal_cost=55,
)

# %%
n.set_investment_periods(INVESTMENT_PERIODS)
n.investment_period_weightings *= 10

REDUCTION_PATH = [300e6, 100e6, 20e6]

for i, year in enumerate(INVESTMENT_PERIODS):
    n.add(
        "GlobalConstraint",
        f"co2-limit-{year}",
        type="primary_energy",
        carrier_attribute="co2_emissions",
        investment_period=year,
        constant=REDUCTION_PATH[i],
        sense="<=",
    )


# %%
def optimize_period(n: pypsa.Network, period: int):
    snapshots = n.snapshots[n.snapshots.get_level_values("period") == period]
    return n.optimize(
        multi_investment_periods=True,
        snapshots=snapshots,
    )


optimize_period(n, 2025)

display(n.generators.p_nom_opt)

display(n.global_constraints)

# %%
n.statistics.energy_balance().div(1e6).round(2)


# %%
def freeze_period(n: pypsa.Network, period: int):
    for c in n.components[["Generator", "Link", "StorageUnit", "Store"]]:
        attr = "e_nom" if c.name == "Store" else "p_nom"
        c.static[attr] = c.static[attr + "_opt"]
        c.static.loc[c.static.build_year == period, attr + "_extendable"] = False


freeze_period(n, 2025)
optimize_period(n, 2035)

freeze_period(n, 2035)
optimize_period(n, 2045)

# %%
n.global_constraints

# %%
display(n.statistics.energy_balance().div(1e6).round(1))

display(n.statistics.capex().div(1e6).round(1))

# %%
(n.statistics.capex().sum() + n.statistics.opex().sum()).div(1e6).round(1)

# %%
df = (
    pd.concat(
        {
            year: n.generators.query(
                f"build_year <= {year} and build_year + lifetime > {year}"
            )
            .groupby("carrier")
            .p_nom_opt.sum()
            for year in INVESTMENT_PERIODS
        },
        axis=1,
    )
    .fillna(0)
    .T.div(1e3)
)


df.plot.area(
    stacked=True,
    linewidth=0,
    ylabel="GW",
    xlabel="Year",
    title="Operational Capacity",
    color=df.columns.map(n.carriers.color),
)

# %%
# for c in n.iterate_components({"Generator", "Link", "StorageUnit", "Store"}):
#     attr = "e_nom" if c.name == "Store" else "p_nom"
#     c.df.loc[c.df.build_year >= 2025, attr + "_extendable"] = True

# n.optimize(
#     multi_investment_periods=True,
#     log_to_console=True,
# )
