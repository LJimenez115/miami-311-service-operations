# Miami 311 Service Operations & SLA Optimization

This project analyzes public City of Miami 311 requests from the official City of Miami ArcGIS layer. The raw source remains unchanged in `data/raw/`; all analysis uses the privacy-conscious cleaned file created in `data/processed/`.

## Run the EDA pipeline

```bash
# Why: Create an isolated environment so this project does not alter Python packages used by other projects.
python3 -m venv .venv
# Why: Install only the libraries listed in the reproducible project requirements file.
.venv/bin/pip install -r requirements.txt
# Why: Run cleaning first, then EDA, to ensure every report uses the same validated cleaned dataset.
.venv/bin/python src/run_pipeline.py
```

## Load the PostgreSQL database

This project uses PostgreSQL rather than a local SQLite file. Install and start PostgreSQL first, then run the following from this project folder.

```bash
# Why: Create one isolated database so this project's rebuild never changes another local database.
psql -d postgres -f sql/00_create_database.sql
# Why: Copy the safe template locally; `.env` is ignored so the password cannot be committed.
cp .env.example .env
# Why: After adding your PostgreSQL password to `.env`, this command creates the schema and loads the cleaned data.
.venv/bin/python scripts/build_database.py
```

Power BI connects through **Get Data → PostgreSQL database**. Use `localhost`, the default port `5432`, and the database name `miami_311_operations`; do not publish the password or `.env` file.

## What is produced

- `data/processed/miami_311_service_requests_clean.csv` — cleaned, analysis-ready dataset
- `reports/data_quality_summary.csv` — documented completeness and validity checks
- `reports/*.csv` — Power BI-ready aggregate tables
- `reports/*.png` — EDA chart images
- PostgreSQL tables — a star schema with one service-request fact table and seven dimensions

## Privacy choice

The raw source includes street address, unit number, property folio, and exact coordinates. The cleaning script intentionally removes those fields from the analysis dataset. ZIP code and commission district remain for geographic operational analysis without exposing unnecessary address-level detail.

## Coverage caution

The source begins late on September 30, 2022 and ends on August 10, 2024. Treat September 2022 and August 2024 as partial months; do not compare their request volumes directly to full months.
