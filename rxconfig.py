import reflex as rx


config = rx.Config(
    app_name="pypsa_network_builder_v2",
    telemetry_enabled=False,
    show_built_with_reflex=False,
    plugins=[
        rx.plugins.RadixThemesPlugin(),
        rx.plugins.SitemapPlugin(),
    ],
)
