"""Quick console dump of every table in risk_profiling.db."""
import sqlite3

db = sqlite3.connect("data/risk_profiling.db")
db.row_factory = sqlite3.Row

# ── Companies ────────────────────────────────────────────────────────────────
print("=== COMPANIES (KYC baselines) ===")
for r in db.execute(
    "SELECT id, legal_name, country, baseline_risk_rating, expected_monthly_volume_eur FROM companies"
):
    vol = f"{r['expected_monthly_volume_eur']:,.0f}" if r["expected_monthly_volume_eur"] else "n/d"
    print(f"  [{r['id']}] {r['legal_name']} | {r['country']} | {r['baseline_risk_rating']} | {vol} EUR/mo")

# ── News per company ─────────────────────────────────────────────────────────
print("\n=== NEWS ARTICLES — conteo por empresa ===")
for r in db.execute(
    "SELECT c.legal_name, COUNT(*) AS n, "
    "MAX(n.adverse_score) AS max_adv "
    "FROM news_articles n JOIN companies c ON c.id=n.company_id GROUP BY c.id"
):
    print(f"  {r['legal_name']}: {r['n']} artículos | max adverse_score: {r['max_adv']}")

print("\n=== NEWS ARTICLES — top 8 por adverse_score ===")
for r in db.execute(
    "SELECT c.legal_name, n.title, n.source, n.published_at, n.adverse_score, n.matched_keywords "
    "FROM news_articles n JOIN companies c ON c.id=n.company_id "
    "ORDER BY n.adverse_score DESC LIMIT 8"
):
    kw = r["matched_keywords"]
    print(f"  [{r['legal_name']}] score={r['adverse_score']}  kw={kw}")
    print(f"    {r['title'][:80]}")
    print(f"    {r['source']}  |  {r['published_at']}")

# ── Funding ───────────────────────────────────────────────────────────────────
print("\n=== FUNDING EVENTS ===")
rows = db.execute(
    "SELECT c.legal_name, f.title, f.round_type, f.amount_value, f.amount_currency, f.announced_at "
    "FROM funding_events f JOIN companies c ON c.id=f.company_id "
    "ORDER BY f.amount_value DESC"
).fetchall()
if rows:
    for r in rows:
        amt = f"{r['amount_value']:,.0f} {r['amount_currency']}" if r["amount_value"] else "importe n/d"
        print(f"  [{r['legal_name']}] {r['round_type'] or '?'} | {amt} | {r['announced_at']}")
        print(f"    {r['title'][:90]}")
else:
    print("  (sin registros)")

# ── Registry ─────────────────────────────────────────────────────────────────
print("\n=== REGISTRY RECORDS (GLEIF) ===")
for r in db.execute(
    "SELECT c.legal_name, rr.lei, rr.entity_status, rr.lei_status, rr.country, rr.address "
    "FROM registry_records rr JOIN companies c ON c.id=rr.company_id"
):
    print(f"  [{r['legal_name']}]")
    print(f"    LEI        : {r['lei']}")
    print(f"    Status     : {r['entity_status']} / {r['lei_status']}")
    print(f"    País       : {r['country']}")
    print(f"    Dirección  : {r['address']}")

# ── Domains ───────────────────────────────────────────────────────────────────
print("\n=== DOMAIN RECORDS (RDAP) ===")
for r in db.execute(
    "SELECT c.legal_name, d.domain, d.registrar, d.registration_date, "
    "d.last_changed_date, d.expiration_date, d.statuses "
    "FROM domain_records d JOIN companies c ON c.id=d.company_id"
):
    print(f"  [{r['legal_name']}] {r['domain']}")
    print(f"    Registrar     : {r['registrar']}")
    print(f"    Registrado    : {r['registration_date']}")
    print(f"    Último cambio : {r['last_changed_date']}")
    print(f"    Expira        : {r['expiration_date']}")
    print(f"    Estados       : {r['statuses']}")

# ── Audit log ─────────────────────────────────────────────────────────────────
print("\n=== AUDIT LOG (últimas 10 entradas) ===")
for r in db.execute(
    "SELECT actor, action, entity_type, entity_id, details, timestamp "
    "FROM audit_logs ORDER BY id DESC LIMIT 10"
):
    print(f"  {r['timestamp']}  {r['action']:25s}  {r['entity_type']} #{r['entity_id']}  {r['details']}")

db.close()
