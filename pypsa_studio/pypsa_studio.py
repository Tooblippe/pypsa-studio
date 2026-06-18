"""Reflex app entrypoint for PyPSA Studio."""

import reflex as rx

from pypsa_studio.state import State
from pypsa_studio.ui.layout import index

app = rx.App()
app.add_page(
    index,
    route="/",
    title="PyPSA Network Builder",
    on_load=State.initialize_builder_on_load,
)
