"""Scrape a rendered PyPSA documentation example and export its final network."""

from __future__ import annotations

import argparse
import subprocess
import sys
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa


DEFAULT_PAGE_NAME = globals().get("DEFAULT_PAGE_NAME", "")
SOURCE_BASE_URL = "https://docs.pypsa.org/latest/examples"


class NotebookCodeParser(HTMLParser):
    """Extract notebook input cells from PyPSA's rendered documentation HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.cells: list[str] = []
        self._capturing = False
        self._depth = 0
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        is_code_cell = (
            tag == "div"
            and attributes.get("class") == "clipboard-copy-txt"
            and (attributes.get("id") or "").startswith("cell-")
        )
        if is_code_cell:
            self._capturing = True
            self._depth = 1
            self._buffer = []
        elif self._capturing and tag == "div":
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if not self._capturing or tag != "div":
            return

        self._depth -= 1
        if self._depth == 0:
            self._capturing = False
            code = unescape("".join(self._buffer)).strip()
            if code:
                self.cells.append(code)

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._buffer.append(data)


def fetch_page(url: str) -> str:
    result = subprocess.run(
        ["curl", "-fsSL", url],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout


def extract_code_cells(html: str) -> list[str]:
    parser = NotebookCodeParser()
    parser.feed(html)
    if not parser.cells:
        raise RuntimeError("No notebook code cells were found in the page HTML.")
    return parser.cells


def write_code(cells: list[str], output: Path) -> None:
    output.write_text("\n\n# %%\n".join(cells) + "\n", encoding="utf-8")


def prepare_cell(cell: str) -> str:
    """Apply narrow compatibility fixes for running notebook code headlessly."""

    return (
        cell.replace('freq="H"', 'freq="h"')
        .replace("freq='H'", "freq='h'")
        .replace('freq = "H"', 'freq = "h"')
        .replace("freq = 'H'", "freq = 'h'")
    )


def display(*values: object, **_: object) -> None:
    for value in values:
        print(value)


def run_cells(cells: list[str], page_name: str, continue_on_error: bool) -> dict[str, object]:
    namespace: dict[str, object] = {
        "__name__": "__main__",
        "display": display,
        "np": np,
        "pd": pd,
        "pypsa": pypsa,
    }
    for index, cell in enumerate(cells, start=1):
        print(f"Running scraped cell {index}/{len(cells)}", flush=True)
        try:
            exec(compile(prepare_cell(cell), f"<{page_name}:cell-{index}>", "exec"), namespace)
        except Exception as exc:
            if not continue_on_error:
                raise
            print(
                f"WARNING: skipped failed cell {index}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
    return namespace


def find_network(namespace: dict[str, object]) -> pypsa.Network:
    network = namespace.get("n")
    if isinstance(network, pypsa.Network):
        return network

    for value in namespace.values():
        if isinstance(value, pypsa.Network):
            return value

    raise RuntimeError("The scraped code did not leave a pypsa.Network in scope.")


def prepare_network_for_export(network: pypsa.Network) -> None:
    for key, value in list(network.meta.items()):
        if isinstance(value, bool):
            network.meta[key] = str(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("page_name", nargs="?", default=DEFAULT_PAGE_NAME)
    parser.add_argument("--url")
    parser.add_argument("--html-input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--code-output", type=Path)
    parser.add_argument(
        "--continue-on-error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Continue past notebook display cells that fail after the network is built.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.page_name:
        raise SystemExit("A page name is required.")

    script_dir = Path(__file__).resolve().parent
    if script_dir.name == "scraped":
        output_dir = script_dir / args.page_name
    else:
        output_dir = script_dir

    url = args.url or f"{SOURCE_BASE_URL}/{args.page_name}/"
    output = args.output or output_dir / f"{args.page_name}.nc"
    code_output = args.code_output or output_dir / f"{args.page_name}.py"

    output_dir.mkdir(parents=True, exist_ok=True)
    html = args.html_input.read_text(encoding="utf-8") if args.html_input else fetch_page(url)
    cells = extract_code_cells(html)
    write_code(cells, code_output)

    namespace = run_cells(cells, args.page_name, args.continue_on_error)
    network = find_network(namespace)
    prepare_network_for_export(network)
    network.export_to_netcdf(output)
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
