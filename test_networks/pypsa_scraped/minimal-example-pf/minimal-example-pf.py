import numpy as np

import pypsa

n = pypsa.Network()

N_BUSES = 3

# %%
for i in range(N_BUSES):
    n.add("Bus", f"My bus {i}", v_nom=20)

n.buses

# %%
for i in range(N_BUSES):
    n.add(
        "Line",
        f"My line {i}",
        bus0=f"My bus {i}",
        bus1=f"My bus {(i + 1) % N_BUSES}",
        x=0.1,
        r=0.01,
    )

n.lines

# %%
n.add("Generator", "My gen", bus="My bus 0", p_set=100, control="PQ")

n.generators

# %%
n.add("Load", "My load", bus="My bus 1", p_set=100, q_set=100)

n.loads

# %%
n.pf()

# %%
n.lines_t.p0

# %%
n.buses_t.v_ang * 180 / np.pi

# %%
n.buses_t.v_mag_pu
