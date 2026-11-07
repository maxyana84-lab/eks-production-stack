"""PostgreSQL access. Connection settings come from DB_* environment variables (ConfigMap + Secret in Kubernetes)."""
import os

import psycopg2


def connect():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "5432")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        dbname=os.environ.get("DB_NAME", "postgres"),
        connect_timeout=int(os.environ.get("DB_CONNECT_TIMEOUT", "3")),
    )


def init_schema(conn) -> None:
    with conn, conn.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS items (id SERIAL PRIMARY KEY, name TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT now())")


def list_items(conn) -> list[dict]:
    with conn, conn.cursor() as cur:
        cur.execute("SELECT id, name FROM items ORDER BY id DESC LIMIT 50")
        return [{"id": r[0], "name": r[1]} for r in cur.fetchall()]


def add_item(conn, name: str) -> dict:
    with conn, conn.cursor() as cur:
        cur.execute("INSERT INTO items (name) VALUES (%s) RETURNING id", (name,))
        return {"id": cur.fetchone()[0], "name": name}
