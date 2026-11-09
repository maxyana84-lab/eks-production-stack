"""Backend REST API. /health is liveness only, /ready checks the database, /metrics is for Prometheus."""
from __future__ import annotations

import os

from flask import Flask, jsonify, request

from . import db
from .metrics import init_metrics


def create_app(connect=db.connect, cors_origins: str | None = None) -> Flask:
    app = Flask(__name__)
    app.json.sort_keys = False
    init_metrics(app, service="backend")

    # The page is served from one host (app.<domain>) and calls the API on another (api.<domain>): the browser only
    # allows that if the API answers with CORS headers. CORS_ALLOW_ORIGIN: comma separated origins, or "*"; empty = off.
    raw = os.environ.get("CORS_ALLOW_ORIGIN", "") if cors_origins is None else cors_origins
    allowed = {o.strip() for o in raw.split(",") if o.strip()}

    @app.after_request
    def cors(response):
        origin = request.headers.get("Origin")
        if allowed and origin and ("*" in allowed or origin in allowed):
            response.headers["Access-Control-Allow-Origin"] = "*" if "*" in allowed else origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Max-Age"] = "600"
        return response

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/ready")
    def ready():
        try:
            conn = connect()
            conn.close()
        except Exception as exc:  # any failure to reach the DB means "not ready"
            return jsonify(status="database unavailable", error=type(exc).__name__), 503
        return jsonify(status="ready")

    @app.get("/api/items")
    def items():
        conn = connect()
        try:
            db.init_schema(conn)
            return jsonify(items=db.list_items(conn))
        finally:
            conn.close()

    @app.post("/api/items")
    def create_item():
        name = (request.get_json(silent=True) or {}).get("name", "").strip()
        if not name:
            return jsonify(error="name is required"), 400
        conn = connect()
        try:
            db.init_schema(conn)
            return jsonify(db.add_item(conn, name)), 201
        finally:
            conn.close()

    @app.errorhandler(Exception)
    def unexpected(exc):
        if hasattr(exc, "code") and isinstance(exc.code, int):  # HTTPException (404 and so on)
            return jsonify(error=getattr(exc, "description", str(exc))), exc.code
        app.logger.exception("unhandled error")
        return jsonify(error="internal error"), 500

    return app

