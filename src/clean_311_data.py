"""Create a validated, privacy-conscious analysis dataset from the raw 311 extract."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


# Why: Paths are derived from this file instead of the current terminal directory,
# so the script works the same from VS Code, a terminal, or an automated run.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "miami_311_service_requests_raw.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
CLEAN_FILE = PROCESSED_DIR / "miami_311_service_requests_clean.csv"
QUALITY_REPORT = PROCESSED_DIR / "cleaning_quality_report.json"

# Why: This explicit list turns a changing source schema into a transparent
# contract; the pipeline stops early instead of silently producing a broken file.
REQUIRED_SOURCE_COLUMNS = {
    "ticket_id",
    "issue_type",
    "issue_Description",
    "case_owner",
    "city",
    "state",
    "zip_code",
    "District",
    "ticket_created_date_time",
    "ticket_last_updated_date_time",
    "ticket_closed_date_time",
    "ticket_status",
    "method_received",
    "goal_days",
    "actual_completed_days",
    "Ticket_Priority",
    "OverDueFlag",
    "ObjectId",
}

# Why: Public raw files commonly use inconsistent capitalization. Renaming once
# gives SQL and Power BI stable, readable field names without changing values.
RENAME_COLUMNS = {
    "ObjectId": "source_object_id",
    "issue_type": "issue_type_code",
    "issue_Description": "issue_description",
    "District": "district",
    "ticket_created_date_time": "created_at",
    "ticket_last_updated_date_time": "last_updated_at",
    "ticket_closed_date_time": "closed_at",
    "Ticket_Priority": "priority",
    "OverDueFlag": "is_overdue_source",
    "actual_completed_days": "resolution_days_source",
}


def read_raw_data() -> pd.DataFrame:
    """Read the original extract as strings where possible to prevent type loss."""
    # Why: Reading ZIP codes as strings protects leading zeros and keeps the raw
    # values unchanged until we explicitly decide how to clean them.
    frame = pd.read_csv(RAW_FILE, dtype={"zip_code": "string", "ticket_id": "string"})
    missing_columns = REQUIRED_SOURCE_COLUMNS.difference(frame.columns)
    if missing_columns:
        raise ValueError(f"Raw source is missing required columns: {sorted(missing_columns)}")
    return frame


def normalize_text(frame: pd.DataFrame) -> pd.DataFrame:
    """Trim whitespace and convert blank text to missing values."""
    # Why: A blank string and a missing value mean the same thing in analysis but
    # behave differently in filters and SQL joins unless standardized here.
    for column in frame.select_dtypes(include="object").columns:
        frame[column] = frame[column].astype("string").str.strip().replace("", pd.NA)
    return frame


def convert_source_timestamps(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert source epoch-millisecond timestamps to Miami local time."""
    # Why: Source timestamps are epoch milliseconds. Converting through UTC first
    # correctly handles daylight saving time before analysis by local workday/month.
    for column in ["created_at", "last_updated_at", "closed_at"]:
        timestamps = pd.to_datetime(frame[column], unit="ms", errors="coerce", utc=True)
        frame[column] = timestamps.dt.tz_convert("America/New_York")
    return frame


def build_analysis_fields(frame: pd.DataFrame) -> pd.DataFrame:
    """Create consistent dates, durations, and status flags for operational EDA."""
    # Why: Dates split into calendar fields make common Power BI trends possible
    # without requiring each report consumer to repeat transformation logic.
    frame["created_date"] = frame["created_at"].dt.date
    frame["created_year"] = frame["created_at"].dt.year.astype("Int64")
    frame["created_month"] = frame["created_at"].dt.month.astype("Int64")
    frame["created_month_name"] = frame["created_at"].dt.month_name()
    frame["created_day_of_week"] = frame["created_at"].dt.day_name()
    frame["created_year_month"] = frame["created_at"].dt.to_period("M").astype("string")

    # Why: A closure timestamp is a more dependable definition of completion than
    # a status label alone, which can vary across source-system workflows.
    frame["is_closed"] = frame["closed_at"].notna()
    calculated_duration = (frame["closed_at"] - frame["created_at"]).dt.total_seconds() / 86_400
    frame["resolution_days_calculated"] = calculated_duration.round(2)

    # Why: Negative durations cannot represent a real completed request, so they
    # become missing values and are counted in the quality report rather than used.
    frame.loc[frame["resolution_days_calculated"] < 0, "resolution_days_calculated"] = pd.NA

    # Why: Source-provided actual days are retained for auditability, but timestamp
    # derived duration is the primary analytic measure because its calculation is explicit.
    frame["resolution_days_source"] = pd.to_numeric(
        frame["resolution_days_source"], errors="coerce"
    )
    frame["goal_days"] = pd.to_numeric(frame["goal_days"], errors="coerce")
    frame["is_overdue_source"] = pd.to_numeric(frame["is_overdue_source"], errors="coerce")
    return frame


def select_safe_analysis_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep business-useful fields while removing address-level identifiers."""
    # Why: Street address, unit number, property folio, and exact coordinates are
    # not needed for service-level analysis and could expose unnecessary location detail.
    safe_columns = [
        "source_object_id", "ticket_id", "issue_type_code", "issue_description",
        "case_owner", "city", "state", "zip_code", "district", "created_at",
        "last_updated_at", "closed_at", "ticket_status", "method_received", "goal_days",
        "resolution_days_source", "priority", "is_overdue_source", "created_date",
        "created_year", "created_month", "created_month_name", "created_day_of_week",
        "created_year_month", "is_closed", "resolution_days_calculated",
    ]
    return frame[safe_columns].copy()


def validate_clean_data(frame: pd.DataFrame) -> dict[str, int | float]:
    """Return simple quality metrics used to decide whether the dataset is usable."""
    # Why: The unique source identifier is the extraction grain. Duplicates would
    # inflate every operational count and must be caught before EDA or SQL loading.
    duplicate_source_ids = int(frame["source_object_id"].duplicated().sum())
    if duplicate_source_ids:
        raise ValueError(f"Found {duplicate_source_ids} duplicate source object IDs.")

    # Why: The report makes all remaining missingness visible instead of hiding
    # data limitations behind charts that look more certain than the source allows.
    return {
        "row_count": int(len(frame)),
        "unique_ticket_id_count": int(frame["ticket_id"].nunique(dropna=True)),
        "duplicate_source_object_ids": duplicate_source_ids,
        "missing_created_at": int(frame["created_at"].isna().sum()),
        "missing_ticket_id": int(frame["ticket_id"].isna().sum()),
        "missing_issue_type": int(frame["issue_type_code"].isna().sum()),
        "closed_request_count": int(frame["is_closed"].sum()),
        "open_request_count": int((~frame["is_closed"]).sum()),
        "negative_duration_count": int((frame["resolution_days_calculated"] < 0).sum()),
    }


def main() -> None:
    """Run cleaning, write the analysis CSV, and save data-quality evidence."""
    # Why: The raw file is never overwritten; every result is written to a new
    # processed location so the original published extract remains recoverable.
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    clean_frame = read_raw_data().rename(columns=RENAME_COLUMNS)
    clean_frame = normalize_text(clean_frame)
    clean_frame = convert_source_timestamps(clean_frame)
    clean_frame = build_analysis_fields(clean_frame)
    clean_frame = select_safe_analysis_columns(clean_frame)
    quality_metrics = validate_clean_data(clean_frame)

    # Why: ISO-like timestamps retain their offset in CSV, helping SQL and Power BI
    # interpret a reproducible local timestamp rather than a locale-specific string.
    for column in ["created_at", "last_updated_at", "closed_at"]:
        clean_frame[column] = clean_frame[column].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    clean_frame.to_csv(CLEAN_FILE, index=False, encoding="utf-8-sig")
    QUALITY_REPORT.write_text(json.dumps(quality_metrics, indent=2), encoding="utf-8")
    print(f"Created cleaned dataset: {CLEAN_FILE}")
    print(f"Created cleaning quality report: {QUALITY_REPORT}")


if __name__ == "__main__":
    # Why: The guard lets this module be imported for future tests without running
    # the file-writing pipeline as a side effect.
    main()
