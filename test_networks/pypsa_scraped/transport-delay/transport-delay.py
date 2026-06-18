import matplotlib.pyplot as plt
import pandas as pd

import pypsa

n = pypsa.Network()
n.set_snapshots(range(8))

n.add("Bus", "production")
n.add("Bus", "demand")

n.add("Generator", "wind", bus="production", p_nom=100, marginal_cost=5)
n.add("Generator", "backup", bus="demand", p_nom=100, marginal_cost=80)
n.add("Load", "load", bus="demand", p_set=[10, 30, 50, 20, 40, 60, 25, 15])
n.sanitize()

# %%
n.add(
    "Link",
    "pipeline",
    bus0="production",
    bus1="demand",
    p_nom=100,
    efficiency=0.95,
    delay=2,
    cyclic_delay=True,
)

n.optimize()

# %%
fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
colors = [f"C{i}" for i in range(8)]
delay = 2
p0_colors = colors
p1_colors = colors[-delay:] + colors[:-delay]
n.links_t.p0["pipeline"].plot.bar(
    ax=axes[0], title="Input (p0 at production)", color=p0_colors
)
(-n.links_t.p1["pipeline"]).plot.bar(
    ax=axes[1], title="Output (-p1 at demand)", color=p1_colors
)
for ax in axes:
    ax.set_ylabel("MW")
plt.tight_layout()

# %%
n.links.loc["pipeline", "cyclic_delay"] = False

n.optimize()

# %%
fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
colors = [f"C{i}" for i in range(8)]
delay = 2
gray = "lightgray"
p0_colors = colors[: len(colors) - delay] + [gray] * delay
p1_colors = [gray] * delay + colors[: len(colors) - delay]
n.links_t.p0["pipeline"].plot.bar(
    ax=axes[0], title="Input (p0 at production)", color=p0_colors
)
(-n.links_t.p1["pipeline"]).plot.bar(
    ax=axes[1], title="Output (-p1 at demand)", color=p1_colors
)
for ax in axes:
    ax.set_ylabel("MW")
plt.tight_layout()

# %%
n.remove("Link", "pipeline")

n.add("Bus", "demand2")
n.add("Generator", "backup2", bus="demand2", p_nom=100, marginal_cost=80)
n.add("Load", "load2", bus="demand2", p_set=[5, 15, 25, 10, 20, 30, 12, 8])

n.add(
    "Link",
    "pipeline",
    bus0="production",
    bus1="demand",
    bus2="demand2",
    p_nom=100,
    efficiency=0.95,
    efficiency2=0.90,
    delay=2,
    delay2=4,
    cyclic_delay=True,
    cyclic_delay2=True,
)

n.optimize()

# %%
fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
colors = [f"C{i}" for i in range(8)]
p0_colors = colors
p1_colors = colors[-2:] + colors[:-2]
p2_colors = colors[-4:] + colors[:-4]
n.links_t.p0["pipeline"].plot.bar(ax=axes[0], title="Input (p0)", color=p0_colors)
(-n.links_t.p1["pipeline"]).plot.bar(
    ax=axes[1], title="Output bus1 (-p1, delay=2)", color=p1_colors
)
(-n.links_t.p2["pipeline"]).plot.bar(
    ax=axes[2], title="Output bus2 (-p2, delay=4)", color=p2_colors
)
for ax in axes:
    ax.set_ylabel("MW")
plt.tight_layout()

# %%
n.remove("Link", "pipeline")
n.remove("Bus", "demand2")
n.remove("Generator", "backup2")
n.remove("Load", "load2")

n.snapshot_weightings.loc[:, "generators"] = [1, 2, 1, 2, 1, 2, 1, 2]

n.add(
    "Link",
    "pipeline",
    bus0="production",
    bus1="demand",
    p_nom=100,
    efficiency=0.95,
    delay=3,
    cyclic_delay=True,
)

n.optimize()

# %%
pd.DataFrame(
    {
        "weighting": n.snapshot_weightings.generators,
        "p0": n.links_t.p0["pipeline"],
        "p1": n.links_t.p1["pipeline"],
    }
)

# %%
from pypsa.components._types.links import Links

src, _ = Links.get_delay_source_indexer(
    n.snapshots, n.snapshot_weightings.generators, delay=3, is_cyclic=True
)

fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
colors = [f"C{i}" for i in range(8)]
p1_colors = [colors[s] for s in src]
n.links_t.p0["pipeline"].plot.bar(
    ax=axes[0], title="Input (p0 at production)", color=colors
)
(-n.links_t.p1["pipeline"]).plot.bar(
    ax=axes[1], title="Output (-p1 at demand)", color=p1_colors
)
for ax in axes:
    ax.set_ylabel("MW")
plt.tight_layout()

# %%
n.snapshot_weightings.loc[:, "generators"] = 4

n.links.loc["pipeline", "delay"] = 3

n.optimize()

# %%
src, _ = Links.get_delay_source_indexer(
    n.snapshots, n.snapshot_weightings.generators, delay=3, is_cyclic=True
)

pd.DataFrame(
    {
        "weighting": n.snapshot_weightings.generators,
        "p0": n.links_t.p0["pipeline"],
        "p1": n.links_t.p1["pipeline"],
        "source snapshot": src,
    }
)

# %%
fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
colors = [f"C{i}" for i in range(8)]
p1_colors = [colors[s] for s in src]
n.links_t.p0["pipeline"].plot.bar(
    ax=axes[0], title="Input (p0 at production)", color=colors
)
(-n.links_t.p1["pipeline"]).plot.bar(
    ax=axes[1], title="Output (-p1 at demand)", color=p1_colors
)
for ax in axes:
    ax.set_ylabel("MW")
plt.tight_layout()

# %%
n.links.loc["pipeline", "delay"] = 5

n.optimize()

# %%
src, _ = Links.get_delay_source_indexer(
    n.snapshots, n.snapshot_weightings.generators, delay=5, is_cyclic=True
)

pd.DataFrame(
    {
        "weighting": n.snapshot_weightings.generators,
        "p0": n.links_t.p0["pipeline"],
        "p1": n.links_t.p1["pipeline"],
        "source snapshot": src,
    }
)

# %%
fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
colors = [f"C{i}" for i in range(8)]
p1_colors = [colors[s] for s in src]
n.links_t.p0["pipeline"].plot.bar(
    ax=axes[0], title="Input (p0 at production)", color=colors
)
(-n.links_t.p1["pipeline"]).plot.bar(
    ax=axes[1], title="Output (-p1 at demand)", color=p1_colors
)
for ax in axes:
    ax.set_ylabel("MW")
plt.tight_layout()
