"""Generate docs/04_data_dictionary.md from the live PostgreSQL catalog.

Types, nullability, defaults, keys and CHECK constraints are READ from the database, so they can never disagree with the schema.
Only the business descriptions are written by hand (DESCRIPTIONS below); the script refuses to run if a column has none.

Usage (project root):   python scripts/build_data_dictionary.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from data_extraction import get_query  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "04_data_dictionary.md"

TABLES = {  # table -> (purpose, one-line row grain)
    "customer_segments": ("Commercial customer groups used for reporting.", "one row per segment"),
    "customers": ("People who have registered with the retailer (synthetic).", "one row per customer record; duplicates exist on purpose"),
    "categories": ("Product category tree (parent/child) including two deliberate case-variant duplicates.", "one row per category"),
    "suppliers": ("Vendors that supply products and receive purchase orders.", "one row per supplier"),
    "products": ("The sellable catalogue.", "one row per SKU"),
    "stores": ("Physical stores plus one online fulfilment hub.", "one row per store"),
    "employees": ("Store staff, with a self-reference to their manager.", "one row per employee"),
    "promotions": ("Discount campaigns.", "one row per promotion"),
    "product_promotions": ("Junction table: which products a promotion covers (many-to-many).", "one row per promotion + product"),
    "sales_orders": ("Order header: who bought, where, when, and the money totals.", "one row per order (completed or cancelled)"),
    "sales_order_items": ("Order lines with a price and cost snapshot at the time of sale.", "one row per order + product"),
    "payments": ("Payment attempts against orders (a failed attempt can precede a successful one).", "one row per payment attempt"),
    "returns": ("Return header: which order came back, when, and why.", "one row per return"),
    "return_items": ("Returned lines with quantity, refund and restock decision.", "one row per return + order line"),
    "inventory": ("Current stock position and stock policy per store and product.", "one row per store + product"),
    "inventory_transactions": ("Ledger of every stock movement; its sum per store+product should equal inventory.quantity_on_hand.", "one row per movement"),
    "purchases": ("Purchase order header sent to a supplier for delivery to a store.", "one row per purchase order"),
    "purchase_items": ("Purchase order lines.", "one row per purchase order + product"),
    "dim_date": ("Calendar table for time analysis and Power BI.", "one row per day"),
}

# (table, column) -> description. created_at / updated_at / is_active are handled by GENERIC below.
DESCRIPTIONS = {
    ("customer_segments", "segment_name"): "Segment label: Regular, Premium, Corporate or Student. Used to compare value and behaviour between groups.",
    ("customer_segments", "description"): "What the segment means in plain words.",
    ("customers", "first_name"): "Given name. Capitalisation is inconsistent in some rows (data-quality scenario).",
    ("customers", "last_name"): "Family name; may carry a trailing space in some rows.",
    ("customers", "email"): "Contact e-mail on reserved example domains. Not unique: duplicate people and invalid formats exist on purpose.",
    ("customers", "phone"): "Contact number in mixed formats; some are invalid or missing.",
    ("customers", "gender"): "M, F or O; NULL when not provided.",
    ("customers", "date_of_birth"): "Birth date; NULL for ~15 % and a few implausible values (1900, future) are planted.",
    ("customers", "city"): "Customer's city; NULL for ~1 %. Used for geographic demand.",
    ("customers", "state"): "Customer's state; NULL when the city is NULL.",
    ("customers", "segment_id"): "Commercial segment; NULL means not assigned.",
    ("customers", "registration_date"): "Date the customer registered. No order may predate it.",
    ("categories", "category_name"): "Category label. Unique case-sensitively, so 'Footwear' and 'FOOTWEAR' co-exist (data-quality scenario).",
    ("categories", "parent_category_id"): "Parent category (Electronics, Fashion ...); NULL for top-level rows.",
    ("suppliers", "supplier_name"): "Trading name of the vendor (fictional).",
    ("suppliers", "contact_email"): "Vendor e-mail; NULL for a few suppliers.",
    ("suppliers", "contact_phone"): "Vendor phone; NULL for a few suppliers.",
    ("suppliers", "city"): "Supplier city.",
    ("suppliers", "state"): "Supplier state.",
    ("suppliers", "gstin"): "15-character GST identification number (synthetic pattern); NULL for a few suppliers.",
    ("suppliers", "lead_time_days"): "Promised days from order to delivery. Compared with actual delivery in supplier analysis.",
    ("products", "sku"): "Stock-keeping unit code; unique.",
    ("products", "product_name"): "Display name. A few near-duplicates differing by case or a trailing space exist on purpose.",
    ("products", "brand"): "Brand (fictional); NULL for ~3 %.",
    ("products", "category_id"): "Category; NULL for 8 products (data-quality scenario).",
    ("products", "supplier_id"): "Main supplier; NULL for 12 products (data-quality scenario).",
    ("products", "unit_cost"): "Current cost per unit, ex-GST, INR.",
    ("products", "unit_price"): "Current selling price (MRP), GST-inclusive, INR.",
    ("products", "gst_rate"): "GST percentage: 0, 5, 12, 18 or 28. Used to turn GST-inclusive prices into net revenue.",
    ("products", "launch_date"): "Date the product went on sale; no sales exist before it.",
    ("stores", "store_code"): "Short unique store code.",
    ("stores", "store_name"): "Store display name.",
    ("stores", "store_type"): "STORE or ONLINE_WAREHOUSE. The warehouse fulfils all online orders.",
    ("stores", "city"): "City of the store.",
    ("stores", "state"): "State of the store.",
    ("stores", "region"): "North, South, East, West or Central: used for regional reporting.",
    ("stores", "opened_date"): "Opening date; no order may predate it.",
    ("employees", "first_name"): "Given name (fictional).",
    ("employees", "last_name"): "Family name (fictional).",
    ("employees", "email"): "Work e-mail on a reserved example domain.",
    ("employees", "store_id"): "Store where the employee works.",
    ("employees", "manager_id"): "The employee's manager (self-reference); NULL for store managers.",
    ("employees", "job_title"): "Role, e.g. Store Manager or Cashier.",
    ("employees", "hire_date"): "Date of joining; employees only appear on orders after this date.",
    ("promotions", "promo_code"): "Unique campaign code such as DIWALI2024.",
    ("promotions", "promo_name"): "Campaign name.",
    ("promotions", "discount_type"): "PERCENT (off the price) or FLAT (rupees per unit).",
    ("promotions", "discount_value"): "Percentage (max 90) or rupees per unit, depending on discount_type.",
    ("promotions", "start_date"): "First day of the campaign.",
    ("promotions", "end_date"): "Last day; never before start_date.",
    ("sales_orders", "order_number"): "Human-readable unique order reference, e.g. ORD-0000123.",
    ("sales_orders", "customer_id"): "The buying customer.",
    ("sales_orders", "store_id"): "Store that served the order (the online hub for online orders).",
    ("sales_orders", "employee_id"): "Salesperson; NULL for online orders.",
    ("sales_orders", "order_date"): "Date and time the order was placed.",
    ("sales_orders", "channel"): "IN_STORE or ONLINE.",
    ("sales_orders", "order_status"): "COMPLETED or CANCELLED. Only COMPLETED orders count as sales.",
    ("sales_orders", "subtotal"): "Sum of quantity x unit_price before discount, GST-inclusive.",
    ("sales_orders", "discount_amount"): "Total discount on the order.",
    ("sales_orders", "gst_amount"): "GST contained inside total_amount. Net revenue = total_amount - gst_amount.",
    ("sales_orders", "total_amount"): "Amount the customer pays: subtotal - discount_amount, GST-inclusive.",
    ("sales_order_items", "order_id"): "Parent order.",
    ("sales_order_items", "product_id"): "Product sold.",
    ("sales_order_items", "promotion_id"): "Promotion that discounted this line; NULL if none.",
    ("sales_order_items", "quantity"): "Units sold; always positive. A few lines are unusually large (bulk buys).",
    ("sales_order_items", "unit_price"): "Price charged per unit at the time of sale (GST-inclusive). Historical prices are lower than today's MRP.",
    ("sales_order_items", "unit_cost"): "Cost per unit at the time of sale (ex-GST). Snapshotted so profit stays correct when costs change.",
    ("sales_order_items", "discount_amount"): "Discount on the whole line.",
    ("sales_order_items", "line_total"): "quantity x unit_price - discount_amount, GST-inclusive.",
    ("payments", "order_id"): "Order being paid.",
    ("payments", "payment_date"): "When the attempt was made.",
    ("payments", "payment_method"): "UPI, CARD, CASH, NET_BANKING or WALLET (cash is in-store only).",
    ("payments", "amount"): "Amount of the attempt, INR.",
    ("payments", "payment_status"): "SUCCESS, FAILED or REFUNDED (payment for a cancelled order).",
    ("payments", "transaction_ref"): "Gateway reference; NULL for cash.",
    ("returns", "order_id"): "The order the return belongs to (completed orders only).",
    ("returns", "return_date"): "When the return was processed; after the order date.",
    ("returns", "return_reason"): "Reason recorded by staff (DEFECTIVE, SIZE_ISSUE ...). A recorded label, not a proven root cause.",
    ("returns", "refund_amount"): "Total refund for the return, GST-inclusive.",
    ("returns", "processed_by"): "Employee who processed the return.",
    ("return_items", "return_id"): "Parent return.",
    ("return_items", "order_item_id"): "The sold line being returned.",
    ("return_items", "quantity"): "Units returned; never more than were sold.",
    ("return_items", "refund_amount"): "Refund for this line, GST-inclusive.",
    ("return_items", "restocked"): "TRUE if the item went back on the shelf; FALSE means written off (typically defective or damaged).",
    ("inventory", "store_id"): "Store holding the stock.",
    ("inventory", "product_id"): "Product held.",
    ("inventory", "quantity_on_hand"): "Units physically in stock now. About 1.2 % of rows deliberately differ from the ledger.",
    ("inventory", "reserved_quantity"): "Units promised to pending orders; never above quantity_on_hand.",
    ("inventory", "reorder_level"): "Stock level at or below which a re-order is triggered. Set by the data generator from lead-time demand, not by a separate safety-stock model.",
    ("inventory", "max_stock_level"): "Order-up-to level: a replenishment order tops stock up to this quantity.",
    ("inventory", "last_restocked_date"): "Date of the last receipt (or opening stock); proxy for stock age.",
    ("inventory_transactions", "store_id"): "Store where the movement happened.",
    ("inventory_transactions", "product_id"): "Product moved.",
    ("inventory_transactions", "transaction_type"): "OPENING, PURCHASE, SALE, RETURN or ADJUSTMENT.",
    ("inventory_transactions", "quantity_change"): "Signed units: positive adds stock, negative removes it; never zero.",
    ("inventory_transactions", "transaction_date"): "When the movement happened.",
    ("inventory_transactions", "reference_type"): "What caused the movement: SALES_ORDER, PURCHASE or RETURN; NULL for opening stock and adjustments.",
    ("inventory_transactions", "reference_id"): "ID of the referenced record. Polymorphic, so it has no foreign key by design.",
    ("purchases", "po_number"): "Unique purchase-order reference.",
    ("purchases", "supplier_id"): "Supplier the order was placed with.",
    ("purchases", "store_id"): "Store receiving the goods.",
    ("purchases", "order_date"): "Date the PO was placed (buyers order on Mondays).",
    ("purchases", "expected_date"): "Order date + the supplier's promised lead time.",
    ("purchases", "received_date"): "Actual delivery date; NULL while status is ORDERED.",
    ("purchases", "status"): "ORDERED (open) or RECEIVED.",
    ("purchases", "total_amount"): "Sum of ordered quantity x unit cost.",
    ("purchase_items", "purchase_id"): "Parent purchase order.",
    ("purchase_items", "product_id"): "Product ordered.",
    ("purchase_items", "quantity_ordered"): "Units ordered.",
    ("purchase_items", "quantity_received"): "Units actually delivered (about 5 % of lines arrive short); 0 while the PO is open.",
    ("purchase_items", "unit_cost"): "Agreed cost per unit, ex-GST.",
    ("dim_date", "date_key"): "The calendar day (primary key).",
    ("dim_date", "year"): "Calendar year.",
    ("dim_date", "quarter"): "Quarter 1-4.",
    ("dim_date", "month"): "Month number 1-12.",
    ("dim_date", "month_name"): "Month name; sort by the month column in reports.",
    ("dim_date", "year_month"): "YYYY-MM label.",
    ("dim_date", "week_of_year"): "ISO-style week number.",
    ("dim_date", "day_of_month"): "Day 1-31.",
    ("dim_date", "day_of_week"): "1 = Monday ... 7 = Sunday.",
    ("dim_date", "day_name"): "Weekday name.",
    ("dim_date", "is_weekend"): "TRUE for Saturday and Sunday.",
}
GENERIC = {
    "created_at": "When the row was created.",
    "updated_at": "When the row was last changed; maintained automatically by a trigger.",
    "is_active": "TRUE while the record is in use; FALSE for discontinued or deactivated records.",
}
PRIMARY_KEY_TEXT = "Surrogate primary key (system-generated identity)."

VIEWS = [
    ("vw_asof", "one row", "First and last order dates; the 'as of' date used everywhere."),
    ("vw_category_canonical", "category", "Maps each category to a canonical id/name so case-variant duplicates merge."),
    ("vw_sales_lines", "sold order line", "Completed order lines with net revenue, cost of goods and gross profit. Feeds most other views."),
    ("vw_orders", "order", "All orders with net amount, return flag and customer segment."),
    ("vw_monthly_sales", "month", "Orders, units, net revenue, profit, margin, AOV, discounts and refunds per month."),
    ("vw_product_performance", "product", "Sales, margin, return rate, stock, cover, turnover, ABC class and revenue/stock class per product."),
    ("vw_customer_summary (materialized)", "customer", "Orders, revenue, RFM scores, RFM segment and activity status per customer."),
    ("vw_inventory_health", "store + product", "Stock, demand, cover, inbound, suggested order and the five-way health status."),
    ("vw_store_performance", "store", "Revenue, orders, AOV, repeat rate, return rate, stock value, growth and peer index per store."),
    ("vw_category_performance", "category + year", "Revenue, margin, returns and year-over-year growth per category and year."),
    ("vw_supplier_performance", "supplier", "Spend, on-time %, fill rate, lead-time gap and open/overdue POs per supplier."),
    ("vw_return_analysis", "returned line", "Reason, store, channel, segment, category, refund (net of GST) and restock flag per returned line."),
]

SQL = """
SELECT c.relname AS table_name, a.attnum, a.attname AS column_name, format_type(a.atttypid, a.atttypmod) AS data_type,
       NOT a.attnotnull AS nullable, pg_get_expr(d.adbin, d.adrelid) AS column_default, a.attidentity AS identity
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY c.relname, a.attnum
"""
CONSTRAINTS = """
SELECT c.relname AS table_name, con.contype, con.conname, pg_get_constraintdef(con.oid) AS definition,
       (SELECT array_agg(a.attname ORDER BY k.ord) FROM unnest(con.conkey) WITH ORDINALITY k(attnum, ord)
        JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum) AS columns,
       rc.relname AS ref_table,
       (SELECT array_agg(a.attname ORDER BY k.ord) FROM unnest(con.confkey) WITH ORDINALITY k(attnum, ord)
        JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.attnum) AS ref_columns
FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_class rc ON rc.oid = con.confrelid
WHERE n.nspname = 'public' AND con.contype IN ('p', 'f', 'u', 'c') ORDER BY c.relname, con.contype, con.conname
"""


def describe(table: str, column: str, is_pk: bool, fk: tuple | None) -> str | None:
    if (table, column) in DESCRIPTIONS:
        text = DESCRIPTIONS[(table, column)]
    elif is_pk:
        text = PRIMARY_KEY_TEXT
    elif column in GENERIC:
        text = GENERIC[column]
    elif fk:
        text = f"Reference to {fk[0]}."
    else:
        return None
    return text


def build() -> tuple[str, list[str]]:
    cols, cons = get_query(SQL), get_query(CONSTRAINTS)
    missing, lines = [], ["# 04. Data dictionary", "",
                          "Generated by `python scripts/build_data_dictionary.py` from the live PostgreSQL catalog: data types, nullability, defaults, "
                          "keys and CHECK constraints are read from the database. Descriptions are written by hand and a test fails if one is missing.", "",
                          "Legend: **PK** primary key, **FK** foreign key, **UQ** unique. `NULL?` says whether the column may be empty.", "",
                          "## Tables", "", "| Table | Purpose | Grain |", "|---|---|---|"]
    lines += [f"| [{t}](#{t}) | {p} | {g} |" for t, (p, g) in TABLES.items()]
    for table, (purpose, grain) in TABLES.items():
        tc = cons[cons["table_name"] == table]
        pk_cols = set(sum([list(r) for r in tc[tc["contype"] == "p"]["columns"]], []))
        fks = {r.columns[0]: (r.ref_table, r.ref_columns[0]) for r in tc[tc["contype"] == "f"].itertuples()}
        uqs = {}
        for r in tc[tc["contype"] == "u"].itertuples():
            for col in r.columns:
                uqs.setdefault(col, []).append("(" + ", ".join(r.columns) + ")" if len(r.columns) > 1 else "")
        lines += ["", f"## {table}", "", f"{purpose} **Grain:** {grain}.", "",
                  "| Column | Data type | NULL? | Key | Default | Description and business meaning |", "|---|---|---|---|---|---|"]
        for r in cols[cols["table_name"] == table].itertuples():
            key = []
            if r.column_name in pk_cols:
                key.append("PK")
            if r.column_name in fks:
                key.append(f"FK -> {fks[r.column_name][0]}.{fks[r.column_name][1]}")
            for grp in uqs.get(r.column_name, []):
                key.append("UQ" + (f" {grp}" if grp else ""))
            raw_default = r.column_default if isinstance(r.column_default, str) else ""
            default = "identity" if r.identity else raw_default.replace("|", "/")
            text = describe(table, r.column_name, r.column_name in pk_cols and len(pk_cols) == 1, fks.get(r.column_name))
            if text is None:
                missing.append(f"{table}.{r.column_name}")
                text = "**MISSING DESCRIPTION**"
            lines.append(f"| {r.column_name} | {r.data_type} | {'yes' if r.nullable else 'no'} | {'; '.join(key)} | {default} | {text} |")
        checks = tc[tc["contype"] == "c"]
        if len(checks):
            lines += ["", "CHECK constraints: " + "; ".join(f"`{d.replace('CHECK ', '', 1)}`" for d in checks["definition"])]
    lines += ["", "## Analytical views", "", "Defined in `database/views.sql`; Python and Power BI read these. Revenue is net of GST, "
              "profit is net revenue minus cost at sale time, sales are completed orders only.", "",
              "| View | Grain | Contents |", "|---|---|---|"] + [f"| {v} | {g} | {d} |" for v, g, d in VIEWS]
    return "\n".join(lines) + "\n", missing


if __name__ == "__main__":
    text, missing = build()
    if missing:
        sys.exit(f"Missing descriptions ({len(missing)}): {missing}")
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT} ({len(text.splitlines())} lines)")
