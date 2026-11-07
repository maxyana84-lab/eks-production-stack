"""Prometheus metrics shared by every request: rate, errors (via the status code label), latency, in-flight."""
import time

from flask import Flask, Response, g, request
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)


def init_metrics(app: Flask, service: str) -> CollectorRegistry:
    # a private registry per app keeps tests independent of each other
    registry = CollectorRegistry()
    requests_total = Counter(
        "http_requests_total", "HTTP requests", ["service", "method", "path", "code"], registry=registry
    )
    duration = Histogram(
        "http_request_duration_seconds", "HTTP request latency", ["service", "method", "path"],
        buckets=BUCKETS, registry=registry,
    )
    in_flight = Gauge("http_requests_in_flight", "Requests being processed (active connections)", ["service"], registry=registry)

    def route_label() -> str:
        # the route template, not the raw URL, so that the label cardinality stays small
        return request.url_rule.rule if request.url_rule else "unmatched"

    @app.before_request
    def start():
        g._t0 = time.perf_counter()
        in_flight.labels(service).inc()

    @app.after_request
    def finish(response):
        path = route_label()
        if path != "/metrics" and hasattr(g, "_t0"):
            requests_total.labels(service, request.method, path, str(response.status_code)).inc()
            duration.labels(service, request.method, path).observe(time.perf_counter() - g._t0)
        return response

    @app.teardown_request
    def done(_exc):
        if hasattr(g, "_t0"):
            in_flight.labels(service).dec()

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)

    return registry
