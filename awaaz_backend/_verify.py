import logging
import sys
import urllib.error
import urllib.parse
import urllib.request
import json

logging.disable(logging.CRITICAL)

BASE = "http://127.0.0.1:8000"
KEY = "awaaz-admin-2024"
failures = []


def call(path, method="GET", payload=None, key=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("X-API-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            return res.status, dict(res.headers), res.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "ignore")


def check(label, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        failures.append(label)


# Citizen flow
st, _, body = call("/")
check("GET / -> 200", st == 200)

st, _, body = call("/api/complaints/text", "POST",
                   {"transcript_text": "Raja Bazaar mein aloo 250 rupay kilo bech rahe hain.",
                    "shop_name": "Final Verify Store"})
check("POST complaint -> 201", st == 201)
data = json.loads(body)
check("price extracted (250)", data.get("reported_price") == 250.0)
check("language detected", bool(data.get("detected_language")))
check("native response present", bool(data.get("native_response")))

# Food safety severity fix
st, _, body = call("/api/complaints/text", "POST",
                   {"transcript_text": "Is chicken se bachon ka pet kharab ho gaya hai."})
d = json.loads(body)
check("food safety category", d.get("category") == "PFA - Food Safety")
check("illness -> High urgency", d.get("urgency") == "High")

# Rates
st, _, body = call("/api/rates?search=potato")
check("rates search -> 200", st == 200)

# Public map points
st, _, body = call("/api/analytics/map/points")
pts = json.loads(body)
check("map points obfuscated", all(round(p["lat"], 3) == p["lat"] for p in pts))
check("map points hide shop names", all("shop_name" not in p for p in pts))

# Admin gate
check("anonymous config -> 401", call("/api/admin/config")[0] == 401)
check("bad key config -> 403", call("/api/admin/config", key="bad")[0] == 403)
check("health public -> 200", call("/api/admin/health")[0] == 200)
check("anonymous export -> 401", call("/api/admin/export")[0] == 401)
check("anonymous reseed -> 401", call("/api/admin/reseed", "POST")[0] == 401)

# Authorized
check("authorized config -> 200", call("/api/admin/config", key=KEY)[0] == 200)
st, hdrs, body = call("/api/admin/export", key=KEY)
check("authorized export -> 200", st == 200)
check("export is attachment", "attachment" in hdrs.get("content-disposition", ""))
check("export has record count", "x-record-count" in {k.lower() for k in hdrs})

st, _, body = call(f"/api/admin/shops/{urllib.parse.quote('Final Verify Store')}", key=KEY)
check("shop dossier -> 200", st == 200)
prof = json.loads(body)
check("dossier citation count", prof["total_citations"] >= 1)
check("dossier has action", bool(prof.get("recommended_action")))

# Filter validation
check("bad date -> 422", call("/api/complaints?date_from=xx")[0] == 422)
check("bad bbox -> 422", call("/api/complaints?bbox=1,2")[0] == 422)
check("valid bbox -> 200", call("/api/complaints?bbox=33.6,73.0,33.7,73.1")[0] == 200)

# Analytics
for ep in ("/api/analytics/overview", "/api/analytics/hotspots",
           "/api/analytics/repeat-offenders", "/api/analytics/trends?days=7"):
    check(f"{ep} -> 200", call(ep)[0] == 200)

print()
if failures:
    print(f"{len(failures)} FAILED")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("ALL FINAL VERIFICATION CHECKS PASSED")
