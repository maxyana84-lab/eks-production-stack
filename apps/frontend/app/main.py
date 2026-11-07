"""Frontend: serves a small static page; the page calls the backend API (URL set through API_URL)."""
import os

from flask import Flask, Response, jsonify, send_from_directory

from .metrics import init_metrics


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    init_metrics(app, service="frontend")

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/config.js")
    def config():
        # runtime configuration, so that one image works for every environment
        api_url = os.environ.get("API_URL", "http://localhost:8000")
        return Response(f'window.APP_CONFIG = {{ apiUrl: "{api_url}" }};', mimetype="application/javascript")

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    return app
