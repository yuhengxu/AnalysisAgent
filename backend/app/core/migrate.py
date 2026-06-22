"""SQLite 轻量迁移：为已有库补列。"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _column_exists(engine: Engine, table: str, column: str) -> bool:
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def run_migrations(engine: Engine) -> None:
    with engine.begin() as conn:
        if not _column_exists(engine, "users", "id"):
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS users ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "username VARCHAR(50) NOT NULL UNIQUE, "
                    "hashed_password VARCHAR(200) NOT NULL, "
                    "role VARCHAR(20) DEFAULT 'user', "
                    "created_at DATETIME"
                    ")"
                )
            )
        if not _column_exists(engine, "reports", "user_id"):
            conn.execute(text("ALTER TABLE reports ADD COLUMN user_id INTEGER"))
        if not _column_exists(engine, "predictions", "user_id"):
            conn.execute(text("ALTER TABLE predictions ADD COLUMN user_id INTEGER"))
        if not _column_exists(engine, "agency_forecast_manual", "id"):
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS agency_forecast_manual ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "year INTEGER NOT NULL, "
                    "month INTEGER NOT NULL, "
                    "rows_json TEXT NOT NULL DEFAULT '[]', "
                    "updated_by INTEGER, "
                    "updated_at DATETIME, "
                    "UNIQUE(year, month)"
                    ")"
                )
            )
        if not _column_exists(engine, "report_table_snapshots", "id"):
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS report_table_snapshots ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "review_year INTEGER NOT NULL, "
                    "review_month INTEGER NOT NULL, "
                    "table_key VARCHAR(40) NOT NULL, "
                    "source_category VARCHAR(10) NOT NULL, "
                    "title VARCHAR(200) DEFAULT '', "
                    "source VARCHAR(200) DEFAULT '', "
                    "headers_json TEXT DEFAULT '[]', "
                    "rows_json TEXT DEFAULT '[]', "
                    "source_urls_json TEXT DEFAULT '[]', "
                    "is_manual_override BOOLEAN DEFAULT 0, "
                    "computed_at DATETIME, "
                    "updated_by INTEGER, "
                    "updated_at DATETIME, "
                    "UNIQUE(review_year, review_month, table_key)"
                    ")"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_report_table_snapshots_ym "
                    "ON report_table_snapshots (review_year, review_month)"
                )
            )
        if not _column_exists(engine, "users", "allowed_pages_json"):
            conn.execute(
                text("ALTER TABLE users ADD COLUMN allowed_pages_json TEXT DEFAULT '[]'")
            )
        if not _column_exists(engine, "users", "is_active"):
            conn.execute(
                text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1")
            )
        if not _column_exists(engine, "users", "updated_at"):
            conn.execute(
                text("ALTER TABLE users ADD COLUMN updated_at DATETIME")
            )
        conn.execute(
            text(
                """
                UPDATE users
                SET allowed_pages_json = :pages
                WHERE role != 'admin'
                  AND (
                    allowed_pages_json IS NULL
                    OR allowed_pages_json = ''
                    OR allowed_pages_json = '[]'
                  )
                """
            ),
            {
                "pages": '["dashboard","data","analysis","prediction","forecast","reports"]'
            },
        )
