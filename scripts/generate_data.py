"""Generate the synthetic retail dataset as CSV files in data/generated/.

Run from the project root:
    python scripts/generate_data.py            # default seed 42, fully reproducible

How it works (simulation, not independent random rows):
 1. Master data (segments, categories, suppliers, stores, employees, customers, products, promotions).
 2. Demand: orders are generated month by month with seasonality, growth, category trends,
    customer churn and store openings. Each order gets 1-8 line items.
 3. Inventory simulation: items are replayed in time order against a per-store, per-product
    stock level. Stock falls with sales; when it reaches the reorder level a purchase order is
    raised and arrives after the supplier's lead time (sometimes late, sometimes partial).
    A sale that cannot be filled from stock is dropped (a lost sale), so stock-outs are real.
 4. Returns, payments and the inventory ledger are derived from the kept sales.
 5. Known data-quality problems are planted (see the DQ section of docs) so that the
    checks in queries/ have something real to find.

Everything is synthetic. Brands, suppliers and people are invented; e-mail addresses use
reserved example domains.
"""
import argparse
import heapq
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_config import (CATEGORIES, CATEGORY_SEASONALITY, CATEGORY_VARIANTS, EMAIL_DOMAINS, FIRST_F,  # noqa: E402
                         FIRST_M, GSTIN_STATE_CODES, JOB_TITLES_HUB, JOB_TITLES_STORE, LAST, OTHER_CITIES,
                         SEGMENTS, STORES, SUPPLIER_DOMAIN, SUPPLIER_PREFIX, SUPPLIER_SUFFIX)

START, END = date(2023, 1, 1), date(2025, 12, 31)
START_ORD, END_ORD = START.toordinal(), END.toordinal()
N_MONTHS = 36
END_SEC = (END_ORD - START_ORD) * 86400 + 86399
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "generated"

N_BASE_CUSTOMERS = 9000
N_DUPLICATE_CUSTOMERS = 120
N_SUPPLIERS = 55
TARGET_ORDERS = 58000
CANCEL_RATE = 0.04
PRICE_INFLATION = 1.04     # yearly; prices at sale time are deflated from today's MRP

TXN_OPENING, TXN_PURCHASE, TXN_SALE, TXN_RETURN, TXN_ADJ = range(5)
TXN_NAMES = ["OPENING", "PURCHASE", "SALE", "RETURN", "ADJUSTMENT"]


# ------------------------------------------------------------------------------ helpers
def month_bounds(m):
    """First and last day (as ordinals) of month index m (0 = Jan 2023)."""
    y, mo = 2023 + m // 12, m % 12 + 1
    first = date(y, mo, 1)
    nxt = date(y + (mo == 12), mo % 12 + 1, 1)
    return first.toordinal(), nxt.toordinal() - 1


def month_number(m):
    return m % 12 + 1


def sec_to_str(sec):
    ts = pd.Timestamp(START) + pd.to_timedelta(np.asarray(sec, dtype="int64"), unit="s")
    return pd.Series(ts).dt.strftime("%Y-%m-%d %H:%M:%S")


def ord_to_str(o):
    return pd.Series(pd.to_datetime(np.asarray(o, dtype="int64") - 719163, unit="D")).dt.strftime("%Y-%m-%d")


def write_csv(df, name):
    df.to_csv(OUT_DIR / f"{name}.csv", index=False, na_rep="")
    print(f"  {name:<24}{len(df):>9,} rows")


def phone_number(rng):
    return str(rng.integers(6, 10)) + "".join(str(d) for d in rng.integers(0, 10, 9))


# ------------------------------------------------------------------------------ master data
def build_segments():
    return pd.DataFrame({
        "segment_id": range(1, len(SEGMENTS) + 1),
        "segment_name": [s[0] for s in SEGMENTS],
        "description": [s[1] for s in SEGMENTS],
    })


def build_categories():
    parents = list(dict.fromkeys(c["parent"] for c in CATEGORIES))
    parent_id = {p: 19 + i for i, p in enumerate(parents)}
    rows = [(pid, p, None) for p, pid in parent_id.items()]                        # parents first (FK order)
    rows += [(i + 1, c["name"], parent_id[c["parent"]]) for i, c in enumerate(CATEGORIES)]
    rows += [(17 + i, v[0], None) for i, v in enumerate(CATEGORY_VARIANTS)]        # planted case variants
    df = pd.DataFrame(rows, columns=["category_id", "category_name", "parent_category_id"])
    df["parent_category_id"] = df["parent_category_id"].astype("Int64")
    df["is_active"] = True
    df["created_at"] = "2022-01-01 09:00:00"
    return df


def build_suppliers(rng):
    rows, cats_of, lead, late_p = [], [], [], []
    used = set()
    for i in range(N_SUPPLIERS):
        c1, c2 = i % 16, (i * 3 + 5) % 16
        code = CATEGORIES[c1]["code"]
        name = f"{SUPPLIER_PREFIX[i % 25]} {SUPPLIER_DOMAIN[code]} {SUPPLIER_SUFFIX[(i // 3) % 7]}"
        while name in used:
            name = f"{SUPPLIER_PREFIX[int(rng.integers(0, 25))]} {SUPPLIER_DOMAIN[code]} {SUPPLIER_SUFFIX[int(rng.integers(0, 7))]}"
        used.add(name)
        if code in ("MOB", "LAP", "TVA", "HAP", "KIT", "FUR"):
            lt = int(rng.integers(10, 26))
        elif code in ("GRO", "BEV", "PER"):
            lt = int(rng.integers(3, 9))
        else:
            lt = int(rng.integers(6, 15))
        city = ["Mumbai", "Delhi", "Bengaluru", "Chennai", "Ahmedabad", "Surat", "Kolkata", "Pune", "Ludhiana", "Jaipur"][i % 10]
        sc = GSTIN_STATE_CODES[i % len(GSTIN_STATE_CODES)]
        letters = "".join(rng.choice(list("ABCDEFGHJKLMNPQRSTUVWXYZ"), 5))
        gstin = f"{sc}{letters}{int(rng.integers(1000, 9999))}{rng.choice(list('ABCDEFGH'))}1Z{rng.choice(list('ABCDEFGH123456'))}"
        rows.append(dict(
            supplier_id=i + 1, supplier_name=name,
            contact_email=f"sales{i + 1}@{name.split()[0].lower()}-supply.example",
            contact_phone="+91" + phone_number(rng), city=city,
            state={"Mumbai": "Maharashtra", "Delhi": "Delhi", "Bengaluru": "Karnataka", "Chennai": "Tamil Nadu",
                   "Ahmedabad": "Gujarat", "Surat": "Gujarat", "Kolkata": "West Bengal", "Pune": "Maharashtra",
                   "Ludhiana": "Punjab", "Jaipur": "Rajasthan"}[city],
            gstin=gstin, lead_time_days=lt, is_active=True,
            created_at="2022-01-01 09:00:00", updated_at="2022-01-01 09:00:00"))
        cats_of.append({c1, c2})
        lead.append(lt)
        late_p.append(float(rng.uniform(0.03, 0.35)))
    df = pd.DataFrame(rows)
    # data-quality scenarios: missing supplier information
    for col, n in (("contact_email", 3), ("contact_phone", 4), ("gstin", 3), ("city", 2)):
        df.loc[rng.choice(N_SUPPLIERS, n, replace=False), col] = None
    df.loc[rng.choice(N_SUPPLIERS, 2, replace=False), "is_active"] = False
    return df, cats_of, np.array(lead), np.array(late_p)


def build_stores():
    rows = [dict(store_id=i + 1, store_code=s[0], store_name=s[1], store_type=s[7], city=s[2], state=s[3],
                 region=s[4], opened_date=s[5], is_active=True, created_at=s[5] + " 09:00:00")
            for i, s in enumerate(STORES)]
    df = pd.DataFrame(rows)
    weights = np.array([s[6] for s in STORES])
    opened = np.array([date.fromisoformat(s[5]).toordinal() for s in STORES])
    return df, weights, opened


def build_employees(rng, stores_df, opened_ord):
    rows, by_store = [], {}
    eid = 0
    extra = {0: 1, 1: 1, 2: 1}                 # three biggest stores get one more employee
    for s in range(len(stores_df)):
        hub = stores_df.loc[s, "store_type"] == "ONLINE_WAREHOUSE"
        n = 4 if hub else 5 + extra.get(s, 0)
        titles = JOB_TITLES_HUB if hub else JOB_TITLES_STORE
        manager_id = None
        by_store[s] = ([], [])
        for k in range(n):
            eid += 1
            first, last = rng.choice(FIRST_M + FIRST_F), rng.choice(LAST)
            new_store = opened_ord[s] > START_ORD - 200
            if k == 0:
                title, hire = ("Hub Manager" if hub else "Store Manager"), opened_ord[s] - 60
                manager_id = eid
                mgr = None
            else:
                title, mgr = titles[(k - 1) % len(titles)], manager_id
                if new_store:
                    hire = opened_ord[s] - 30 if rng.random() < 0.8 else opened_ord[s] + int(rng.integers(0, 400))
                elif rng.random() < 0.8:
                    hire = int(rng.integers(opened_ord[s], START_ORD))
                else:
                    hire = int(rng.integers(START_ORD, date(2025, 6, 30).toordinal()))
            hire = min(hire, END_ORD)
            rows.append(dict(employee_id=eid, first_name=first, last_name=last,
                             email=f"{first}.{last}{eid}@retailco.example".lower(), store_id=s + 1,
                             manager_id=mgr, job_title=title, hire_date=hire, is_active=True))
            by_store[s][0].append(eid)
            by_store[s][1].append(hire)
    df = pd.DataFrame(rows)
    df["manager_id"] = df["manager_id"].astype("Int64")
    df.loc[rng.choice(len(df), 3, replace=False), "is_active"] = False
    out = df.copy()
    out["hire_date"] = ord_to_str(df["hire_date"])
    out["created_at"] = out["hire_date"] + " 09:00:00"
    out["updated_at"] = out["created_at"]
    by_store = {s: (np.array(v[0]), np.array(v[1])) for s, v in by_store.items()}
    return out, by_store


def _messy_email(rng, first, last, uid):
    r = rng.random()
    base = f"{first}.{last}{uid % 997}".lower()
    dom = EMAIL_DOMAINS[int(rng.integers(0, 3))]
    if r < 0.02:      # invalid formats
        return rng.choice([f"{base}.{dom}", f"{base}@", f"{base}@{dom.split('.')[0]}", f"{base}@@{dom}",
                           f"{base} @{dom}", f"{base}..x@{dom}"])
    if r < 0.05:
        return None
    return f"{base}@{dom}"


def _messy_phone(rng):
    r = rng.random()
    p = phone_number(rng)
    if r < 0.02:      # invalid
        return rng.choice([p[:9], p + "1", "98765abcde", "0000000000"])
    if r < 0.06:
        return None
    if r < 0.20:      # inconsistent but valid formatting
        return rng.choice([f"+91{p}", f"+91-{p}", f"{p[:5]} {p[5:]}"])
    return p


def build_customers(rng, stores_df, store_w, n_stores_physical):
    n = N_BASE_CUSTOMERS
    seg_share = np.array([s[2] for s in SEGMENTS])
    seg_idx = rng.choice(len(SEGMENTS), n, p=seg_share)
    gender = rng.choice(["M", "F", "O"], n, p=[0.485, 0.505, 0.01]).astype(object)
    gender[rng.random(n) < 0.05] = None
    first = np.array([rng.choice(FIRST_M) if g == "M" else rng.choice(FIRST_F) if g == "F"
                      else rng.choice(FIRST_M + FIRST_F) for g in gender])
    last = rng.choice(LAST, n)

    # city / home store
    other = list(OTHER_CITIES)
    city, state, home = [], [], []
    sw = store_w[:n_stores_physical] / store_w[:n_stores_physical].sum()
    for _ in range(n):
        if rng.random() < 0.90:
            s = int(rng.choice(n_stores_physical, p=sw))
            city.append(stores_df.loc[s, "city"]); state.append(stores_df.loc[s, "state"]); home.append(s)
        else:
            c = str(rng.choice(other))
            city.append(c); state.append(OTHER_CITIES[c][0]); home.append(OTHER_CITIES[c][1])
    city, state = np.array(city, dtype=object), np.array(state, dtype=object)
    miss = rng.random(n) < 0.01
    city[miss] = None; state[miss] = None

    # registration: 25% existing customers, the rest spread over the window with mild growth
    old = rng.random(n) < 0.25
    reg = np.where(old, rng.integers(date(2021, 6, 1).toordinal(), START_ORD, n),
                   START_ORD + (1095 * rng.beta(1.15, 1.0, n)).astype(int))

    # purchasing propensity (heavy-tailed) and churn
    weight = (0.25 + np.minimum(rng.gamma(0.6, 1.0, n), 4.0)) * np.array([s[3] for s in SEGMENTS])[seg_idx]
    weight[rng.random(n) < 0.08] = 0.0                    # registered but never buy
    churn = np.where(rng.random(n) < 0.35, reg + rng.integers(120, 700, n), 10 ** 9)

    dob = (date(2025, 1, 1).toordinal() - (rng.integers(18, 71, n) * 365.25 + rng.integers(0, 365, n))).astype(int)
    dob_str = ord_to_str(dob).astype(object)
    dob_str[rng.random(n) < 0.15] = None
    bad = rng.choice(n, 7, replace=False)
    dob_str[bad[:4]] = "1900-01-01"                        # implausible birth dates
    dob_str[bad[4:]] = "2031-05-05"                        # future birth dates

    df = pd.DataFrame(dict(
        customer_id=np.arange(1, n + 1), first_name=first, last_name=last,
        email=[_messy_email(rng, f, l, i) for i, (f, l) in enumerate(zip(first, last))],
        phone=[_messy_phone(rng) for _ in range(n)], gender=gender, date_of_birth=dob_str,
        city=city, state=state, segment_id=seg_idx + 1, registration_date=reg, is_active=True))
    df["segment_id"] = df["segment_id"].astype("Int64")
    df.loc[rng.random(n) < 0.01, "segment_id"] = pd.NA

    # inconsistent name capitalisation / whitespace
    r = rng.random(n)
    df.loc[r < 0.02, "first_name"] = df.loc[r < 0.02, "first_name"].str.upper()
    df.loc[(r >= 0.02) & (r < 0.035), "first_name"] = df.loc[(r >= 0.02) & (r < 0.035), "first_name"].str.lower()
    df.loc[(r >= 0.035) & (r < 0.045), "last_name"] = df.loc[(r >= 0.035) & (r < 0.045), "last_name"] + " "

    # duplicate-like customers: same person registered twice with small variations
    src = rng.choice(np.where(weight > 0)[0], N_DUPLICATE_CUSTOMERS, replace=False)
    dup = df.iloc[src].copy()
    dup["customer_id"] = np.arange(n + 1, n + 1 + len(dup))
    dup["registration_date"] = np.minimum(dup["registration_date"] + rng.integers(30, 400, len(dup)), END_ORD - 5)
    flip = rng.random(len(dup))
    dup.loc[flip < 0.4, "first_name"] = dup.loc[flip < 0.4, "first_name"].str.lower()
    dup.loc[(flip >= 0.4) & (flip < 0.7), "first_name"] = dup.loc[(flip >= 0.4) & (flip < 0.7), "first_name"].str[:-1]
    dup.loc[flip >= 0.7, "email"] = dup.loc[flip >= 0.7, "email"].str.upper()
    df = pd.concat([df, dup], ignore_index=True)
    weight = np.concatenate([weight, weight[src] * 0.4])
    churn = np.concatenate([churn, churn[src]])
    seg_idx = np.concatenate([seg_idx, seg_idx[src]])
    home = np.concatenate([home, np.array(home)[src]]).astype(int)

    # a fraction of long-churned customers are flagged inactive
    inactive = (churn < END_ORD - 180) & (rng.random(len(df)) < 0.8)
    df["is_active"] = ~inactive

    internal = dict(seg_idx=seg_idx.astype(int), home=home, weight=weight, reg=df["registration_date"].to_numpy(),
                    churn=churn)
    out = df.copy()
    out["registration_date"] = ord_to_str(df["registration_date"])
    out["created_at"] = out["registration_date"] + " 10:00:00"
    out["updated_at"] = out["created_at"]
    return out, internal


def build_products(rng, cats_of, sup_lead):
    rows, n_sku = [], 0
    for ci, c in enumerate(CATEGORIES):
        combos = [(t, b, v) for t in c["types"] for b in c["brands"] for v in c["variants"]]
        n_pick = int(rng.integers(38, 42))
        for k in rng.choice(len(combos), n_pick, replace=False):
            (tname, lo, hi), brand, var = combos[k]
            price = float(rng.uniform(lo, hi))
            price = int(round(price / 10) * 10 - 1) if price >= 100 else int(price)
            price = max(price, 1)
            ex_gst = price / (1 + c["gst"] / 100)
            cost = round(ex_gst / (1 + float(rng.uniform(*c["markup"]))), 2)
            n_sku += 1
            sups = [i for i, s in enumerate(cats_of) if ci in s]
            rows.append(dict(sku=f"{c['code']}-{n_sku:05d}", product_name=f"{brand} {tname} {var}", brand=brand,
                             cat_idx=ci, sup_idx=int(rng.choice(sups)), unit_cost=cost, unit_price=price,
                             gst_rate=c["gst"], price_ref=price))
    df = pd.DataFrame(rows)
    P = len(df)

    # lifecycle: 12% launched during the window, 30 discontinued, a few dead-weight products
    df["launch_m"] = 0
    new = rng.random(P) < 0.12
    df.loc[new, "launch_m"] = rng.integers(1, 33, new.sum())
    df["end_m"] = N_MONTHS - 1
    df["is_active"] = True
    disc = rng.choice(np.where(~new)[0], 30, replace=False)
    df.loc[disc, "is_active"] = False
    df.loc[disc, "end_m"] = rng.integers(12, 31, 30)

    price_factor = np.clip((3000 / df["unit_price"].to_numpy()) ** 0.4, 0.4, 3.0)
    dem = np.array([c["demand"] for c in CATEGORIES])[df["cat_idx"].to_numpy()]
    w = rng.lognormal(0.0, 0.8, P) * dem * price_factor
    w[rng.random(P) < 0.05] *= 0.03                                       # slow movers
    active_old = np.where(df["is_active"] & (df["launch_m"] == 0))[0]
    w[rng.choice(active_old, 12, replace=False)] = 0.0                    # listed but never sold
    df["w"] = w

    # near-duplicate product rows (data-quality scenario)
    src = rng.choice(np.where(w > 0)[0], 6, replace=False)
    dup = df.iloc[src].copy()
    dup["sku"] = [s + "-D" for s in dup["sku"]]
    dup["product_name"] = [n.lower() if i % 2 == 0 else n + " " for i, n in enumerate(dup["product_name"])]
    dup["w"] = dup["w"] * 0.3
    df = pd.concat([df, dup], ignore_index=True)
    P = len(df)
    df["product_id"] = np.arange(1, P + 1)

    # products launched in the window start on the first day of their launch month
    launch_date = [month_bounds(int(m))[0] if m > 0
                   else (date(2019, 1, 1) + timedelta(days=int(rng.integers(0, 1400)))).toordinal()
                   for m in df["launch_m"]]

    out = pd.DataFrame(dict(
        product_id=df["product_id"], sku=df["sku"], product_name=df["product_name"], brand=df["brand"],
        category_id=df["cat_idx"] + 1, supplier_id=df["sup_idx"] + 1, unit_cost=df["unit_cost"],
        unit_price=df["unit_price"], gst_rate=df["gst_rate"], launch_date=ord_to_str(launch_date),
        is_active=df["is_active"]))
    out["category_id"] = out["category_id"].astype("Int64")
    out["supplier_id"] = out["supplier_id"].astype("Int64")
    # data-quality scenarios: missing brand / supplier / category, case-variant categories
    out.loc[rng.random(P) < 0.03, "brand"] = None
    out.loc[rng.choice(P, 12, replace=False), "supplier_id"] = pd.NA
    out.loc[rng.choice(P, 8, replace=False), "category_id"] = pd.NA
    home_app = np.where(df["cat_idx"] == 3)[0]
    footwear = np.where(df["cat_idx"] == 8)[0]
    out.loc[rng.choice(home_app, 5, replace=False), "category_id"] = 17
    out.loc[rng.choice(footwear, 4, replace=False), "category_id"] = 18
    out["created_at"] = out["launch_date"] + " 09:00:00"
    out["updated_at"] = out["created_at"]
    return out, df


def build_promotions(rng, prod):
    templates = [  # code, name, (m1,d1), (m2,d2), type, value, category codes
        ("REPUBLIC", "Republic Day Sale", (1, 20), (1, 26), "PERCENT", 10, ["MOB", "LAP", "TVA", "HAP"]),
        ("SUMMER", "Summer Cooling Sale", (4, 1), (5, 15), "PERCENT", 15, ["HAP", "KIT"]),
        ("SCHOOL", "Back to School", (6, 10), (7, 10), "PERCENT", 12, ["BKS", "KID"]),
        ("MONSOON", "Monsoon Fashion Fest", (7, 15), (8, 15), "PERCENT", 18, ["MEN", "WOM", "FTW"]),
        ("FREEDOM", "Freedom Week Offer", (8, 10), (8, 16), "FLAT", 100, ["MOB", "PER", "GRO"]),
        ("DIWALI", "Diwali Dhamaka", (10, 18), (11, 12), "PERCENT", 20,
         ["MOB", "LAP", "TVA", "HAP", "KIT", "MEN", "WOM", "KID", "FTW", "FUR", "TOY"]),
        ("CLEARANCE", "Electronics Clearance", (11, 24), (11, 30), "PERCENT", 25, ["TVA", "LAP", "SPT"]),
        ("YEAREND", "Year-End Fest", (12, 18), (12, 31), "FLAT", 200, ["WOM", "MEN", "TOY", "SPT"]),
    ]
    code_to_ci = {c["code"]: i for i, c in enumerate(CATEGORIES)}
    promos, links, meta = [], [], []
    pid = 0
    for year in (2023, 2024, 2025):
        for code, name, (m1, d1), (m2, d2), typ, val, ccodes in templates:
            pid += 1
            s, e = date(year, m1, d1), date(year, m2, d2)
            val = val + (int(rng.integers(-2, 3)) if typ == "PERCENT" else 0)
            cis = [code_to_ci[c] for c in ccodes]
            cand = np.where(prod["cat_idx"].isin(cis))[0]
            chosen = cand[rng.random(len(cand)) < 0.55]
            promos.append(dict(promotion_id=pid, promo_code=f"{code}{year}", promo_name=f"{name} {year}",
                               discount_type=typ, discount_value=val, start_date=s.isoformat(),
                               end_date=e.isoformat(), is_active=False, created_at=f"{year}-01-01 09:00:00"))
            links += [(pid, int(p) + 1) for p in chosen]
            meta.append((pid, s.toordinal(), e.toordinal(), typ, float(val), chosen))
    pid += 1   # one upcoming promotion that has no sales yet
    promos.append(dict(promotion_id=pid, promo_code="NEWYEAR2026", promo_name="New Year Sale 2026",
                       discount_type="PERCENT", discount_value=10, start_date="2026-01-01", end_date="2026-01-15",
                       is_active=True, created_at="2025-12-15 09:00:00"))
    cand = np.where(prod["cat_idx"].isin([0, 1, 5, 6]))[0]
    links += [(pid, int(p) + 1) for p in cand[rng.random(len(cand)) < 0.4]]
    return pd.DataFrame(promos), pd.DataFrame(links, columns=["promotion_id", "product_id"]), meta


# ------------------------------------------------------------------------------ demand
def generate_orders(rng, cust, prod, stocked, store_w, store_open, emp_by_store, promo_meta, n_phys):
    C, P, S = len(cust["weight"]), len(prod), stocked.shape[0]
    hub = S - 1
    seg_lambda = np.array([s[4] for s in SEGMENTS])
    seas = np.array([0.85, 0.85, 0.95, 1.0, 1.0, 0.9, 0.9, 0.95, 1.05, 1.45, 1.35, 1.15])
    raw = np.array([seas[m % 12] * (1 + 0.35 * m / 35) for m in range(N_MONTHS)])
    n_orders_m = np.round(raw / raw.sum() * TARGET_ORDERS).astype(int)
    cat_trend = np.array([c["trend"] for c in CATEGORIES])
    cat_names = [c["name"] for c in CATEGORIES]
    cat_of = prod["cat_idx"].to_numpy()
    sw = store_w[:n_phys] / store_w[:n_phys].sum()

    o = {k: [] for k in ("cust", "ts", "d", "store", "online", "emp", "n_items")}
    items = {k: [] for k in ("ord", "prod", "store")}
    offset = 0
    for m in range(N_MONTHS):
        ms, me = month_bounds(m)
        n = int(n_orders_m[m])
        elig = (cust["reg"] <= me) & (cust["churn"] >= ms)
        p = cust["weight"] * elig
        if p.sum() == 0:
            continue
        c = rng.choice(C, n, p=p / p.sum())
        ndays = me - ms + 1
        dow = np.array([(date.fromordinal(ms + i).weekday() >= 5) * 0.3 + 1.0 for i in range(ndays)])
        d = ms + rng.choice(ndays, n, p=dow / dow.sum())
        d = np.minimum(np.maximum(d, cust["reg"][c]), me)
        d = np.minimum(d, cust["churn"][c])
        hours = np.arange(10, 22)
        hw = np.array([2, 3, 4, 4, 3, 3, 4, 5, 6, 6, 4, 2], dtype=float)
        tod = rng.choice(hours, n, p=hw / hw.sum()) * 3600 + rng.integers(0, 3600, n)
        ts = (d - START_ORD) * 86400 + tod

        online = rng.random(n) < (0.08 + 0.14 * m / 35)
        store = np.where(rng.random(n) < 0.85, cust["home"][c], rng.choice(n_phys, n, p=sw))
        bad = store_open[store] > d
        while bad.any():
            store[bad] = rng.choice(n_phys, bad.sum(), p=sw)
            bad = store_open[store] > d
        store = np.where(online, hub, store)

        emp = np.zeros(n, dtype=np.int64)          # 0 = no employee (online)
        for s in range(n_phys):
            idx = np.where((store == s) & ~online)[0]
            if len(idx):
                ids, hires = emp_by_store[s]
                ok = ids[hires <= ms]
                emp[idx] = rng.choice(ok if len(ok) else ids[:1], len(idx))

        n_items = np.minimum(1 + rng.poisson(seg_lambda[cust["seg_idx"][c]]), 8)

        # products for this month, per store
        cf = np.array([(1 + cat_trend[i]) ** (m / 12) * CATEGORY_SEASONALITY.get(cat_names[i], {}).get(month_number(m), 1.0)
                       for i in range(len(CATEGORIES))])
        avail = (prod["launch_m"].to_numpy() <= m) & (prod["end_m"].to_numpy() >= m)
        boost = np.ones(P)
        for _, ps, pe, _, _, chosen in promo_meta:
            if min(pe, me) - max(ps, ms) + 1 >= 15:
                boost[chosen] *= 1.35
        pf = prod["w"].to_numpy() * cf[cat_of] * avail * boost
        order_rep = np.repeat(np.arange(n), n_items)
        item_store = store[order_rep]
        item_prod = np.zeros(len(order_rep), dtype=np.int64)
        for s in range(S):
            sel = np.where(item_store == s)[0]
            if len(sel) == 0:
                continue
            cum = np.cumsum(pf * stocked[s])
            item_prod[sel] = np.searchsorted(cum, rng.random(len(sel)) * cum[-1], side="right").clip(0, P - 1)

        for k, v in (("cust", c), ("ts", ts), ("d", d), ("store", store), ("online", online), ("emp", emp),
                     ("n_items", n_items)):
            o[k].append(v)
        items["ord"].append(order_rep + offset)
        items["prod"].append(item_prod)
        items["store"].append(item_store)
        offset += n

    o = {k: np.concatenate(v) for k, v in o.items()}
    it = pd.DataFrame({k: np.concatenate(v) for k, v in items.items()})
    it = it.groupby(["ord", "prod"], as_index=False).agg(store=("store", "first"), cnt=("store", "size"))
    return o, it


def price_items(rng, it, o, prod, cust, promo_meta):
    """Quantities, historical price/cost snapshot and promotion discounts for every line."""
    n = len(it)
    cat = prod["cat_idx"].to_numpy()[it["prod"].to_numpy()]
    qm = np.array([c["qty"] for c in CATEGORIES])[cat]
    q = it["cnt"].to_numpy() * (1 + rng.poisson(np.maximum(qm - 1, 0.0)))
    seg = cust["seg_idx"][o["cust"][it["ord"].to_numpy()]]
    corp = (seg == 2) & (rng.random(n) < 0.3)
    q = np.where(corp, q * rng.integers(1, 4, n), q)

    d = o["d"][it["ord"].to_numpy()]
    years = (END_ORD - d) / 365.25
    p_now = prod["price_ref"].to_numpy()[it["prod"].to_numpy()].astype(float)
    c_now = prod["unit_cost"].to_numpy()[it["prod"].to_numpy()]
    price = np.maximum(np.round(p_now / PRICE_INFLATION ** years), 1.0)
    cost = np.round(c_now / PRICE_INFLATION ** years, 2)

    outlier = (rng.random(n) < 0.0015) & (price < 1500)
    q = np.where(outlier, rng.integers(25, 80, n), q)
    q = np.minimum(q, 100)

    best = np.zeros(n)
    promo = np.zeros(n, dtype=np.int64)
    applied = rng.random(n) < 0.85
    for pid, ps, pe, typ, val, chosen in promo_meta:
        flag = np.zeros(len(prod), dtype=bool)
        flag[chosen] = True
        mask = applied & (d >= ps) & (d <= pe) & flag[it["prod"].to_numpy()]
        unit = price * val / 100 if typ == "PERCENT" else np.minimum(val, 0.4 * price)
        upd = mask & (unit > best)
        best = np.where(upd, unit, best)
        promo = np.where(upd, pid, promo)
    disc = np.round(best * q, 2)
    it = it.copy()
    it["qty"], it["unit_price"], it["unit_cost"] = q, price, cost
    it["discount"], it["promo"] = disc, promo
    it["line_total"] = np.round(q * price - disc, 2)
    return it


# ------------------------------------------------------------------------------ inventory simulation
def simulate_inventory(rng, it, o, cancelled, prod, stocked, sup_lead, sup_late, store_open):
    S, P = stocked.shape
    n = len(it)
    order = np.lexsort((it["ord"].to_numpy(), o["ts"][it["ord"].to_numpy()]))
    it = it.iloc[order].reset_index(drop=True)
    ords, prods, stores = it["ord"].to_numpy(), it["prod"].to_numpy(), it["store"].to_numpy()
    qtys, costs = it["qty"].to_numpy(), it["unit_cost"].to_numpy()
    ts_arr = o["ts"][ords]
    is_canc = cancelled[ords]
    pair = stores * P + prods

    completed = ~is_canc
    units = np.bincount(pair[completed], weights=qtys[completed], minlength=S * P)
    first_ord = np.array([month_bounds(int(m))[0] for m in prod["launch_m"]])
    pair_start = np.maximum.outer(store_open, first_ord).clip(min=START_ORD).ravel()
    days = np.maximum(END_ORD - pair_start + 1, 1)
    rate = units / days
    p_of_pair = np.tile(np.arange(P), S)
    lead_p = sup_lead[prod["sup_idx"].to_numpy()][p_of_pair]

    # Minimum stock levels depend on price: nobody keeps 15 units of a 50,000-rupee laptop on the shelf.
    price_p = prod["price_ref"].to_numpy()[p_of_pair].astype(float)
    rl_floor = np.where(price_p >= 3000, 1, 2)
    rl = np.maximum(np.ceil(rate * (lead_p + 9)).astype(int), rl_floor)
    mx_gap = np.maximum(np.where(price_p >= 10000, 1, 2), np.ceil(rate * 45).astype(int))   # ~6 weeks of demand
    mx = np.maximum(rl * 3, rl + mx_gap)
    under = (rate > 0.15) & (rng.random(S * P) < 0.10)                  # under-provisioned fast movers
    rl = np.where(under, np.ceil(rl * 0.45).astype(int), rl)
    mx = np.where(under, np.ceil(mx * 0.6).astype(int), mx)
    # Opening stock: mostly near the order-up-to level; ~6-25% of slow / non-selling pairs are
    # deliberately over-stocked (these become the overstock / dead-stock examples).
    normal = np.ceil(mx * rng.uniform(0.6, 1.0, S * P)).astype(int)
    excess = np.where(units == 0, rng.integers(15, 151, S * P), rng.integers(20, 100, S * P))
    price_pair = prod["price_ref"].to_numpy()[p_of_pair].astype(float)
    excess = np.maximum(3, (excess * np.clip(3000 / price_pair, 0.05, 1.0)).astype(int))   # costly items are over-stocked in far smaller quantities
    make_excess = (rate < 0.03) & (rng.random(S * P) < np.where(units == 0, 0.25, 0.06))
    opening = np.where(make_excess, excess, normal)
    stocked_flat = stocked.ravel()

    stock = np.where(stocked_flat, opening, 0).astype(np.int64)
    pending = np.zeros(S * P, dtype=np.int64)
    last_restock = pair_start.copy()
    t_pair, t_type, t_qty, t_ts, t_ref = [], [], [], [], []
    for pr in np.where(stocked_flat)[0]:
        t_pair.append(pr); t_type.append(TXN_OPENING); t_qty.append(int(stock[pr]))
        t_ts.append(int((pair_start[pr] - START_ORD) * 86400)); t_ref.append(None)

    po_items, jitter, heap = [], {}, []
    keep = np.ones(n, dtype=bool)
    adj_r = rng.random(n)
    seq = 0

    def receive_until(limit):
        while heap and heap[0][0] <= limit:
            rts, _, pr, ordered, received, key = heapq.heappop(heap)
            stock[pr] += received
            pending[pr] -= ordered
            last_restock[pr] = START_ORD + rts // 86400
            t_pair.append(pr); t_type.append(TXN_PURCHASE); t_qty.append(received); t_ts.append(rts); t_ref.append(key)

    for i in range(n):
        if is_canc[i]:
            continue
        ts = int(ts_arr[i])
        receive_until(ts)
        pr, q = int(pair[i]), int(qtys[i])
        if stock[pr] < q:
            keep[i] = False                                      # lost sale: not enough stock
            continue
        stock[pr] -= q
        t_pair.append(pr); t_type.append(TXN_SALE); t_qty.append(-q); t_ts.append(ts); t_ref.append(int(ords[i]))
        if adj_r[i] < 0.002 and stock[pr] > 0:                   # occasional shrinkage / count correction
            a = min(int(stock[pr]), int(rng.integers(1, 4)))
            stock[pr] -= a
            t_pair.append(pr); t_type.append(TXN_ADJ); t_qty.append(-a); t_ts.append(ts + 60); t_ref.append(None)
        if stock[pr] + pending[pr] <= rl[pr]:
            qty = int(mx[pr] - stock[pr] - pending[pr])
            if qty < 1:
                continue
            s, p = pr // P, pr % P
            sup = int(prod["sup_idx"].iat[p])
            od = START_ORD + ts // 86400
            od += (-((od + 6) % 7)) % 7          # buyers place consolidated POs on Mondays
            key = (sup, s, od)
            if key not in jitter:
                extra = int(rng.integers(2, 11)) if rng.random() < sup_late[sup] else int(rng.integers(-1, 2))
                jitter[key] = max(1, int(sup_lead[sup]) + extra)
            recv_ord = od + jitter[key]
            received = qty if rng.random() > 0.05 else max(1, int(qty * rng.uniform(0.8, 0.99)))
            unit_cost = round(float(costs[i]) * float(rng.uniform(0.97, 1.0)), 2)
            arrives = recv_ord <= END_ORD
            po_items.append((sup, s, p, od, od + int(sup_lead[sup]), recv_ord if arrives else None, qty,
                             received if arrives else 0, unit_cost))
            pending[pr] += qty
            if arrives:
                seq += 1
                heapq.heappush(heap, ((recv_ord - START_ORD) * 86400 + 7 * 3600, seq, pr, qty, received, key))
    receive_until(END_SEC)

    sim = dict(stock=stock, pending=pending, rl=rl, mx=mx, last_restock=last_restock, pair_start=pair_start,
               stocked=stocked_flat, rate=rate, units=units,
               txn=(t_pair, t_type, t_qty, t_ts, t_ref), po_items=po_items, keep=keep, order=order,
               lost_units=int(qtys[~keep].sum()), lost_lines=int((~keep).sum()), n_completed=int(completed.sum()))
    return it, sim


# ------------------------------------------------------------------------------ main
def main(seed):
    rng = np.random.default_rng(seed)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating synthetic data (seed={seed}) -> {OUT_DIR}")

    segments = build_segments()
    categories = build_categories()
    suppliers, cats_of, sup_lead, sup_late = build_suppliers(rng)
    stores, store_w, store_open = build_stores()
    n_phys = int((stores["store_type"] == "STORE").sum())
    S = len(stores)
    employees, emp_by_store = build_employees(rng, stores, store_open)
    customers, cust = build_customers(rng, stores, store_w, n_phys)
    products, prod = build_products(rng, cats_of, sup_lead)
    promotions, product_promotions, promo_meta = build_promotions(rng, prod)
    P = len(prod)

    # Stores range expensive items selectively; the online hub stocks almost everything.
    price = prod["price_ref"].to_numpy()
    p_stock = np.where(price >= 10000, 0.30, np.where(price >= 3000, 0.45, 0.85))
    stocked = rng.random((S, P)) < p_stock
    stocked[S - 1] = rng.random(P) < np.where(price >= 10000, 0.75, 0.92)
    stocked[:, prod["w"].to_numpy() == 0] |= rng.random((S, int((prod["w"] == 0).sum()))) < 0.5

    o, it = generate_orders(rng, cust, prod, stocked, store_w, store_open, emp_by_store, promo_meta, n_phys)
    n_orders = len(o["cust"])
    o["cancelled"] = rng.random(n_orders) < CANCEL_RATE
    it = price_items(rng, it, o, prod, cust, promo_meta)
    it, sim = simulate_inventory(rng, it, o, o["cancelled"], prod, stocked, sup_lead, sup_late, store_open)
    keep = sim["keep"]
    it = it[keep].reset_index(drop=True)

    # ---- renumber orders chronologically; drop orders that lost every line
    has_lines = np.bincount(it["ord"].to_numpy(), minlength=n_orders) > 0
    o_keep = np.where(has_lines)[0]
    o_keep = o_keep[np.lexsort((o_keep, o["ts"][o_keep]))]
    new_id = np.full(n_orders, -1, dtype=np.int64)
    new_id[o_keep] = np.arange(1, len(o_keep) + 1)
    it["order_id"] = new_id[it["ord"].to_numpy()]
    it = it.sort_values(["order_id", "prod"]).reset_index(drop=True)
    it["order_item_id"] = np.arange(1, len(it) + 1)
    it["gst_rate"] = prod["gst_rate"].to_numpy()[it["prod"].to_numpy()]
    it["gst_part"] = np.round(it["line_total"] * it["gst_rate"] / (100 + it["gst_rate"]), 2)
    it["gross"] = np.round(it["qty"] * it["unit_price"], 2)

    agg = it.groupby("order_id").agg(subtotal=("gross", "sum"), discount_amount=("discount", "sum"),
                                     gst_amount=("gst_part", "sum"), total_amount=("line_total", "sum"))
    K = len(o_keep)
    oid = np.arange(1, K + 1)
    is_online = o["online"][o_keep]
    cancelled = o["cancelled"][o_keep]
    orders = pd.DataFrame(dict(
        order_id=oid, order_number=[f"ORD-{i:07d}" for i in oid],
        customer_id=o["cust"][o_keep] + 1,
        store_id=o["store"][o_keep] + 1,
        employee_id=pd.array(np.where(o["emp"][o_keep] == 0, pd.NA, o["emp"][o_keep]), dtype="Int64"),
        order_date=sec_to_str(o["ts"][o_keep]).to_numpy(),
        channel=np.where(is_online, "ONLINE", "IN_STORE"),
        order_status=np.where(cancelled, "CANCELLED", "COMPLETED")))
    orders = orders.join(agg.round(2), on="order_id")
    orders["created_at"] = orders["order_date"]
    orders["updated_at"] = orders["order_date"]

    order_items = pd.DataFrame(dict(
        order_item_id=it["order_item_id"], order_id=it["order_id"], product_id=it["prod"] + 1,
        promotion_id=pd.array(np.where(it["promo"] == 0, pd.NA, it["promo"]), dtype="Int64"),
        quantity=it["qty"], unit_price=it["unit_price"], unit_cost=it["unit_cost"],
        discount_amount=it["discount"], line_total=it["line_total"]))

    # ---- returns (only from completed orders)
    comp = it[~o["cancelled"][it["ord"].to_numpy()]].copy()
    cat_ret = 0.5 * np.array([c["ret"] for c in CATEGORIES])[prod["cat_idx"].to_numpy()]
    mult = np.ones(P)
    mult[rng.choice(np.where(prod["w"].to_numpy() > 0)[0], 10, replace=False)] = rng.uniform(4, 6, 10)
    p_ret = cat_ret[comp["prod"].to_numpy()] * mult[comp["prod"].to_numpy()]
    p_ret = p_ret * np.where(o["online"][comp["ord"].to_numpy()], 1.4, 1.0)
    comp = comp[rng.random(len(comp)) < np.minimum(p_ret, 0.6)]
    delay = np.minimum(1 + rng.geometric(0.15, len(comp)), 30)
    comp["ret_ts"] = o["ts"][comp["ord"].to_numpy()] + delay * 86400 + rng.integers(0, 40000, len(comp))
    comp = comp[comp["ret_ts"] <= END_SEC]
    comp["ret_qty"] = np.where(comp["qty"] > 1, np.maximum(1, (comp["qty"] * rng.uniform(0.3, 1.0, len(comp))).astype(int)), 1)
    comp["refund"] = np.round(comp["line_total"] * comp["ret_qty"] / comp["qty"], 2)

    apparel = {5, 6, 7, 8}
    electro = {0, 1, 2, 3, 4, 11, 12}
    reasons = ["DEFECTIVE", "WRONG_ITEM", "NOT_AS_DESCRIBED", "CHANGED_MIND", "SIZE_ISSUE", "DAMAGED_IN_TRANSIT", "OTHER"]
    rp = {"a": [0.12, 0.08, 0.15, 0.20, 0.38, 0.04, 0.03], "e": [0.38, 0.10, 0.15, 0.17, 0.0, 0.15, 0.05],
          "o": [0.15, 0.12, 0.20, 0.30, 0.0, 0.12, 0.11]}
    first_line = comp.groupby("order_id").head(1)
    ret_reason = {}
    for oid_, ci in zip(first_line["order_id"], prod["cat_idx"].to_numpy()[first_line["prod"].to_numpy()]):
        k = "a" if ci in apparel else "e" if ci in electro else "o"
        ret_reason[oid_] = rng.choice(reasons, p=rp[k])
    ret_orders = comp.groupby("order_id").agg(ret_ts=("ret_ts", "min"), refund=("refund", "sum")).reset_index()
    ret_orders = ret_orders.sort_values(["ret_ts", "order_id"]).reset_index(drop=True)
    ret_orders["return_id"] = np.arange(1, len(ret_orders) + 1)
    rid = dict(zip(ret_orders["order_id"], ret_orders["return_id"]))
    comp["return_id"] = comp["order_id"].map(rid)
    comp["ret_ts"] = comp["order_id"].map(dict(zip(ret_orders["order_id"], ret_orders["ret_ts"])))
    defective = comp["order_id"].map(ret_reason).isin(["DEFECTIVE", "DAMAGED_IN_TRANSIT"])
    comp["restocked"] = np.where(defective, rng.random(len(comp)) < 0.05, rng.random(len(comp)) < 0.95)

    order_store = dict(zip(oid, o["store"][o_keep]))
    order_emp_pool = {}
    emp_ids = employees["employee_id"].to_numpy()
    processed = []
    for orow in ret_orders.itertuples():
        st = order_store[orow.order_id]
        ids, hires = emp_by_store[st]
        d = START_ORD + int(orow.ret_ts) // 86400
        ok = ids[hires <= d]
        processed.append(int(rng.choice(ok if len(ok) else ids[:1])))
    returns = pd.DataFrame(dict(
        return_id=ret_orders["return_id"], order_id=ret_orders["order_id"],
        return_date=sec_to_str(ret_orders["ret_ts"]).to_numpy(),
        return_reason=ret_orders["order_id"].map(ret_reason),
        refund_amount=ret_orders["refund"].round(2), processed_by=processed))
    returns["created_at"] = returns["return_date"]
    return_items = pd.DataFrame(dict(
        return_item_id=np.arange(1, len(comp) + 1), return_id=comp["return_id"].to_numpy(),
        order_item_id=comp["order_item_id"].to_numpy(), quantity=comp["ret_qty"].to_numpy(),
        refund_amount=comp["refund"].to_numpy(), restocked=comp["restocked"].to_numpy()))

    # ---- payments
    tot = orders["total_amount"].to_numpy()
    ots = o["ts"][o_keep]
    pay_rows = []
    m_store = ["UPI", "CARD", "CASH", "NET_BANKING", "WALLET"]
    for i in range(K):
        r = rng.random()
        if cancelled[i]:
            if r < 0.5:
                pay_rows.append((i + 1, ots[i] + 120, str(rng.choice(m_store[:2] + m_store[3:])), tot[i], "REFUNDED"))
            continue
        if r < 0.004:                       # data-quality scenario: completed order with no payment
            continue
        pm = str(rng.choice(m_store if not is_online[i] else ["UPI", "CARD", "NET_BANKING", "WALLET"],
                            p=[0.45, 0.28, 0.12, 0.08, 0.07] if not is_online[i] else [0.52, 0.30, 0.10, 0.08]))
        if rng.random() < 0.05:
            pay_rows.append((i + 1, ots[i] + 30, pm, tot[i], "FAILED"))
            pay_rows.append((i + 1, ots[i] + int(rng.integers(120, 480)), pm, tot[i], "SUCCESS"))
        else:
            pay_rows.append((i + 1, ots[i] + int(rng.integers(5, 300)), pm, tot[i], "SUCCESS"))
    payments = pd.DataFrame(pay_rows, columns=["order_id", "ts", "payment_method", "amount", "payment_status"])
    payments = payments[payments["amount"] > 0].reset_index(drop=True)
    payments.insert(0, "payment_id", np.arange(1, len(payments) + 1))
    payments["payment_date"] = sec_to_str(payments.pop("ts")).to_numpy()
    payments["transaction_ref"] = [None if m == "CASH" else "TXN" + "".join(rng.choice(list("0123456789ABCDEF"), 12))
                                   for m in payments["payment_method"]]
    payments["created_at"] = payments["payment_date"]
    payments = payments[["payment_id", "order_id", "payment_date", "payment_method", "amount", "payment_status",
                         "transaction_ref", "created_at"]]

    # ---- purchases
    po = pd.DataFrame(sim["po_items"], columns=["sup", "s", "p", "od", "exp", "recv", "q_ord", "q_recv", "cost"])
    grp = po.groupby(["sup", "s", "od"], as_index=False).agg(exp=("exp", "first"), recv=("recv", "first"),
                                                             total=("q_ord", "size"))
    grp = grp.sort_values(["od", "sup", "s"]).reset_index(drop=True)
    grp["purchase_id"] = np.arange(1, len(grp) + 1)
    po = po.merge(grp[["sup", "s", "od", "purchase_id"]], on=["sup", "s", "od"])
    po["line"] = po["q_ord"] * po["cost"]
    tot_po = po.groupby("purchase_id")["line"].sum().round(2)
    purchases = pd.DataFrame(dict(
        purchase_id=grp["purchase_id"], po_number=[f"PO-{i:06d}" for i in grp["purchase_id"]],
        supplier_id=grp["sup"] + 1, store_id=grp["s"] + 1, order_date=ord_to_str(grp["od"]).to_numpy(),
        expected_date=ord_to_str(grp["exp"]).to_numpy(),
        received_date=pd.Series(ord_to_str(grp["recv"].fillna(0).astype(int)).to_numpy()).where(grp["recv"].notna()),
        status=np.where(grp["recv"].notna(), "RECEIVED", "ORDERED"),
        total_amount=tot_po.reindex(grp["purchase_id"]).to_numpy()))
    purchases["created_at"] = purchases["order_date"] + " 09:00:00"
    purchase_items = pd.DataFrame(dict(
        purchase_item_id=np.arange(1, len(po) + 1), purchase_id=po["purchase_id"], product_id=po["p"] + 1,
        quantity_ordered=po["q_ord"], quantity_received=po["q_recv"], unit_cost=po["cost"]))
    key_to_po = {(r.sup, r.s, r.od): r.purchase_id for r in grp.itertuples()}

    # ---- inventory ledger + current stock
    stock, S_P = sim["stock"].copy(), S * P
    t_pair, t_type, t_qty, t_ts, t_ref = (list(x) for x in sim["txn"])
    ref_type, ref_id = [], []
    for ty, rf in zip(t_type, t_ref):
        if ty == TXN_SALE:
            ref_type.append("SALES_ORDER"); ref_id.append(int(new_id[rf]))
        elif ty == TXN_PURCHASE:
            ref_type.append("PURCHASE"); ref_id.append(key_to_po[rf])
        else:
            ref_type.append(None); ref_id.append(None)
    # dropped-order sale ledger rows cannot exist: their items were never sold
    ledger = pd.DataFrame(dict(pair=t_pair, type=t_type, qty=t_qty, ts=t_ts, reference_type=ref_type,
                               reference_id=ref_id))
    # sales of orders that were fully removed cannot appear (all their lines were dropped => no SALE txn)
    rt_pair = (o["store"][o_keep][comp["order_id"].to_numpy() - 1] * P + comp["prod"].to_numpy())
    rr = comp["restocked"].to_numpy()
    ret_led = pd.DataFrame(dict(pair=rt_pair[rr], type=TXN_RETURN, qty=comp["ret_qty"].to_numpy()[rr],
                                ts=comp["ret_ts"].to_numpy()[rr] + 3600, reference_type="RETURN",
                                reference_id=comp["return_id"].to_numpy()[rr]))
    np.add.at(stock, rt_pair[rr], comp["ret_qty"].to_numpy()[rr])
    ledger = pd.concat([ledger, ret_led], ignore_index=True)

    # a few pairs are written off at the end of the window (ledger-consistent zero stock)
    cand = np.where(sim["stocked"] & (stock > 0) & (stock <= 15) & (sim["pending"] == 0))[0]
    wo = rng.choice(cand, min(15, len(cand)), replace=False)
    ledger = pd.concat([ledger, pd.DataFrame(dict(pair=wo, type=TXN_ADJ, qty=-stock[wo], ts=END_SEC - 3600,
                                                  reference_type=None, reference_id=None))], ignore_index=True)
    stock[wo] = 0

    ledger = ledger.sort_values(["ts", "pair"], kind="stable").reset_index(drop=True)
    inventory_transactions = pd.DataFrame(dict(
        transaction_id=np.arange(1, len(ledger) + 1), store_id=ledger["pair"] // P + 1,
        product_id=ledger["pair"] % P + 1, transaction_type=[TXN_NAMES[t] for t in ledger["type"]],
        quantity_change=ledger["qty"], transaction_date=sec_to_str(ledger["ts"]).to_numpy(),
        reference_type=ledger["reference_type"], reference_id=pd.array(ledger["reference_id"], dtype="Int64")))
    inventory_transactions["created_at"] = inventory_transactions["transaction_date"]

    # ---- inventory snapshot (with a few planted ledger mismatches)
    rows = np.where(sim["stocked"])[0]
    onhand = stock[rows].copy()
    mism = rng.choice(len(rows), int(0.012 * len(rows)), replace=False)
    onhand[mism] = np.maximum(0, onhand[mism] + rng.choice([-3, -2, -1, 1, 2, 5], len(mism)))
    reserved = np.where((rng.random(len(rows)) < 0.2) & (onhand > 0),
                        np.minimum(onhand, rng.integers(1, 4, len(rows))), 0)
    restock = np.where(sim["last_restock"][rows] < START_ORD, START_ORD, sim["last_restock"][rows])
    inventory = pd.DataFrame(dict(
        inventory_id=np.arange(1, len(rows) + 1), store_id=rows // P + 1, product_id=rows % P + 1,
        quantity_on_hand=onhand, reserved_quantity=reserved, reorder_level=sim["rl"][rows],
        max_stock_level=sim["mx"][rows], last_restocked_date=ord_to_str(restock).to_numpy()))
    inventory["updated_at"] = f"{END.isoformat()} 23:59:00"

    # ---- write
    customers_out = customers[["customer_id", "first_name", "last_name", "email", "phone", "gender",
                               "date_of_birth", "city", "state", "segment_id", "registration_date", "is_active",
                               "created_at", "updated_at"]]
    orders_out = orders[["order_id", "order_number", "customer_id", "store_id", "employee_id", "order_date", "channel",
                         "order_status", "subtotal", "discount_amount", "gst_amount", "total_amount", "created_at",
                         "updated_at"]]
    employees_out = employees[["employee_id", "first_name", "last_name", "email", "store_id", "manager_id",
                               "job_title", "hire_date", "is_active", "created_at", "updated_at"]]
    tables = dict(customer_segments=segments, categories=categories, suppliers=suppliers, stores=stores,
                  employees=employees_out, customers=customers_out,
                  products=products, promotions=promotions, product_promotions=product_promotions,
                  sales_orders=orders_out, sales_order_items=order_items, payments=payments, returns=returns,
                  return_items=return_items, inventory=inventory, inventory_transactions=inventory_transactions,
                  purchases=purchases, purchase_items=purchase_items)
    print("Writing CSV files:")
    for name, df in tables.items():
        write_csv(df, name)

    done = orders_out[orders_out["order_status"] == "COMPLETED"]
    print("\nSimulation notes:")
    print(f"  completed order lines demanded : {sim['n_completed']:,}")
    print(f"  lost to stock-outs             : {sim['lost_lines']:,} lines ({sim['lost_lines'] / sim['n_completed']:.1%})")
    print(f"  orders kept / cancelled        : {len(done):,} / {int(cancelled.sum()):,}")
    print(f"  gross sales (completed, incl. GST): INR {done['total_amount'].sum():,.0f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seed", type=int, default=42)
    main(ap.parse_args().seed)
