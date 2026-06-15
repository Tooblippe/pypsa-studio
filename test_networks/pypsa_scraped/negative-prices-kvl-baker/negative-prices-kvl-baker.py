import pypsa

n = pypsa.Network()

# %%
# Add three buses in a triangular layout
n.add("Bus", "Bus1", x=0, y=2)  # Top-left
n.add("Bus", "Bus2", x=2, y=2)  # Top-right
n.add("Bus", "Bus3", x=1, y=0);  # Bottom (load)

# %%
# Add generators
n.add("Generator", "Gen1", bus="Bus1", p_nom=100, marginal_cost=10)
n.add("Generator", "Gen2", bus="Bus2", p_nom=100, marginal_cost=20)
n.add("Generator", "Gen3", bus="Bus3", p_nom=100, marginal_cost=100);

# %%
# Add a load of 100 MW at Bus2
n.add("Load", "Load3", bus="Bus3", p_set=100);

# %%
# Add three lines
n.add("Line", "Line12", bus0="Bus1", bus1="Bus2", x=1, s_nom=100)
n.add("Line", "Line23", bus0="Bus2", bus1="Bus3", x=1, s_nom=100)
n.add("Line", "Line13", bus0="Bus1", bus1="Bus3", x=1, s_nom=10);

# %%
n.optimize()

# %%
print(f"Objective value: {n.objective} €")

# %%
n.generators_t.p

# %%
n.lines_t.p0

# %%
n.buses_t.marginal_price

# %%
n.add("Load", "Load1", bus="Bus1", p_set=1);

# %%
n.optimize()

# %%
print(f"Objective value: {n.objective} €")

# %%
n.generators_t.p

# %%
n.lines_t.p0

# %%
bus_size = (
    n.statistics.supply(groupby="bus", components=["Generator", "Load"])
    .groupby("bus")
    .sum()
)
line_flows = n.lines_t.p0.iloc[0]
bus_color = n.buses_t.marginal_price.iloc[0]
line_loading = n.lines_t.p0.iloc[0] / n.lines.s_nom

# %%
n.plot.map(
    bus_size=bus_size / 8000,
    line_width=line_flows / 5,
    line_flow=line_flows / 30,
    bus_color=bus_color,
    line_color=line_loading,
);
