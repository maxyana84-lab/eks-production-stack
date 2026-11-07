#!/usr/bin/env python3
"""Generates the Grafana dashboards (one per service) as JSON files inside the charts.

    python3 scripts/gen_dashboards.py
The charts publish them as ConfigMaps labelled grafana_dashboard=1; the Grafana sidecar loads them,
so they survive Grafana restarts.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def panel(pid, title, exprs, unit, x, y, w=12, h=8):
    return {
        "id": pid,
        "type": "timeseries",
        "title": title,
        "datasource": {"type": "prometheus", "uid": "${datasource}"},
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "targets": [{"expr": e, "legendFormat": legend, "refId": chr(65 + i)} for i, (e, legend) in enumerate(exprs)],
    }


def dashboard(uid, title, panels):
    return {
        "uid": uid,
        "title": title,
        "tags": ["eks-production-stack"],
        "schemaVersion": 39,
        "version": 1,
        "refresh": "30s",
        "time": {"from": "now-1h", "to": "now"},
        "templating": {"list": [{"name": "datasource", "type": "datasource", "query": "prometheus", "current": {}}]},
        "panels": panels,
    }


def http_panels(service):
    sel = f'service="{service}"'
    quantile = lambda q: (
        f'histogram_quantile({q}, sum by (le) (rate(http_request_duration_seconds_bucket{{{sel}}}[5m])))',
        f"p{int(q * 100)}",
    )
    return [
        panel(1, "Request rate", [(f"sum(rate(http_requests_total{{{sel}}}[5m]))", "requests/s")], "reqps", 0, 0),
        panel(
            2, "Error rate (5xx)",
            [(f'sum(rate(http_requests_total{{{sel},code=~"5.."}}[5m])) / sum(rate(http_requests_total{{{sel}}}[5m]))', "5xx share")],
            "percentunit", 12, 0,
        ),
        panel(3, "Latency p50 / p95 / p99", [quantile(0.5), quantile(0.95), quantile(0.99)], "s", 0, 8),
    ]


frontend = dashboard("eks-frontend", "Frontend", http_panels("frontend"))

backend = dashboard(
    "eks-backend", "Backend",
    http_panels("backend")
    + [panel(4, "Active connections (in-flight requests)", [('sum(http_requests_in_flight{service="backend"})', "in flight")], "short", 12, 8)],
)

# Bitnami PostgreSQL chart with metrics.enabled=true ships postgres-exporter
database = dashboard(
    "eks-database", "Database",
    [
        panel(1, "Connections", [("sum(pg_stat_database_numbackends)", "backends")], "short", 0, 0),
        panel(
            2, "Query (transaction) rate",
            [("sum(rate(pg_stat_database_xact_commit[5m]) + rate(pg_stat_database_xact_rollback[5m]))", "transactions/s")],
            "ops", 12, 0,
        ),
        panel(
            3, "Replication lag (standalone: no data)",
            [("max(pg_replication_lag_seconds)", "lag")], "s", 0, 8,
        ),
        panel(
            4, "Disk usage of the data volume",
            [('max by (persistentvolumeclaim) (kubelet_volume_stats_used_bytes{persistentvolumeclaim=~"data-.*postgresql.*"} / kubelet_volume_stats_capacity_bytes{persistentvolumeclaim=~"data-.*postgresql.*"})', "{{persistentvolumeclaim}}")],
            "percentunit", 12, 8,
        ),
    ],
)

for chart, dash in (("frontend", frontend), ("backend", backend), ("database", database)):
    target = ROOT / "charts" / chart / "files"
    target.mkdir(parents=True, exist_ok=True)
    (target / "dashboard.json").write_text(json.dumps(dash, indent=2) + "\n")
    print("wrote", target / "dashboard.json")
