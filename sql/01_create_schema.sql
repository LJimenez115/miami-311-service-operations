-- Why: SQLite is portable, requires no server setup, and Power BI can connect to it
-- through its SQLite connector or through an exported fact/dimension table set.
PRAGMA foreign_keys = ON;

-- Why: A dedicated date dimension prevents repeated calendar calculations in every
-- dashboard visual and supports both created-date and closed-date analysis.
CREATE TABLE IF NOT EXISTS dim_date (
    date_key INTEGER PRIMARY KEY,
    calendar_date TEXT NOT NULL UNIQUE,
    calendar_year INTEGER NOT NULL,
    calendar_quarter INTEGER NOT NULL,
    calendar_month INTEGER NOT NULL,
    month_name TEXT NOT NULL,
    day_of_month INTEGER NOT NULL,
    day_name TEXT NOT NULL,
    is_weekend INTEGER NOT NULL CHECK (is_weekend IN (0, 1))
);
-- Why: This table supplies one consistent calendar definition to every fact row.

-- Why: Location is kept at ZIP-and-district level to support geographic analysis
-- without restoring the exact addresses intentionally removed during cleaning.
CREATE TABLE IF NOT EXISTS dim_location (
    location_key INTEGER PRIMARY KEY,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    zip_code TEXT NOT NULL,
    district INTEGER NOT NULL,
    UNIQUE (city, state, zip_code, district)
);
-- Why: The composite uniqueness rule prevents duplicate dimension members.

-- Why: Issue type is separated from requests because each category appears across
-- many tickets and needs a single source of business naming.
CREATE TABLE IF NOT EXISTS dim_issue_type (
    issue_type_key INTEGER PRIMARY KEY,
    issue_type_code TEXT NOT NULL,
    issue_description TEXT NOT NULL,
    UNIQUE (issue_type_code, issue_description)
);
-- Why: This dimension supports category-level volume and resolution analysis.

-- Why: Case owner is a reusable operational entity, not an attribute that should
-- be repeated as free text on every request row.
CREATE TABLE IF NOT EXISTS dim_case_owner (
    case_owner_key INTEGER PRIMARY KEY,
    case_owner_name TEXT NOT NULL UNIQUE
);
-- Why: This enables workload and turnaround comparisons by responsible team.

-- Why: Intake method identifies how a resident submitted a service request.
CREATE TABLE IF NOT EXISTS dim_intake_method (
    intake_method_key INTEGER PRIMARY KEY,
    intake_method_name TEXT NOT NULL UNIQUE
);
-- Why: This makes channel-demand analysis a simple dimension filter in Power BI.

-- Why: Priority is stored once because it is a controlled classification shared by
-- many requests, while the fact table keeps only the foreign key.
CREATE TABLE IF NOT EXISTS dim_priority (
    priority_key INTEGER PRIMARY KEY,
    priority_name TEXT NOT NULL UNIQUE
);
-- Why: This supports asking whether priority level affects volume or resolution time.

-- Why: Status is modeled separately so source workflow labels remain consistent in
-- reports and can be extended later with a status-group field if needed.
CREATE TABLE IF NOT EXISTS dim_status (
    status_key INTEGER PRIMARY KEY,
    status_name TEXT NOT NULL UNIQUE
);
-- Why: This avoids repeating status text tens of thousands of times in the fact table.

-- Why: The fact table records one row per service-request ticket and holds the
-- numeric measures and foreign keys that connect the business dimensions.
CREATE TABLE IF NOT EXISTS fact_service_request (
    service_request_key INTEGER PRIMARY KEY,
    source_object_id INTEGER NOT NULL UNIQUE,
    ticket_id TEXT NOT NULL UNIQUE,
    created_date_key INTEGER NOT NULL,
    closed_date_key INTEGER,
    location_key INTEGER NOT NULL,
    issue_type_key INTEGER NOT NULL,
    case_owner_key INTEGER NOT NULL,
    intake_method_key INTEGER NOT NULL,
    priority_key INTEGER NOT NULL,
    status_key INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    last_updated_at TEXT,
    closed_at TEXT,
    goal_days REAL,
    resolution_days_source REAL,
    resolution_days_calculated REAL,
    is_overdue_source INTEGER,
    is_closed INTEGER NOT NULL CHECK (is_closed IN (0, 1)),
    FOREIGN KEY (created_date_key) REFERENCES dim_date(date_key),
    FOREIGN KEY (closed_date_key) REFERENCES dim_date(date_key),
    FOREIGN KEY (location_key) REFERENCES dim_location(location_key),
    FOREIGN KEY (issue_type_key) REFERENCES dim_issue_type(issue_type_key),
    FOREIGN KEY (case_owner_key) REFERENCES dim_case_owner(case_owner_key),
    FOREIGN KEY (intake_method_key) REFERENCES dim_intake_method(intake_method_key),
    FOREIGN KEY (priority_key) REFERENCES dim_priority(priority_key),
    FOREIGN KEY (status_key) REFERENCES dim_status(status_key)
);
-- Why: Foreign keys protect referential integrity so every request joins to valid dimensions.

-- Why: These indexes speed common Power BI filters and SQL aggregations without
-- duplicating the table data or changing the business grain.
CREATE INDEX IF NOT EXISTS idx_fact_created_date ON fact_service_request(created_date_key);
CREATE INDEX IF NOT EXISTS idx_fact_issue_type ON fact_service_request(issue_type_key);
CREATE INDEX IF NOT EXISTS idx_fact_location ON fact_service_request(location_key);
CREATE INDEX IF NOT EXISTS idx_fact_case_owner ON fact_service_request(case_owner_key);
CREATE INDEX IF NOT EXISTS idx_fact_status ON fact_service_request(status_key);
-- Why: Indexes make the expected dashboard filters responsive as the data grows.
