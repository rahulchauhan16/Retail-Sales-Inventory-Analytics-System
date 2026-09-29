-- =============================================================================
-- A least-privilege login for Power BI: it can READ the analytical views and nothing else.
-- Power BI never needs to write, and it should not be able to see or change the raw tables.
--
-- Run once (Windows PowerShell; choose your own password, do not commit it):
--   Get-Content database/powerbi_readonly.sql | docker exec -i retail_pg psql -U retail_user -d retail_analytics -v pw="YourPasswordHere"
--
-- Views run with their OWNER's rights, so this role does not need access to the base tables.
-- Re-run this file after `python scripts/load_data.py`, because rebuilding the views drops their grants.
-- =============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'powerbi_reader') THEN
        CREATE ROLE powerbi_reader LOGIN;
    END IF;
END $$;

ALTER ROLE powerbi_reader PASSWORD :'pw';

GRANT CONNECT ON DATABASE retail_analytics TO powerbi_reader;
GRANT USAGE ON SCHEMA public TO powerbi_reader;

GRANT SELECT ON vw_asof, vw_category_canonical, vw_sales_lines, vw_orders, vw_monthly_sales, vw_product_performance,
                vw_customer_summary, vw_inventory_health, vw_store_performance, vw_category_performance,
                vw_supplier_performance, vw_return_analysis
    TO powerbi_reader;

-- Two small dimension tables that have no view of their own
GRANT SELECT ON dim_date, stores TO powerbi_reader;
