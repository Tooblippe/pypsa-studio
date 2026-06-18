import numpy as np

import pypsa

# %%
# marginal costs in EUR/MWh
marginal_costs = {"Wind": 0, "Hydro": 0, "Coal": 30, "Gas": 60, "Oil": 80}

# power plant capacities (nominal powers in MW) in each country (not necessarily realistic)
power_plant_p_nom = {
    "South Africa": {"Coal": 35000, "Wind": 3000, "Gas": 8000, "Oil": 2000},
    "Mozambique": {
        "Hydro": 1200,
    },
    "Eswatini": {
        "Hydro": 600,
    },
}

# transmission capacities in MW (not necessarily realistic)
transmission = {
    "South Africa": {"Mozambique": 500, "Eswatini": 250},
    "Mozambique": {"Eswatini": 100},
}

# country electrical loads in MW (not necessarily realistic)
loads = {"South Africa": 42000, "Mozambique": 650, "Eswatini": 250}

# %%
country = "South Africa"

n = pypsa.Network()

n.add("Bus", country)

for tech in power_plant_p_nom[country]:
    n.add(
        "Generator",
        f"{country} {tech}",
        bus=country,
        p_nom=power_plant_p_nom[country][tech],
        marginal_cost=marginal_costs[tech],
    )


n.add("Load", f"{country} load", bus=country, p_set=loads[country])

# %%
n.optimize()

# %%
n.loads_t.p

# %%
n.generators_t.p

# %%
n.buses_t.marginal_price

# %%
n = pypsa.Network()

countries = ["Mozambique", "South Africa"]

for country in countries:
    n.add("Bus", country)

    for tech in power_plant_p_nom[country]:
        n.add(
            "Generator",
            f"{country} {tech}",
            bus=country,
            p_nom=power_plant_p_nom[country][tech],
            marginal_cost=marginal_costs[tech],
        )

    n.add("Load", f"{country} load", bus=country, p_set=loads[country])

    # add transmission as controllable Link
    if country not in transmission:
        continue

    for other_country in countries:
        if other_country not in transmission[country]:
            continue

        # NB: Link is by default unidirectional, so have to set p_min_pu = -1
        # to allow bidirectional (i.e. also negative) flow
        n.add(
            "Link",
            f"{country} - {other_country} link",
            bus0=country,
            bus1=other_country,
            p_nom=transmission[country][other_country],
            p_min_pu=-1,
        )

# %%
n.optimize()

# %%
n.loads_t.p

# %%
n.generators_t.p

# %%
n.buses_t.marginal_price

# %%
n.links_t.p0

# %%
n.links_t.mu_lower

# %%
n = pypsa.Network()

countries = ["Eswatini", "Mozambique", "South Africa"]

for country in countries:
    n.add("Bus", country)

    for tech in power_plant_p_nom[country]:
        n.add(
            "Generator",
            f"{country} {tech}",
            bus=country,
            p_nom=power_plant_p_nom[country][tech],
            marginal_cost=marginal_costs[tech],
        )

    n.add("Load", f"{country} load", bus=country, p_set=loads[country])

    if country not in transmission:
        continue

    for other_country in countries:
        if other_country not in transmission[country]:
            continue

        n.add(
            "Link",
            f"{country} - {other_country} link",
            bus0=country,
            bus1=other_country,
            p_nom=transmission[country][other_country],
            p_min_pu=-1,
        )

# %%
n.optimize()

# %%
n.loads_t.p

# %%
n.generators_t.p

# %%
n.buses_t.marginal_price

# %%
n.links_t.p0

# %%
n.links_t.mu_lower

# %%
country = "South Africa"

n = pypsa.Network()

n.add("Bus", country)

for tech in power_plant_p_nom[country]:
    n.add(
        "Generator",
        f"{country} {tech}",
        bus=country,
        p_nom=power_plant_p_nom[country][tech],
        marginal_cost=marginal_costs[tech],
    )

# standard high marginal utility consumers
n.add("Load", f"{country} load", bus=country, p_set=loads[country])

# add an industrial load as a negative-dispatch generator with marginal utility of 70 EUR/MWh for 8000 MW
n.add(
    "Generator",
    f"{country} industrial load",
    bus=country,
    p_max_pu=0,
    p_min_pu=-1,
    p_nom=8000,
    marginal_cost=70,
)

# %%
n.optimize()

# %%
n.loads_t.p

# %%
n.generators_t.p

# %%
n.buses_t.marginal_price

# %%
country = "South Africa"

n = pypsa.Network()

n.set_snapshots(range(4))

n.add("Bus", country)

# availability (p_max_pu) is variable for wind
for tech in power_plant_p_nom[country]:
    n.add(
        "Generator",
        f"{country} {tech}",
        bus=country,
        p_nom=power_plant_p_nom[country][tech],
        marginal_cost=marginal_costs[tech],
        p_max_pu=([0.3, 0.6, 0.4, 0.5] if tech == "Wind" else 1),
    )

# load which varies over the snapshots
n.add(
    "Load",
    f"{country} load",
    bus=country,
    p_set=loads[country] + np.array([0, 1000, 3000, 4000]),
)

# %%
n.optimize()

# %%
n.loads_t.p

# %%
n.generators_t.p

# %%
n.buses_t.marginal_price

# %%
country = "South Africa"

n = pypsa.Network()

# snapshots labelled by [0,1,2,3]
n.set_snapshots(range(4))

n.add("Bus", country)

# p_max_pu is variable for wind
for tech in power_plant_p_nom[country]:
    n.add(
        "Generator",
        f"{country} {tech}",
        bus=country,
        p_nom=power_plant_p_nom[country][tech],
        marginal_cost=marginal_costs[tech],
        p_max_pu=([0.3, 0.6, 0.4, 0.5] if tech == "Wind" else 1),
    )

# load which varies over the snapshots
n.add(
    "Load",
    f"{country} load",
    bus=country,
    p_set=loads[country] + np.array([0, 1000, 3000, 4000]),
)

# storage unit to do price arbitrage
n.add(
    "StorageUnit",
    f"{country} pumped hydro",
    bus=country,
    p_nom=1000,
    max_hours=6,  # energy storage in terms of hours at full power
)

# %%
n.optimize()

# %%
n.loads_t.p

# %%
n.generators_t.p

# %%
n.storage_units_t.p

# %%
n.storage_units_t.state_of_charge

# %%
n.buses_t.marginal_price
