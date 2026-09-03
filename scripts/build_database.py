"""Build the normalized PostgreSQL database from the cleaned Miami 311 dataset."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, make_url


# Why: Every path is calculated from this file so the build works from VS Code or
# a terminal without requiring the user to change into a particular directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLEAN_FILE = PROJECT_ROOT / "data" / "processed" / "miami_311_service_requests_clean.csv"
SCHEMA_FILE = PROJECT_ROOT / "sql" / "01_create_schema.sql"
DATABASE_DIR = PROJECT_ROOT / "database"
BUILD_REPORT = DATABASE_DIR / "database_build_report.json"
DATABASE_NAME = "miami_311_operations"


def get_database_url() -> str:
    """Read and validate the local PostgreSQL connection string."""
    # Why: Loading `.env` keeps the password outside source control while allowing a
    # beginner-friendly `DATABASE_URL` configuration in VS Code or a terminal.
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is missing. Copy .env.example to .env and add your password.")
    parsed_url = make_url(database_url)
    # Why: The schema intentionally drops only project tables for repeatable loads,
    # so this guard prevents a connection typo from targeting another database.
    if parsed_url.database != DATABASE_NAME:
        raise ValueError(f"DATABASE_URL must use the dedicated `{DATABASE_NAME}` database.")
    return database_url


def safe_text(series: pd.Series) -> pd.Series:
    """Return a non-null text dimension value for a source column."""
    # Why: Dimension foreign keys cannot be null in this star schema, so missing
    # values become an explicit 'Unknown' member rather than disappearing in joins.
    return series.astype("string").fillna("Unknown").str.strip().replace("", "Unknown")


def make_dimension(
    frame: pd.DataFrame,
    columns: list[str],
    key_column: str,
    table_name: str,
    connection: Connection,
    database_column_names: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Create one surrogate-key dimension and return its natural-key mapping."""
    # Why: Surrogate keys make fact rows compact and protect the model if a business
    # label changes in the source later.
    dimension = frame[columns].drop_duplicates().sort_values(columns).reset_index(drop=True)
    dimension.insert(0, key_column, range(1, len(dimension) + 1))
    # Why: Some source labels are concise (`priority`), while database labels are
    # explicit (`priority_name`). The returned mapping keeps source names for merges.
    database_dimension = dimension.rename(columns=database_column_names or {})
    database_dimension.to_sql(table_name, connection, if_exists="append", index=False)
    return dimension


def build_date_dimension(frame: pd.DataFrame, connection: Connection) -> pd.DataFrame:
    """Create one row per created or closed local calendar date."""
    # Why: A single conformed date dimension serves both created and closed dates,
    # which enables consistent calendar filtering across multiple measures.
    created_dates = pd.to_datetime(frame["created_date"], errors="coerce")
    closed_dates = pd.to_datetime(frame["closed_at"], errors="coerce", utc=True).dt.tz_convert(
        "America/New_York"
    ).dt.normalize().dt.tz_localize(None)
    all_dates = pd.Series(pd.concat([created_dates, closed_dates]).dropna().unique())
    dates = pd.DataFrame({"calendar_date_value": sorted(all_dates)})
    dates["date_key"] = dates["calendar_date_value"].dt.strftime("%Y%m%d").astype(int)
    dates["calendar_date"] = dates["calendar_date_value"].dt.date
    dates["calendar_year"] = dates["calendar_date_value"].dt.year
    dates["calendar_quarter"] = dates["calendar_date_value"].dt.quarter
    dates["calendar_month"] = dates["calendar_date_value"].dt.month
    dates["month_name"] = dates["calendar_date_value"].dt.month_name()
    dates["day_of_month"] = dates["calendar_date_value"].dt.day
    dates["day_name"] = dates["calendar_date_value"].dt.day_name()
    dates["is_weekend"] = dates["calendar_date_value"].dt.dayofweek.isin([5, 6])
    output_columns = [
        "date_key", "calendar_date", "calendar_year", "calendar_quarter", "calendar_month",
        "month_name", "day_of_month", "day_name", "is_weekend",
    ]
    dates[output_columns].to_sql("dim_date", connection, if_exists="append", index=False)
    return dates[["calendar_date_value", "date_key"]]


def main() -> None:
    """Create the database, load dimensions then facts, and verify row counts."""
    # Why: The source is the cleaned CSV only; raw address-level data is never
    # loaded into the database intended for analysis and dashboarding.
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    source = pd.read_csv(CLEAN_FILE, dtype={"ticket_id": "string", "zip_code": "string"})

    # Why: These normalized text fields are used to create stable natural keys for
    # all dimensions before the numeric foreign keys are added to the fact table.
    for column in ["issue_type_code", "issue_description", "case_owner", "city", "state",
                   "zip_code", "method_received", "priority", "ticket_status"]:
        source[column] = safe_text(source[column])
    source["district"] = pd.to_numeric(source["district"], errors="coerce").fillna(-1).astype(int)
    source["created_date_value"] = pd.to_datetime(source["created_date"], errors="coerce")
    if source["created_date_value"].isna().any():
        raise ValueError("Every fact row needs a valid created_date.")
    if source["ticket_id"].duplicated().any():
        raise ValueError("ticket_id must be unique before loading facts.")

    # Why: PostgreSQL holds the shared database outside this repository, while the
    # schema file recreates only the dedicated project's tables on each verified run.
    engine = create_engine(get_database_url())
    with engine.begin() as connection:
        for statement in SCHEMA_FILE.read_text(encoding="utf-8").split(";"):
            if statement.strip():
                connection.exec_driver_sql(statement)

        date_dimension = build_date_dimension(source, connection)
        location_dimension = make_dimension(
            source, ["city", "state", "zip_code", "district"], "location_key", "dim_location", connection
        )
        issue_dimension = make_dimension(
            source, ["issue_type_code", "issue_description"], "issue_type_key", "dim_issue_type", connection
        )
        owner_dimension = make_dimension(
            source, ["case_owner"], "case_owner_key", "dim_case_owner", connection,
            {"case_owner": "case_owner_name"},
        )
        method_dimension = make_dimension(
            source, ["method_received"], "intake_method_key", "dim_intake_method", connection,
            {"method_received": "intake_method_name"},
        )
        priority_dimension = make_dimension(
            source, ["priority"], "priority_key", "dim_priority", connection,
            {"priority": "priority_name"},
        )
        status_dimension = make_dimension(
            source, ["ticket_status"], "status_key", "dim_status", connection,
            {"ticket_status": "status_name"},
        )

        # Why: Each merge replaces a human-readable source label with the matching
        # surrogate key, preserving the one-row-per-ticket grain in the fact table.
        fact = source.merge(
            date_dimension.rename(columns={"calendar_date_value": "created_date_value", "date_key": "created_date_key"}),
            on="created_date_value", how="left",
        )
        closed_date_value = pd.to_datetime(fact["closed_at"], errors="coerce", utc=True).dt.tz_convert(
            "America/New_York"
        ).dt.normalize().dt.tz_localize(None)
        fact = fact.merge(
            date_dimension.rename(columns={"calendar_date_value": "closed_date_value", "date_key": "closed_date_key"}),
            left_on=closed_date_value, right_on="closed_date_value", how="left",
        ).drop(columns=["closed_date_value"])
        for dimension, keys in [
            (location_dimension, ["city", "state", "zip_code", "district"]),
            (issue_dimension, ["issue_type_code", "issue_description"]),
            (owner_dimension, ["case_owner"]),
            (method_dimension, ["method_received"]),
            (priority_dimension, ["priority"]),
            (status_dimension, ["ticket_status"]),
        ]:
            fact = fact.merge(dimension, on=keys, how="left")

        fact.insert(0, "service_request_key", range(1, len(fact) + 1))
        # Why: Explicit datetime and boolean types let PostgreSQL enforce the same
        # business meaning that Power BI will use for time and status calculations.
        for column in ["created_at", "last_updated_at", "closed_at"]:
            fact[column] = pd.to_datetime(fact[column], errors="coerce", utc=True)
        fact["is_closed"] = fact["is_closed"].astype(bool)
        overdue_numeric = pd.to_numeric(fact["is_overdue_source"], errors="coerce")
        fact["is_overdue_source"] = overdue_numeric.map(
            lambda value: None if pd.isna(value) else bool(value)
        )
        fact_columns = [
            "service_request_key", "source_object_id", "ticket_id", "created_date_key", "closed_date_key",
            "location_key", "issue_type_key", "case_owner_key", "intake_method_key", "priority_key",
            "status_key", "created_at", "last_updated_at", "closed_at", "goal_days",
            "resolution_days_source", "resolution_days_calculated", "is_overdue_source", "is_closed",
        ]
        fact[fact_columns].to_sql("fact_service_request", connection, if_exists="append", index=False)

        # Why: Counting each table after loading confirms both the expected fact
        # grain and that dimensions were populated before the database is delivered.
        counts = {
            table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            for table in [
                "dim_date", "dim_location", "dim_issue_type", "dim_case_owner", "dim_intake_method",
                "dim_priority", "dim_status", "fact_service_request",
            ]
        }
        # Why: PostgreSQL rejects invalid foreign keys during the insert itself; a
        # successful transaction is therefore the integrity check for this rebuild.
        foreign_key_check = "passed (PostgreSQL constraints enforced during insert)"

    engine.dispose()

    # Why: The build report provides quick evidence that the database was created
    # completely and can be compared to the cleaned-data row count in future reruns.
    BUILD_REPORT.write_text(
        json.dumps({"database_platform": "PostgreSQL", "database_name": DATABASE_NAME,
                    "table_row_counts": counts, "foreign_key_check": foreign_key_check}, indent=2),
        encoding="utf-8",
    )
    print(f"Loaded PostgreSQL database: {DATABASE_NAME}")
    print(f"Created build report: {BUILD_REPORT}")


if __name__ == "__main__":
    # Why: The guard permits importing helper functions for testing without an
    # accidental rebuild of the dedicated PostgreSQL project database.
    main()
