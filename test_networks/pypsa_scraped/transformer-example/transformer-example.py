import numpy as np
import pandas as pd

import pypsa

n = pypsa.Network()

n.add("Bus", "MV bus", v_nom=20, v_mag_pu_set=1.02)
n.add("Bus", "LV1 bus", v_nom=0.4)
n.add("Bus", "LV2 bus", v_nom=0.4)

n.add(
    "Transformer",
    "MV-LV trafo",
    type="0.4 MVA 20/0.4 kV",
    bus0="MV bus",
    bus1="LV1 bus",
)
n.add(
    "Line", "LV cable", type="NAYY 4x50 SE", bus0="LV1 bus", bus1="LV2 bus", length=0.1
)
n.add("Generator", "External Grid", bus="MV bus", control="Slack", marginal_cost=10)
n.add("Load", "LV load", bus="LV2 bus", p_set=0.1, q_set=0.05)


# %%
def run_power_flow(n: pypsa.Network) -> pd.DataFrame:
    n.lpf()
    n.pf(use_seed=True)
    return pd.DataFrame(
        {
            "Voltage Angles": n.buses_t.v_ang.loc["now"] * 180.0 / np.pi,
            "Voltage Magnitude": n.buses_t.v_mag_pu.loc["now"],
        }
    )


# %%
run_power_flow(n)

# %%
n.transformers.tap_position = 2
run_power_flow(n)

# %%
n.transformers.tap_position = -2
run_power_flow(n)

# %%
new_trafo_lv_tap = n.transformer_types.loc[["0.4 MVA 20/0.4 kV"]]
new_trafo_lv_tap.index = ["New trafo"]
new_trafo_lv_tap.tap_side = 1
new_trafo_lv_tap.T

# %%
n.add("TransformerType", "New trafo", **new_trafo_lv_tap.iloc[0].to_dict())
n.transformers.type = "New trafo"
n.transformers.tap_position = 2
run_power_flow(n)

# %%
n.transformers.T

# %%
n.transformers.tap_position = -2
run_power_flow(n)

# %%
n.generators.p_nom = 1
n.lines.s_nom = 1
n.optimize()
pd.DataFrame(
    {
        "Voltage Angles": n.buses_t.v_ang.loc["now"] * 180.0 / np.pi,
        "Voltage Magnitude": n.buses_t.v_mag_pu.loc["now"],
    }
)
