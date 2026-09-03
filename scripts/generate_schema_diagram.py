"""Render a readable PNG showing the Miami 311 Power BI star schema."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


# Why: The image is stored with the database deliverables so the SQL model and its
# visual explanation stay together when the project is opened in VS Code or shared.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_FILE = PROJECT_ROOT / "database" / "miami_311_star_schema.png"

# Why: Each table displays only the primary key and relationship-relevant fields;
# the full column list remains authoritative in the SQL schema file.
TABLES = {
    "dim_date": (5.55, 7.25, 3.15, 1.85, ["PK  date_key", "calendar_date", "year • quarter • month", "day_name • is_weekend"]),
    "dim_issue_type": (0.35, 6.25, 3.45, 1.7, ["PK  issue_type_key", "issue_type_code", "issue_description"]),
    "dim_case_owner": (0.35, 3.95, 3.45, 1.45, ["PK  case_owner_key", "case_owner_name"]),
    "dim_location": (0.35, 1.35, 3.45, 1.7, ["PK  location_key", "city • state", "zip_code • district"]),
    "fact_service_request": (5.1, 3.0, 4.05, 3.25, ["PK  service_request_key", "ticket_id • source_object_id", "FK  created_date_key • closed_date_key", "FK  location • issue • owner", "FK  method • priority • status", "measures: goal / resolution / overdue"]),
    "dim_intake_method": (10.4, 6.25, 3.45, 1.45, ["PK  intake_method_key", "intake_method_name"]),
    "dim_priority": (10.4, 4.05, 3.45, 1.45, ["PK  priority_key", "priority_name"]),
    "dim_status": (10.4, 1.45, 3.45, 1.45, ["PK  status_key", "status_name"]),
}


def draw_table(axis, name, x, y, width, height, fields) -> None:
    """Draw one schema table with a title band and key fields."""
    # Why: A shared table style lets the relationship lines remain the focus rather
    # than making the diagram look like a screenshot of implementation details.
    is_fact = name == "fact_service_request"
    fill = "#D8EAF8" if is_fact else "#F7FAFC"
    title_fill = "#1F4E79" if is_fact else "#4E7B9A"
    axis.add_patch(FancyBboxPatch((x, y), width, height, boxstyle="round,pad=0.04", facecolor=fill,
                                  edgecolor="#315A73", linewidth=1.2, zorder=3))
    axis.add_patch(FancyBboxPatch((x, y + height - 0.43), width, 0.43, boxstyle="round,pad=0.04",
                                  facecolor=title_fill, edgecolor=title_fill, zorder=4))
    axis.text(x + width / 2, y + height - 0.215, name, ha="center", va="center", color="white",
              fontsize=10, fontweight="bold", zorder=5)
    for index, field in enumerate(fields):
        axis.text(x + 0.18, y + height - 0.7 - index * 0.34, field, ha="left", va="center",
                  fontsize=8.5, color="#17324D", zorder=5)


def connect(axis, start, end) -> None:
    """Draw a dimension-to-fact relationship behind the table boxes."""
    # Why: Arrowheads point toward the fact table, reinforcing that dimension keys
    # are referenced many times by the central one-row-per-request fact table.
    axis.annotate("", xy=end, xytext=start, arrowprops={"arrowstyle": "->", "color": "#7895A9", "lw": 1.6}, zorder=1)


def main() -> None:
    """Create the schema diagram image."""
    # Why: The figure size and hidden axes prioritize a clean, readable relationship
    # diagram that can be reviewed beside the SQL file or included in a portfolio.
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(14, 9))
    axis.set(xlim=(0, 14.2), ylim=(0.6, 9.6))
    axis.axis("off")
    figure.suptitle("Miami 311 Service Operations — Power BI Star Schema", fontsize=16, fontweight="bold", color="#17324D")
    connect(axis, (7.1, 7.25), (7.1, 6.25))
    connect(axis, (3.8, 7.05), (5.1, 5.55))
    connect(axis, (3.8, 4.65), (5.1, 4.8))
    connect(axis, (3.8, 2.2), (5.1, 3.75))
    connect(axis, (10.4, 6.95), (9.15, 5.45))
    connect(axis, (10.4, 4.75), (9.15, 4.6))
    connect(axis, (10.4, 2.15), (9.15, 3.65))
    for name, values in TABLES.items():
        draw_table(axis, name, *values)
    figure.text(0.5, 0.035, "Arrow direction: dimension table → fact_service_request foreign key", ha="center", fontsize=9, color="#4C6274")
    figure.tight_layout(rect=(0, 0.06, 1, 0.94))
    figure.savefig(OUTPUT_FILE, dpi=200, bbox_inches="tight")
    plt.close(figure)
    print(f"Created schema image: {OUTPUT_FILE}")


if __name__ == "__main__":
    # Why: This guard allows future code to import the table layout without
    # automatically rendering an image.
    main()
