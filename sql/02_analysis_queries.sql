-- Why: This query establishes the size of the completed database and the share of
-- requests with a closure timestamp before interpreting operational performance.
SELECT
    COUNT(*) AS total_requests,
    SUM(is_closed) AS closed_requests,
    ROUND(100.0 * SUM(is_closed) / COUNT(*), 2) AS closure_rate_percent
FROM fact_service_request;
-- Why: The result is the primary data-volume quality check for the loaded database.

-- Why: This query identifies the service categories creating the largest workload.
SELECT
    i.issue_description,
    COUNT(*) AS request_count,
    ROUND(MEDIAN(f.resolution_days_calculated), 2) AS median_resolution_days
FROM fact_service_request AS f
JOIN dim_issue_type AS i ON f.issue_type_key = i.issue_type_key
GROUP BY i.issue_description
ORDER BY request_count DESC
LIMIT 10;
-- Why: In SQLite versions without MEDIAN(), replace that expression with AVG() or
-- calculate the median in Power BI/Python; the joins and grouping remain the same.

-- Why: This query compares workload, turnaround, and source overdue flags by team.
SELECT
    o.case_owner_name AS case_owner,
    COUNT(*) AS request_count,
    ROUND(AVG(f.resolution_days_calculated), 2) AS average_resolution_days,
    ROUND(100.0 * AVG(f.is_overdue_source), 2) AS source_overdue_rate_percent
FROM fact_service_request AS f
JOIN dim_case_owner AS o ON f.case_owner_key = o.case_owner_key
GROUP BY o.case_owner_name
ORDER BY request_count DESC;
-- Why: This produces a management-ready team view without exposing address-level data.

-- Why: This query shows monthly demand, using the created-date foreign key to join
-- the shared date dimension rather than recalculating month values from timestamps.
SELECT
    d.calendar_year,
    d.calendar_month,
    d.month_name,
    COUNT(*) AS request_count
FROM fact_service_request AS f
JOIN dim_date AS d ON f.created_date_key = d.date_key
GROUP BY d.calendar_year, d.calendar_month, d.month_name
ORDER BY d.calendar_year, d.calendar_month;
-- Why: The result is ready for a Power BI date trend visual.
