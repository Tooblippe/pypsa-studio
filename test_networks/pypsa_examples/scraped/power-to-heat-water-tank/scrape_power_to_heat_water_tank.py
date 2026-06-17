from pathlib import Path
import runpy

DEFAULT_PAGE_NAME = "power-to-heat-water-tank"
runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scrape_pypsa_example.py"),
    init_globals={"DEFAULT_PAGE_NAME": DEFAULT_PAGE_NAME},
    run_name="__main__",
)
