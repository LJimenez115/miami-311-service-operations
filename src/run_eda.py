"""Generate transparent operational EDA tables and charts from cleaned 311 data."""

from __future__ import annotations

from pathlib import Path

# Why: The non-interactive backend lets the script save chart files reliably from
# VS Code terminals and automated runs without requiring a graphical Python window.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


# Why: The source is the cleaned dataset only, preventing raw address-level fields
# from accidentally appearing in charts or aggregate files.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLEAN_FILE = PROJECT_ROOT / "data" / "processed" / "miami_311_service_requests_clean.csv"
REPORT_DIR = PROJECT_ROOT / "reports"

# Why: One neutral theme makes all generated figures look consistent and readable
# when reviewed in a portfolio, README, or Power BI planning meeting.
sns.set_theme(style="whitegrid", palette="deep")


def read_clean_data() -> pd.DataFrame:
    """Load and type the fields used in operational measures."""
    # Why: Parsing these dates at read time makes the code fail early if the clean
    # file has been modified into an invalid format.
    frame = pd.read_csv(CLEAN_FILE, parse_dates=["created_at", "last_updated_at", "closed_at"])
    frame["created_year_month"] = pd.to_datetime(frame["created_year_month"], errors="coerce")
    return frame


def export_quality_summary(frame: pd.DataFrame) -> None:
    """Export a compact quality table for review before interpreting results."""
    # Why: EDA should state the number of valid records behind a metric, not only
    # publish visual conclusions from an unknown or incomplete subset.
    summary = pd.DataFrame(
        {
            "metric": ["total_requests", "closed_requests", "requests_with_resolution_duration",
                       "missing_issue_type", "missing_zip_code", "missing_case_owner"],
            "value": [len(frame), frame["is_closed"].sum(), frame["resolution_days_calculated"].notna().sum(),
                      frame["issue_type_code"].isna().sum(), frame["zip_code"].isna().sum(),
                      frame["case_owner"].isna().sum()],
        }
    )
    summary.to_csv(REPORT_DIR / "data_quality_summary.csv", index=False)


def export_operational_tables(frame: pd.DataFrame) -> None:
    """Create Power BI-ready aggregates for volume and service-performance questions."""
    # Why: Monthly volume exposes demand seasonality and workload changes over time.
    monthly = (
        frame.groupby("created_year_month", dropna=True)
        .agg(request_count=("ticket_id", "size"), closed_count=("is_closed", "sum"))
        .reset_index()
    )
    monthly["closure_rate"] = (monthly["closed_count"] / monthly["request_count"]).round(4)
    monthly.to_csv(REPORT_DIR / "monthly_request_volume.csv", index=False)

    # Why: Top categories identify the request types most likely to drive staffing,
    # automation, or process-improvement conversations.
    top_issues = (
        frame.groupby(["issue_type_code", "issue_description"], dropna=False)
        .agg(request_count=("ticket_id", "size"), median_resolution_days=("resolution_days_calculated", "median"),
             overdue_rate=("is_overdue_source", "mean"))
        .reset_index()
        .sort_values("request_count", ascending=False)
    )
    top_issues.to_csv(REPORT_DIR / "issue_type_performance.csv", index=False)

    # Why: Owner-level metrics reveal workload and speed patterns while retaining
    # counts, so a small group is not overinterpreted as a performance outlier.
    owner_performance = (
        frame.groupby("case_owner", dropna=False)
        .agg(request_count=("ticket_id", "size"), median_resolution_days=("resolution_days_calculated", "median"),
             average_resolution_days=("resolution_days_calculated", "mean"), overdue_rate=("is_overdue_source", "mean"))
        .reset_index()
        .query("request_count >= 30")
        .sort_values("request_count", ascending=False)
    )
    owner_performance.to_csv(REPORT_DIR / "owner_performance.csv", index=False)

    # Why: ZIP-level aggregation enables geographic demand analysis without carrying
    # the street address or exact coordinates into the analysis layer.
    zip_performance = (
        frame.groupby("zip_code", dropna=False)
        .agg(request_count=("ticket_id", "size"), median_resolution_days=("resolution_days_calculated", "median"),
             overdue_rate=("is_overdue_source", "mean"))
        .reset_index()
        .sort_values("request_count", ascending=False)
    )
    zip_performance.to_csv(REPORT_DIR / "zip_code_performance.csv", index=False)

    # Why: Status counts distinguish requests that are unresolved from records that
    # merely have an unusual category or owner value.
    status_summary = (
        frame.groupby("ticket_status", dropna=False)
        .size()
        .reset_index(name="request_count")
        .sort_values("request_count", ascending=False)
    )
    status_summary.to_csv(REPORT_DIR / "status_summary.csv", index=False)


def save_charts(frame: pd.DataFrame) -> None:
    """Write exploratory charts that summarize volume, categories, and duration."""
    # Why: The volume chart establishes whether workload is stable, seasonal, or
    # changing before looking for explanations in category or location fields.
    monthly = frame.groupby("created_year_month", dropna=True).size().reset_index(name="request_count")
    figure, axis = plt.subplots(figsize=(12, 5))
    sns.lineplot(data=monthly, x="created_year_month", y="request_count", marker="o", ax=axis)
    axis.set(title="Monthly 311 Request Volume", xlabel="Month", ylabel="Requests")
    figure.autofmt_xdate()
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "monthly_request_volume.png", dpi=180)
    plt.close(figure)

    # Why: Limiting the display to ten categories preserves legibility while the
    # complete category table remains available in CSV for full Power BI analysis.
    top_issues = frame["issue_description"].value_counts(dropna=False).head(10).sort_values()
    figure, axis = plt.subplots(figsize=(10, 6))
    top_issues.plot(kind="barh", ax=axis, color="#2A6F97")
    axis.set(title="Top 10 Request Categories", xlabel="Requests", ylabel="Category")
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "top_request_categories.png", dpi=180)
    plt.close(figure)

    # Why: The 99th percentile cap prevents extreme records from flattening the
    # main distribution while still retaining every record in the CSV outputs.
    durations = frame["resolution_days_calculated"].dropna()
    if not durations.empty:
        capped_durations = durations[durations <= durations.quantile(0.99)]
        figure, axis = plt.subplots(figsize=(10, 5))
        sns.histplot(capped_durations, bins=30, ax=axis, color="#4C956C")
        axis.set(title="Resolution Duration Distribution (through 99th percentile)",
                 xlabel="Days from creation to closure", ylabel="Closed requests")
        figure.tight_layout()
        figure.savefig(REPORT_DIR / "resolution_duration_distribution.png", dpi=180)
        plt.close(figure)


def main() -> None:
    """Run the complete EDA reporting stage."""
    # Why: A dedicated reports folder separates reusable analysis outputs from raw
    # and row-level processed data, making the future Power BI import choice clear.
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    frame = read_clean_data()
    export_quality_summary(frame)
    export_operational_tables(frame)
    save_charts(frame)
    print(f"Created EDA tables and charts in: {REPORT_DIR}")


if __name__ == "__main__":
    # Why: The guard keeps importing this module safe for tests or future notebooks.
    main()
