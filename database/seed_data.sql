-- =============================================================================
-- Post-load seed step. Run automatically by scripts/load_data.py after the CSV load.
--   1. Populates the dim_date calendar table
--   2. Re-syncs identity sequences (rows were loaded with explicit IDs, so the
--      sequences would otherwise restart at 1 and collide on the next INSERT)
-- The bulk data itself is loaded from data/generated/*.csv with COPY, because
-- 300k+ INSERT statements would be slow and unreadable in a .sql file.
-- =============================================================================

-- ---- calendar: one row per day, covering the data window (+ upcoming promo dates) ----
INSERT INTO dim_date
SELECT d::date                                        AS date_key,
       EXTRACT(year    FROM d)::smallint              AS year,
       EXTRACT(quarter FROM d)::smallint              AS quarter,
       EXTRACT(month   FROM d)::smallint              AS month,
       TRIM(TO_CHAR(d, 'Month'))                      AS month_name,
       TO_CHAR(d, 'YYYY-MM')                          AS year_month,
       EXTRACT(week FROM d)::smallint                 AS week_of_year,
       EXTRACT(day  FROM d)::smallint                 AS day_of_month,
       EXTRACT(isodow FROM d)::smallint               AS day_of_week,      -- 1 = Monday
       TRIM(TO_CHAR(d, 'Day'))                        AS day_name,
       EXTRACT(isodow FROM d) IN (6, 7)               AS is_weekend
FROM generate_series('2021-01-01'::date, '2026-12-31'::date, interval '1 day') AS d
ON CONFLICT (date_key) DO NOTHING;

-- ---- sequence sync ----
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT c.table_name, c.column_name
        FROM information_schema.columns c
        WHERE c.table_schema = 'public' AND c.is_identity = 'YES'
    LOOP
        EXECUTE format(
            'SELECT setval(pg_get_serial_sequence(%L, %L), COALESCE(MAX(%I), 0) + 1, false) FROM %I',
            r.table_name, r.column_name, r.column_name, r.table_name);
    END LOOP;
END $$;
