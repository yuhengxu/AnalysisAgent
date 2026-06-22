from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_UTC_MIGRATION_KEY = "utc_to_beijing_v1"

_TIMESTAMP_TABLES: list[tuple[str, tuple[str, ...]]] = [
    ("llm_dialogue_logs", ("created_at",)),
    ("predictions", ("created_at", "updated_at")),
    ("agent_runs", ("created_at",)),
    ("reports", ("created_at", "updated_at")),
    ("report_templates", ("created_at",)),
    ("forecast_results", ("created_at",)),
    ("factor_assessments", ("created_at",)),
    ("datasets", ("created_at",)),
    ("balance_forecasts", ("created_at",)),
    ("price_series", ("created_at",)),
]


def _migrate_utc_timestamps_to_beijing() -> None:
    """一次性将历史 UTC naive 时间戳转为北京时间存储。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS app_meta ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
        )
        done = conn.execute(
            text("SELECT value FROM app_meta WHERE key = :key"),
            {"key": _UTC_MIGRATION_KEY},
        ).fetchone()
        if done:
            return

        for table, columns in _TIMESTAMP_TABLES:
            exists = conn.execute(
                text(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type='table' AND name = :name"
                ),
                {"name": table},
            ).fetchone()
            if not exists:
                continue
            for column in columns:
                conn.execute(
                    text(
                        f"UPDATE {table} "
                        f"SET {column} = datetime({column}, '+8 hours') "
                        f"WHERE {column} IS NOT NULL"
                    )
                )

        conn.execute(
            text("INSERT INTO app_meta (key, value) VALUES (:key, :value)"),
            {"key": _UTC_MIGRATION_KEY, "value": "done"},
        )


_SNAPSHOT_MONTH_MIGRATION_KEY = "balance_snapshot_month_v1"


def _migrate_balance_snapshot_month() -> None:
    """为 balance_forecasts 增加 snapshot_month 并更新唯一约束。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS app_meta ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
        )
        done = conn.execute(
            text("SELECT value FROM app_meta WHERE key = :key"),
            {"key": _SNAPSHOT_MONTH_MIGRATION_KEY},
        ).fetchone()
        if done:
            return

        exists = conn.execute(
            text(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name = 'balance_forecasts'"
            )
        ).fetchone()
        if not exists:
            conn.execute(
                text("INSERT INTO app_meta (key, value) VALUES (:key, :value)"),
                {"key": _SNAPSHOT_MONTH_MIGRATION_KEY, "value": "done"},
            )
            return

        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(balance_forecasts)")).fetchall()]
        if "snapshot_month" not in cols:
            conn.execute(text("DROP TABLE IF EXISTS balance_forecasts_new"))
            conn.execute(
                text(
                    """
                    CREATE TABLE balance_forecasts_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        dataset_id INTEGER NOT NULL,
                        agency VARCHAR(50) NOT NULL,
                        snapshot_month VARCHAR(10) NOT NULL DEFAULT '',
                        update_date VARCHAR(20) NOT NULL DEFAULT '',
                        supply_demand VARCHAR(10) NOT NULL,
                        period VARCHAR(20) NOT NULL,
                        value REAL NOT NULL,
                        balance_gap REAL,
                        created_at DATETIME,
                        UNIQUE(agency, snapshot_month, supply_demand, period)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO balance_forecasts_new (
                        id, dataset_id, agency, snapshot_month, update_date,
                        supply_demand, period, value, balance_gap, created_at
                    )
                    SELECT
                        id, dataset_id, agency, '', COALESCE(update_date, ''),
                        supply_demand, period, value, balance_gap, created_at
                    FROM balance_forecasts
                    WHERE id IN (
                        SELECT MAX(id)
                        FROM balance_forecasts
                        GROUP BY agency, supply_demand, period
                    )
                    """
                )
            )
            conn.execute(text("DROP TABLE balance_forecasts"))
            conn.execute(text("ALTER TABLE balance_forecasts_new RENAME TO balance_forecasts"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_balance_forecasts_snapshot_month ON balance_forecasts (snapshot_month)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_balance_forecasts_dataset_id ON balance_forecasts (dataset_id)"))

        conn.execute(
            text("INSERT INTO app_meta (key, value) VALUES (:key, :value)"),
            {"key": _SNAPSHOT_MONTH_MIGRATION_KEY, "value": "done"},
        )


def init_db():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_utc_timestamps_to_beijing()
    _migrate_balance_snapshot_month()
    from app.core.database import SessionLocal
    from app.services.report_table_data import ReportTableDataService

    db = SessionLocal()
    try:
        ReportTableDataService(db).migrate_agency_forecasts()
    finally:
        db.close()
