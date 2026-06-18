import reflex as rx

config = rx.Config(
    app_name="pypsa_studio",
    telemetry_enabled=False,
    show_built_with_reflex=False,
    plugins=[
        rx.plugins.RadixThemesPlugin(),
        rx.plugins.SitemapPlugin(),
    ],
)
