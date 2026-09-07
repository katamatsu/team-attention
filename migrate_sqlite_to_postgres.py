"""Copy the local attendance.db into a PostgreSQL database.

Usage:
    $env:DATABASE_URL = "postgresql://..."
    python migrate_sqlite_to_postgres.py
"""

import os
import sqlite3
from pathlib import Path

import psycopg


BASE_DIR = Path(__file__).resolve().parent
SQLITE_PATH = BASE_DIR / "attendance.db"
SCHEMA_PATH = BASE_DIR / "supabase_schema.sql"
TABLES = (
    "members",
    "practices",
    "games",
    "attendance",
    "game_stats",
    "opponent_players",
    "opponent_stats",
    "events",
    "dashboard_memos",
    "game_participation",
)


def copy_table(sqlite_connection, postgres_connection, table):
    if not sqlite_connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone():
        return 0
    sqlite_rows = sqlite_connection.execute(f"SELECT * FROM {table}").fetchall()
    if not sqlite_rows:
        return 0

    columns = [column[1] for column in sqlite_connection.execute(f"PRAGMA table_info({table})")]
    column_list = ", ".join(columns)
    placeholders = ", ".join("%s" for _ in columns)
    query = f"INSERT INTO {table} ({column_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
    with postgres_connection.cursor() as cursor:
        cursor.executemany(query, [tuple(row) for row in sqlite_rows])
    return len(sqlite_rows)


def apply_schema(postgres_connection):
    if not SCHEMA_PATH.exists():
        raise SystemExit(f"Schema file not found: {SCHEMA_PATH}")
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with postgres_connection.cursor() as cursor:
        cursor.execute(schema)
    postgres_connection.commit()


def reset_identity_sequences(postgres_connection):
    with postgres_connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1), "
                f"(SELECT COUNT(*) > 0 FROM {table}))"
            )


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set")
    if not SQLITE_PATH.exists():
        raise SystemExit(f"SQLite database not found: {SQLITE_PATH}")

    with sqlite3.connect(SQLITE_PATH) as sqlite_connection, psycopg.connect(database_url) as postgres_connection:
        apply_schema(postgres_connection)
        counts = {table: copy_table(sqlite_connection, postgres_connection, table) for table in TABLES}
        reset_identity_sequences(postgres_connection)
        postgres_connection.commit()

    for table, count in counts.items():
        print(f"{table}: {count} rows copied")
    print("Migration completed")


if __name__ == "__main__":
    main()
