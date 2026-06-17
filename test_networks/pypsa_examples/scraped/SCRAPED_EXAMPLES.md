# Scraped PyPSA documentation examples

Source index: https://docs.pypsa.org/latest/examples/examples/

Examples classified as scraped build a network with `.add(...)` calls. Examples classified as ignored either load an existing `pypsa.examples.*` network without building one, or do not construct a network with `.add(...)`.

Export status: 36 scraped examples, 36 NetCDF exports created, 8 examples ignored.

## Scraped

- `example-1` -> `test_networks/pypsa_examples/scraped/example-1/` (Quickstart 1 - Markets)
- `example-2` -> `test_networks/pypsa_examples/scraped/example-2/` (Quickstart 2 - Power Flow)
- `example-3` -> `test_networks/pypsa_examples/scraped/example-3/` (Quickstart 3 - Investments & Storage)
- `simple-electricity-market-examples` -> `test_networks/pypsa_examples/scraped/simple-electricity-market-examples/` (Electricity Markets)
- `unit-commitment` -> `test_networks/pypsa_examples/scraped/unit-commitment/` (Unit Commitment)
- `uc-prices` -> `test_networks/pypsa_examples/scraped/uc-prices/` (Negative Prices in Linearized Unit Commitment)
- `minimal-example-pf` -> `test_networks/pypsa_examples/scraped/minimal-example-pf/` (Newton-Raphson Power Flow)
- `negative-prices-kvl-baker` -> `test_networks/pypsa_examples/scraped/negative-prices-kvl-baker/` (Negative LMPs from Line Congestion)
- `rolling-horizon` -> `test_networks/pypsa_examples/scraped/rolling-horizon/` (Rolling-Horizon Optimization)
- `water-value` -> `test_networks/pypsa_examples/scraped/water-value/` (Water Values for Long-Duration Storage Operation)
- `demand-supply-bids` -> `test_networks/pypsa_examples/scraped/demand-supply-bids/` (Demand and Supply Bids in Electricity Markets)
- `capacity-expansion-planning-single-node` -> `test_networks/pypsa_examples/scraped/capacity-expansion-planning-single-node/` (1-Node Capacity Expansion)
- `3-node-cem` -> `test_networks/pypsa_examples/scraped/3-node-cem/` (3-Node Capacity Expansion)
- `multi-investment-optimisation` -> `test_networks/pypsa_examples/scraped/multi-investment-optimisation/` (Pathway Planning)
- `myopic-pathway` -> `test_networks/pypsa_examples/scraped/myopic-pathway/` (Myopic Pathway Planning)
- `stochastic-optimization` -> `test_networks/pypsa_examples/scraped/stochastic-optimization/` (Stochastic Optimization)
- `modular-expansion` -> `test_networks/pypsa_examples/scraped/modular-expansion/` (Modular Expansion)
- `committable-extendable` -> `test_networks/pypsa_examples/scraped/committable-extendable/` (Committable + Extendable Components)
- `modular-committable` -> `test_networks/pypsa_examples/scraped/modular-committable/` (Modular Expansion with Unit Commitment)
- `sector-coupling-single-node` -> `test_networks/pypsa_examples/scraped/sector-coupling-single-node/` (Single Node Sector Coupling)
- `islanded-methanol-production` -> `test_networks/pypsa_examples/scraped/islanded-methanol-production/` (Islanded Fuel Production)
- `battery-electric-vehicle-charging` -> `test_networks/pypsa_examples/scraped/battery-electric-vehicle-charging/` (Electric Vehicles)
- `chp-fixed-heat-power-ratio` -> `test_networks/pypsa_examples/scraped/chp-fixed-heat-power-ratio/` (Backpressure CHP)
- `power-to-gas-boiler-chp` -> `test_networks/pypsa_examples/scraped/power-to-gas-boiler-chp/` (Extraction-Condensing CHP)
- `power-to-heat-water-tank` -> `test_networks/pypsa_examples/scraped/power-to-heat-water-tank/` (Heat Pumps and Thermal Storage)
- `biomass-synthetic-fuels-carbon-management` -> `test_networks/pypsa_examples/scraped/biomass-synthetic-fuels-carbon-management/` (Carbon Management)
- `scigrid-redispatch` -> `test_networks/pypsa_examples/scraped/scigrid-redispatch/` (Redispatch Example)
- `demand-elasticity` -> `test_networks/pypsa_examples/scraped/demand-elasticity/` (Demand Elasticity)
- `imperfect-competition` -> `test_networks/pypsa_examples/scraped/imperfect-competition/` (Imperfect Competition)
- `generation-investment-screening-curve` -> `test_networks/pypsa_examples/scraped/generation-investment-screening-curve/` (Screening Curves)
- `chained-hydro-reservoirs` -> `test_networks/pypsa_examples/scraped/chained-hydro-reservoirs/` (Chained Hydro-Reservoirs)
- `transformer-example` -> `test_networks/pypsa_examples/scraped/transformer-example/` (Transformers)
- `reserve-power` -> `test_networks/pypsa_examples/scraped/reserve-power/` (Reserve Constraints)
- `transport-delay` -> `test_networks/pypsa_examples/scraped/transport-delay/` (Transport Delay)
- `periodic-operational-limits` -> `test_networks/pypsa_examples/scraped/periodic-operational-limits/` (Defining Asset Operational Limits over User-Defined Time Periods)
- `replace-generator-storage-units-with-store` -> `test_networks/pypsa_examples/scraped/replace-generator-storage-units-with-store/` (StorageUnit as Link and Store Components)

## Ignored

- `ac-dc-lopf` (Meshed AC-DC Networks): loads pypsa.examples network
- `scigrid-lopf-then-pf` (SciGRID Network): loads pypsa.examples network
- `scigrid-sclopf` (Security-Constrained LOPF): loads pypsa.examples network
- `mga` (Modelling to Generate Alternatives): loads pypsa.examples network
- `near-opt-space` (Exploring the Near-Optimal Feasible Space): loads pypsa.examples network
- `time-series-aggregation` (Time Series Aggregation): no network .add construction
- `gsa` (Global Sensitivity Analysis): loads pypsa.examples network
- `tracing-infeasibilities` (Tracing Infeasibilities): loads pypsa.examples network
