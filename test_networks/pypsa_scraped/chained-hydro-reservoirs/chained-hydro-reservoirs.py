import pandas as pd

import pypsa

n = pypsa.Network()
n.set_snapshots(range(8))

n.add("Carrier", "reservoir")
n.add("Carrier", "rain")

n.add("Bus", "electricity 1", carrier="electricity")
n.add("Bus", "electricity 2", carrier="electricity")

n.add("Bus", "reservoir 1", carrier="reservoir")
n.add("Bus", "reservoir 2", carrier="reservoir")

n.add(
    "Generator",
    "rain",
    bus="reservoir 1",
    carrier="rain",
    p_nom=350,
    p_max_pu=[0.0, 0.3, 0.8, 0.5, 0.1, 0.0, 0.2, 0.4],
)

n.add(
    "Load",
    "load 1",
    bus="electricity 1",
    p_set=[20, 20, 15, 15, 30, 40, 35, 25],
    carrier="electricity",
)
n.add(
    "Load",
    "load 2",
    bus="electricity 2",
    p_set=[30, 25, 20, 20, 40, 50, 45, 30],
    carrier="electricity",
);

# %%
n.add(
    "Link",
    "spillage",
    bus0="reservoir 1",
    bus1="reservoir 2",
    carrier="spillage",
    efficiency=0.5,
    p_nom_extendable=True,
)

n.add(
    "Link",
    "turbine 1",
    bus0="reservoir 1",
    bus1="electricity 1",
    bus2="reservoir 2",
    carrier="turbine",
    efficiency=0.9,
    efficiency2=0.5,
    capital_cost=1000,
    p_nom_extendable=True,
)

n.add(
    "Link",
    "turbine 2",
    bus0="reservoir 2",
    bus1="electricity 2",
    carrier="turbine",
    efficiency=0.9,
    capital_cost=1000,
    p_nom_extendable=True,
)


n.add(
    "Store",
    "reservoir 1",
    bus="reservoir 1",
    carrier="reservoir",
    e_cyclic=True,
    e_nom=10_000,
)

n.add(
    "Store",
    "reservoir 2",
    bus="reservoir 2",
    carrier="reservoir",
    e_cyclic=True,
    e_nom=10_000,
)
n.sanitize()

# %%
n.optimize(n.snapshots)
print("Objective:", n.objective)

# Save no-delay results for later comparison
no_delay = {
    "objective": n.objective,
    "generators_p": n.generators_t.p.copy(),
    "links_p0": n.links_t.p0.copy(),
    "links_p1": n.links_t.p1.copy(),
    "links_p2": n.links_t.p2.copy(),
    "stores_p": n.stores_t.p.copy(),
    "stores_e": n.stores_t.e.copy(),
    "link_p_nom_opt": n.links.p_nom_opt.copy(),
}

# %%
import plotly.graph_objects as go
from plotly.subplots import make_subplots

carrier_colors = {
    "rain": "#4C78A8",
    "spillage": "#E45756",
    "turbine": "#F58518",
    "reservoir": "#72B7B2",
    "electricity": "#54A24B",
}


def plot_energy_balance(n, title=""):
    eb = n.stats.energy_balance(groupby=["bus", "carrier"], groupby_time=False).fillna(
        0
    )

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=["Reservoir 1", "Reservoir 2", "Electricity 1", "Electricity 2"],
        specs=[[{"secondary_y": True}, {"secondary_y": True}], [{}, {}]],
        vertical_spacing=0.15,
    )

    seen = set()
    for bus, row, col in [
        ("reservoir 1", 1, 1),
        ("reservoir 2", 1, 2),
        ("electricity 1", 2, 1),
        ("electricity 2", 2, 2),
    ]:
        bus_eb = eb.xs(bus, level="bus")
        for (comp, carrier), values in bus_eb.iterrows():
            group = f"{comp}: {carrier}"
            fig.add_trace(
                go.Bar(
                    x=n.snapshots,
                    y=values,
                    name=group,
                    marker_color=carrier_colors.get(carrier, "#999"),
                    legendgroup=group,
                    showlegend=group not in seen,
                ),
                row=row,
                col=col,
            )
            seen.add(group)

        if bus.startswith("reservoir"):
            group = "Reservoir level"
            fig.add_trace(
                go.Scatter(
                    x=n.snapshots,
                    y=n.stores_t.e[bus],
                    mode="lines+markers",
                    name=group,
                    line={"color": "black", "width": 2, "dash": "dot"},
                    legendgroup=group,
                    showlegend=group not in seen,
                ),
                row=row,
                col=col,
                secondary_y=True,
            )
            seen.add(group)

    fig.update_layout(height=600, barmode="relative", title_text=title)
    fig.update_yaxes(title_text="Power [MW]", row=1, col=1)
    fig.update_yaxes(title_text="Energy [MWh]", secondary_y=True, row=1, col=1)
    fig.update_yaxes(title_text="Energy [MWh]", secondary_y=True, row=1, col=2)
    fig.update_yaxes(title_text="Power [MW]", row=2, col=1)
    fig.update_xaxes(title_text="Snapshot", row=2, col=1)
    fig.update_xaxes(title_text="Snapshot", row=2, col=2)
    return fig


plot_energy_balance(n, title="No Delay")

# %%
n.links.loc["spillage", "delay"] = 1
n.links.loc["turbine 1", "delay2"] = 1

n.optimize(n.snapshots)
print("Objective with delay:", n.objective)

# %%
plot_energy_balance(n, title="With Delay")

# %%
fig = make_subplots(
    rows=1, cols=2, subplot_titles=["Reservoir 1", "Reservoir 2"], shared_yaxes=True
)
for col, store in enumerate(["reservoir 1", "reservoir 2"], 1):
    fig.add_trace(
        go.Scatter(
            x=n.snapshots,
            y=no_delay["stores_e"][store],
            mode="lines+markers",
            name="No delay",
            marker_symbol="circle",
            marker_color="orange",
            line={"color": "orange", "width": 2},
            legendgroup="no_delay",
            showlegend=(col == 1),
        ),
        row=1,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=n.snapshots,
            y=n.stores_t.e[store],
            mode="lines+markers",
            name="With delay",
            marker_symbol="diamond",
            marker_color="forestgreen",
            line={"color": "forestgreen", "width": 2, "dash": "dash"},
            legendgroup="delay",
            showlegend=(col == 1),
        ),
        row=1,
        col=col,
    )
fig.update_layout(height=350, yaxis_title="Energy [MWh]")
fig.update_xaxes(title_text="Snapshot")

# %%
scenarios = [
    (no_delay["links_p0"]["spillage"], -no_delay["links_p1"]["spillage"], "No Delay"),
    (n.links_t.p0["spillage"], -n.links_t.p1["spillage"], "With Delay"),
]
fig = make_subplots(
    rows=1, cols=2, subplot_titles=["Spillage (No Delay)", "Spillage (With Delay)"]
)
for col, (sent, received, label) in enumerate(scenarios, 1):
    fig.add_trace(
        go.Scatter(
            x=n.snapshots,
            y=sent,
            mode="lines+markers",
            name="Sent (p0)",
            marker_symbol="circle",
            marker_color="#4C78A8",
            line={"color": "#4C78A8", "width": 2},
            legendgroup="sent",
            showlegend=(col == 1),
        ),
        row=1,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=n.snapshots,
            y=received,
            mode="lines+markers",
            name="Received (-p1)",
            marker_symbol="diamond",
            marker_color="#E45756",
            line={"color": "#E45756", "width": 2, "dash": "dash"},
            legendgroup="recv",
            showlegend=(col == 1),
        ),
        row=1,
        col=col,
    )
fig.update_layout(height=350)
fig.update_yaxes(title_text="Power [MW]")
fig.update_xaxes(title_text="Snapshot")

# %%
pd.DataFrame(
    {
        "No Delay": {
            "Objective": no_delay["objective"],
            "Spillage capacity [MW]": no_delay["link_p_nom_opt"]["spillage"],
            "Turbine 1 capacity [MW]": no_delay["link_p_nom_opt"]["turbine 1"],
            "Turbine 2 capacity [MW]": no_delay["link_p_nom_opt"]["turbine 2"],
            "Total rain generation [MWh]": no_delay["generators_p"].sum().sum(),
        },
        "With Delay": {
            "Objective": n.objective,
            "Spillage capacity [MW]": n.links.p_nom_opt["spillage"],
            "Turbine 1 capacity [MW]": n.links.p_nom_opt["turbine 1"],
            "Turbine 2 capacity [MW]": n.links.p_nom_opt["turbine 2"],
            "Total rain generation [MWh]": n.generators_t.p.sum().sum(),
        },
    }
).round(2)

# %%
fig = make_subplots(
    rows=1,
    cols=2,
    subplot_titles=["No Delay", "With Delay"],
    shared_yaxes=True,
)
flow_items = [
    ("Rain inflow", "generators_p", "rain", "links_p0", None, "#4C78A8"),
    ("Spillage", "links_p0", "spillage", "links_p0", None, "#E45756"),
    ("Turbine 1", "links_p0", "turbine 1", "links_p0", None, "#F58518"),
    ("Turbine 2", "links_p0", "turbine 2", "links_p0", None, "#72B7B2"),
]
for col, data in enumerate([no_delay, None], 1):
    src = no_delay if col == 1 else None
    for name, key, comp, *_, color in flow_items:
        if col == 1:
            y = (
                no_delay[key][comp]
                if key != "generators_p"
                else no_delay["generators_p"][comp]
            )
        else:
            if key == "generators_p":
                y = n.generators_t.p[comp]
            else:
                y = n.links_t.p0[comp]
        fig.add_trace(
            go.Bar(
                x=n.snapshots,
                y=y,
                name=name,
                marker_color=color,
                legendgroup=name,
                showlegend=(col == 1),
            ),
            row=1,
            col=col,
        )

fig.update_layout(height=400, barmode="group", yaxis_title="Power [MW]")
fig.update_xaxes(title_text="Snapshot")
