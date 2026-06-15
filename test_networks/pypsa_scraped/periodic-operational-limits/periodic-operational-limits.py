import calendar

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import xarray as xr

# %%
def get_p_monthly(network: pypsa.Network, output_mw: float) -> pd.Series:
    """Define a monthly output limit for dispatch, set for the first snapshot of each month."""
    sns = network.snapshots
    weights = network.snapshot_weightings["generators"]
    return pd.Series(output_mw * weights, index=sns).resample("MS").sum().reindex(sns)


n = pypsa.examples.model_energy()

ccgt_p_nom = 2000  # MW – fixed installed capacity
min_fraction = 0.15  # lower bound: 15 % of maximum possible monthly output
max_fraction = 0.40  # upper bound: 40 % of maximum possible monthly output
p_min_monthly = get_p_monthly(n, min_fraction * ccgt_p_nom)
p_max_monthly = get_p_monthly(n, max_fraction * ccgt_p_nom)

# Replace load shedding with a fixed-capacity CCGT
n.remove("Generator", "load shedding")

n.add(
    "Generator",
    "CCGT",
    bus="electricity",
    carrier="CCGT",
    p_nom=ccgt_p_nom,
    marginal_cost=60,  # €/MWh
    p_nom_extendable=False,
    p_min_periodic=p_min_monthly,
    p_max_periodic=p_max_monthly,
)
n.add("Carrier", "CCGT")

monthly_bounds = (
    pd.concat([p_min_monthly, p_max_monthly], axis=1, keys=["p_min", "p_max"])
    .groupby(n.snapshots.month.rename("month"))
    .sum()
)
display(monthly_bounds)

# %%
def get_grouper(limit_attr: xr.DataArray) -> xr.DataArray:
    """Return a grouper for snapshots in the same period based on the NaN values between each non-NaN value in the limit attribute."""
    return limit_attr.notnull().cumsum("snapshot").rename("limit_period")


def period_ccgt_output_constraints(n: pypsa.Network, sns: pd.Index) -> None:
    """Add lower and upper energy-output constraints for the CCGT dispatch per period.

    Parameters
    ----------
    n : pypsa.Network
    sns : pd.Index
        Active snapshots passed by PyPSA during optimisation.
    """
    m = n.model
    selector = {"name": "CCGT", "snapshot": sns}
    p_ccgt = m.variables["Generator-p"].sel(**selector)
    weights = n.snapshot_weightings["generators"].loc[sns]
    for limit, sign in {"max": "<=", "min": ">="}.items():
        limit_attr = n.components["Generator"].da[f"p_{limit}_periodic"].sel(**selector)
        grouper = get_grouper(limit_attr)
        p_period = (p_ccgt * weights).groupby(grouper).sum()
        p_lim_period = limit_attr.groupby(grouper).sum()
        m.add_constraints(
            lhs=p_period, sign=sign, rhs=p_lim_period, name=f"CCGT-period-{limit}"
        )

# %%
# --- Baseline: no custom constraints ---
n_base = n.copy()
n_base.optimize(include_objective_constant=False)
print("Baseline solved")

# %%
# --- Constrained: with monthly CCGT output limits ---
n_constrained = n.copy()
n_constrained.optimize(
    extra_functionality=period_ccgt_output_constraints,
    include_objective_constant=False,
)
print("Constrained solve completed")

# %%
display(n_constrained.model.constraints["CCGT-period-min"])
display(n_constrained.model.constraints["CCGT-period-max"])

# %%
def periodic_energy_balance(
    network: pypsa.Network | pypsa.NetworkCollection, grouper: pd.Series
) -> pd.Series:
    """Return periodic energy output [MWh] for a solved network.

    The `grouper` defines which snapshots belong to the same period, e.g. by month or by season.
    """
    weights = network.snapshot_weightings.generators
    energy_balance = network.statistics.energy_balance(
        groupby_time=False, bus_carrier="electricity"
    ).droplevel(["component", "bus_carrier"])
    energy_balance_period = (energy_balance * weights).T.groupby(grouper).sum()
    return energy_balance_period


def discharge_capacity(network: pypsa.Network | pypsa.NetworkCollection) -> pd.Series:
    """Return discharge capacity [MW] for a solved network."""
    generators = network.generators.p_nom_opt
    storage_units = network.storage_units.p_nom_opt
    capacity = pd.concat([generators, storage_units])
    return capacity


nc = pypsa.NetworkCollection({"Baseline": n_base, "Constrained": n_constrained})
grouper = get_grouper(
    n_constrained.components["Generator"].da["p_min_periodic"].sel(name="CCGT")
).to_series()

# %%
monthly_energy_balance = periodic_energy_balance(nc, grouper).xs(
    "CCGT", level="carrier", axis=1
)

month_labels = [calendar.month_abbr[m] for m in monthly_bounds.index]
df_plot = (
    monthly_energy_balance.stack().to_frame("Monthly CCGT dispatch (MWh)").reset_index()
)
df_plot["Month"] = df_plot["limit_period"].apply(lambda m: calendar.month_abbr[m])
fig = px.bar(
    df_plot,
    x="Month",
    y="Monthly CCGT dispatch (MWh)",
    color="network",
    barmode="group",
)

# Overlay the monthly bounds to verify that CCGT dispatch is within the limits
common_attrs = {
    "x": month_labels,
    "mode": "lines",
    "legendgroup": "bound",
    "line": {"width": 1, "shape": "hvh", "color": "black"},
}
fig.add_trace(go.Scatter(y=monthly_bounds["p_min"], showlegend=False, **common_attrs))
fig.add_trace(
    go.Scatter(
        y=monthly_bounds["p_max"],
        name="Feasible constrained range",
        fill="tonexty",
        fillcolor="rgba(169, 169, 169, 0.3)",
        **common_attrs,
    )
)

# %%
capacity = discharge_capacity(nc)
df_plot = capacity.to_frame("Capacity (MW)").reset_index()
fig_capacity = px.bar(
    df_plot,
    x="name",
    y="Capacity (MW)",
    color="network",
    barmode="group",
)
fig_capacity.update_layout(
    xaxis_title="Generator / Storage unit", yaxis_title="Installed capacity (MW)"
)

# %%
with pd.option_context("display.float_format", "{:,.0f} M€".format):
    capex = nc.statistics.capex().groupby("network").sum() / 1e6
    opex = nc.statistics.opex().groupby("network").sum() / 1e6
    total = capex + opex
    cost_df = pd.concat([capex, opex, total], axis=1, keys=["Capex", "Opex", "Total"]).T
    cost_df["Cost delta"] = (
        cost_df["Constrained"]
        .subtract(cost_df["Baseline"])
        .div(cost_df["Baseline"])
        .mul(100)
        .round(1)
        .astype(str)
        + " %"
    )
    display(cost_df)
