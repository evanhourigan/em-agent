from starlette_exporter import PrometheusMiddleware, handle_metrics


def add_prometheus(app, app_name: str = "gateway") -> None:
    app.add_middleware(
        PrometheusMiddleware,
        app_name=app_name,
        prefix=app_name,
        group_paths=True,
    )
    app.add_route("/metrics", handle_metrics)
