# Entity Relationship Diagram

Renders automatically on GitHub (Mermaid). Crow's-foot notation: `||--o{` means "one to zero-or-many".

```mermaid
erDiagram
    customer_segments ||--o{ customers : "classifies"
    categories        ||--o{ categories : "parent of"
    categories        ||--o{ products : "contains"
    suppliers         ||--o{ products : "supplies"
    suppliers         ||--o{ purchases : "receives PO"
    stores            ||--o{ employees : "employs"
    employees         ||--o{ employees : "manages"
    stores            ||--o{ sales_orders : "sells"
    customers         ||--o{ sales_orders : "places"
    employees         ||--o{ sales_orders : "handles"
    sales_orders      ||--|{ sales_order_items : "contains"
    products          ||--o{ sales_order_items : "sold as"
    promotions        ||--o{ sales_order_items : "applied to"
    promotions        ||--o{ product_promotions : "covers"
    products          ||--o{ product_promotions : "eligible for"
    sales_orders      ||--o{ payments : "paid by"
    sales_orders      ||--o{ returns : "may have"
    returns           ||--|{ return_items : "contains"
    sales_order_items ||--o{ return_items : "returned as"
    stores            ||--o{ inventory : "holds"
    products          ||--o{ inventory : "stocked as"
    stores            ||--o{ inventory_transactions : "moves stock"
    products          ||--o{ inventory_transactions : "moves"
    stores            ||--o{ purchases : "receives"
    purchases         ||--|{ purchase_items : "contains"
    products          ||--o{ purchase_items : "bought as"
```

## Relationship types

| Type | Relationship | Implemented by |
|---|---|---|
| One-to-many | segment → customers, category → products, supplier → products, store → employees, customer → orders, store → orders, order → items, order → payments, order → returns, return → return items, purchase → purchase items | FK on the "many" side |
| Many-to-many | products ↔ promotions | junction table `product_promotions` (composite PK) |
| Many-to-many | products ↔ stores (stock) | `inventory` (UNIQUE store_id + product_id) |
| Many-to-many | orders ↔ products | `sales_order_items` (UNIQUE order_id + product_id) |
| Many-to-many | purchases ↔ products | `purchase_items` |
| Self-reference | category hierarchy, employee → manager | FK to same table |
| One-to-one | *none enforced.* `inventory` is 1:1 with a (store, product) pair, enforced by a UNIQUE constraint | — |
| Polymorphic (no FK) | `inventory_transactions.reference_id` points to a purchase, sales order or return depending on `reference_type` | documented, checked in data-quality queries |

`dim_date` is a standalone calendar table, joined on date for Power BI time intelligence.
