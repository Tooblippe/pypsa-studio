import pandas as pd
from numpy.testing import assert_almost_equal, assert_array_almost_equal

import pypsa


# %%
def replace_storage_unit(n: pypsa.Network, name: str) -> tuple:
    """
    Replace the storage unit with `name` with a bus for the energy
    carrier, two links for the conversion of the energy carrier to and from electricity,
    a store to keep track of the depletion of the energy carrier and its
    CO2 emissions, and a variable generator for the storage inflow.

    Because the energy size and power size are linked in the storage unit by the `max_hours`,
    `extra_functionality` must be added to the optimisation to implement this constraint.
    """
    su = n.storage_units.loc[name]

    bus_name = f"{su['bus']} {su['carrier']}"
    link_1_name = f"{name} converter {su['carrier']} to AC"
    link_2_name = f"{name} converter AC to {su['carrier']}"
    store_name = f"{name} store {su['carrier']}"
    gen_name = f"{name} inflow"

    n.add("Bus", bus_name, carrier=su["carrier"])

    # dispatch link
    n.add(
        "Link",
        link_1_name,
        bus0=bus_name,
        bus1=su["bus"],
        capital_cost=su["capital_cost"] * su["efficiency_dispatch"],
        p_nom=su["p_nom"] / su["efficiency_dispatch"],
        p_nom_extendable=su["p_nom_extendable"],
        p_nom_max=su["p_nom_max"] / su["efficiency_dispatch"],
        p_nom_min=su["p_nom_min"] / su["efficiency_dispatch"],
        p_max_pu=su["p_max_pu"],
        marginal_cost=su["marginal_cost"] * su["efficiency_dispatch"],
        efficiency=su["efficiency_dispatch"],
    )

    # store link
    n.add(
        "Link",
        link_2_name,
        bus0=su["bus"],
        bus1=bus_name,
        p_nom=su["p_nom"],
        p_nom_extendable=su["p_nom_extendable"],
        p_nom_max=su["p_nom_max"],
        p_nom_min=su["p_nom_min"],
        p_max_pu=-su["p_min_pu"],
        efficiency=su["efficiency_store"],
    )

    if (
        name in n.storage_units_t.state_of_charge_set.columns
        and (~pd.isnull(n.storage_units_t.state_of_charge_set[name])).any()
    ):
        e_max_pu = pd.Series(data=1, index=n.snapshots)
        e_min_pu = pd.Series(data=0, index=n.snapshots)
        non_null = ~pd.isnull(n.storage_units_t.state_of_charge_set[name])
        e_max_pu[non_null] = n.storage_units_t.state_of_charge_set[name][non_null]
        e_min_pu[non_null] = n.storage_units_t.state_of_charge_set[name][non_null]
    else:
        e_max_pu = 1
        e_min_pu = 0

    n.add(
        "Store",
        store_name,
        bus=bus_name,
        e_nom=su["p_nom"] * su["max_hours"],
        e_nom_min=su["p_nom_min"] / su["efficiency_dispatch"] * su["max_hours"],
        e_nom_max=su["p_nom_max"] / su["efficiency_dispatch"] * su["max_hours"],
        e_nom_extendable=su["p_nom_extendable"],
        e_max_pu=e_max_pu,
        e_min_pu=e_min_pu,
        standing_loss=su["standing_loss"],
        e_cyclic=su["cyclic_state_of_charge"],
        e_initial=su["state_of_charge_initial"],
    )

    n.add("Carrier", "rain", co2_emissions=0)

    # inflow from a variable generator, which can be curtailed (i.e. spilled)
    inflow_max = n.storage_units_t.inflow[name].max()

    if inflow_max == 0:
        inflow_pu = 0
    else:
        inflow_pu = n.storage_units_t.inflow[name] / inflow_max

    n.add(
        "Generator",
        gen_name,
        bus=bus_name,
        carrier="rain",
        p_nom=inflow_max,
        p_max_pu=inflow_pu,
    )

    if su["p_nom_extendable"]:
        ratio2 = su["max_hours"]
        ratio1 = ratio2 * su["efficiency_dispatch"]

        def extra_functionality(n: pypsa.Network, sns: pd.Index) -> None:
            m = n.model
            lhs = (
                m["Store-e_nom"].at[store_name]
                - m["Link-p_nom"].at[link_1_name] * ratio1
            )
            m.add_constraints(lhs == 0, name="store_fix_1")

            lhs = (
                m["Store-e_nom"].at[store_name]
                - m["Link-p_nom"].at[link_2_name] * ratio2
            )
            m.add_constraints(lhs == 0, name="store_fix_2")

    else:
        extra_functionality = None

    n.remove("StorageUnit", name)

    return bus_name, link_1_name, link_2_name, store_name, gen_name, extra_functionality


# %%
n_r = pypsa.examples.storage_hvdc()
n_r.optimize()

# %%
n = pypsa.examples.storage_hvdc()

name = "Storage 0"

(
    bus_name,
    link_1_name,
    link_2_name,
    store_name,
    gen_name,
    extra_functionality,
) = replace_storage_unit(n, name)
n.optimize(extra_functionality=extra_functionality)

# %%
assert_almost_equal(n_r.objective, n.objective, decimal=2)

assert_array_almost_equal(
    n_r.storage_units_t.state_of_charge[name],
    n.stores_t.e[store_name],
)

assert_array_almost_equal(
    n_r.storage_units_t.p[name],
    -n.links_t.p1[link_1_name] - n.links_t.p0[link_2_name],
)

assert_array_almost_equal(
    n_r.storage_units.at[name, "p_nom_opt"],
    n.links.at[link_2_name, "p_nom_opt"],
)

assert_array_almost_equal(
    n_r.storage_units.at[name, "p_nom_opt"],
    n.links.at[link_1_name, "p_nom_opt"]
    * n_r.storage_units.at[name, "efficiency_dispatch"],
)
