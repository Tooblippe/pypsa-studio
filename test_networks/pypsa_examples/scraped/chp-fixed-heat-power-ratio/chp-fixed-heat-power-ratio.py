import pypsa

n = pypsa.Network()

n.add("Bus", "Frankfurt", carrier="AC")
n.add("Load", "Frankfurt", bus="Frankfurt", p_set=5)

n.add("Bus", "Frankfurt heat", carrier="heat")
n.add("Load", "Frankfurt heat", bus="Frankfurt heat", p_set=3)

n.add("Bus", "Frankfurt gas", carrier="gas")
n.add("Generator", "Frankfurt gas", bus="Frankfurt gas", marginal_cost=100, p_nom=100)

n.add(
    "Link",
    "OCGT",
    bus0="Frankfurt gas",
    bus1="Frankfurt",
    p_nom_extendable=True,
    capital_cost=600,
    efficiency=0.4,  # electricity per unit of gas
)

n.add(
    "Link",
    "CHP",
    bus0="Frankfurt gas",
    bus1="Frankfurt",
    bus2="Frankfurt heat",
    p_nom_extendable=True,
    capital_cost=1400,
    efficiency=0.3,  # electricity per unit of gas
    efficiency2=0.3,  # heat per unit of gas
)

n.optimize();

# %%
n.loads_t.p

# %%
n.links_t.p0

# %%
n.links_t.p1

# %%
n.links_t.p2
