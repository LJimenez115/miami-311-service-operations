-- Why: This query establishes the size of the completed database and the share of
-- requests with a closure timestamp before interpreting operational performance.
SELECT
    COUNT(*) AS total_requests,
    COUNT(*) FILTER (WHERE is_closed) AS closed_requests,
    ROUND((100.0 * COUNT(*) FILTER (WHERE is_closed) / COUNT(*))::NUMERIC, 2) AS closure_rate_percent
FROM fact_service_request;
-- Why: The result is the primary data-volume quality check for the loaded database.

-- Why: This query identifies the service categories creating the largest workload.
SELECT
    i.issue_description,
    COUNT(*) AS request_count,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY f.resolution_days_calculated)::NUMERIC, 2) AS median_resolution_days
FROM fact_service_request AS f
JOIN dim_issue_type AS i ON f.issue_type_key = i.issue_type_key
GROUP BY i.issue_description
ORDER BY request_count DESC
LIMIT 10;
-- Why: PostgreSQL's ordered-set percentile function calculates a true median without
-- forcing the dashboard layer to approximate the result.

-- Why: This query compares workload, turnaround, and source overdue flags by team.
SELECT
    o.case_owner_name AS case_owner,
    COUNT(*) AS request_count,
    ROUND(AVG(f.resolution_days_calculated)::NUMERIC, 2) AS average_resolution_days,
    ROUND((100.0 * AVG(f.is_overdue_source::INTEGER))::NUMERIC, 2) AS source_overdue_rate_percent
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
