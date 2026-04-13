import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

CONGRESS_API_KEY = os.environ.get("CONGRESS_API_KEY")
FEC_API_KEY = os.environ.get("FEC_API_KEY")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
HEADERS = {"User-Agent": "civic-tracker/1.0 (github.com/bucket-debug/civic-tracker)"}

status = {
    "bills": "fail",
    "finance": "fail",
    "members": "fail",
    "news": "fail",
}


def save(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def log_response_error(label, resp):
    try:
        body = resp.text[:400]
    except Exception:
        body = "(unreadable)"
    print(f"[FAIL] {label:<24} HTTP {resp.status_code}: {body}")


def congress_get(path, params=None):
    """GET a congress.gov v3 endpoint, injecting the API key."""
    full_params = {**(params or {}), "api_key": CONGRESS_API_KEY}
    resp = requests.get(
        f"https://api.congress.gov/v3/{path}",
        params=full_params,
        headers=HEADERS,
        timeout=30,
    )
    return resp


def fetch_cosponsor_breakdown(bill_type, bill_number):
    """Return (dem_count, rep_count) for a bill. Returns (0, 0) on any failure."""
    try:
        type_lower = (bill_type or "").lower()
        resp = congress_get(
            f"bill/119/{type_lower}/{bill_number}/cosponsors",
            {"format": "json"},
        )
        if not resp.ok:
            return 0, 0
        cosponsors = resp.json().get("cosponsors", [])
        dem = sum(1 for c in cosponsors if (c.get("party") or "").upper() == "D")
        rep = sum(1 for c in cosponsors if (c.get("party") or "").upper() == "R")
        return dem, rep
    except Exception:
        return 0, 0


def shape_bill(b):
    """Normalise a raw congress.gov bill record into our storage schema."""
    sponsors = b.get("sponsors") or []
    sponsor_name = sponsors[0].get("fullName") if sponsors else None
    latest = b.get("latestAction") or {}
    bill_type = (b.get("type") or "").upper()
    bill_number = b.get("number")

    dem, rep = fetch_cosponsor_breakdown(bill_type, bill_number)
    time.sleep(0.2)  # Respect congress.gov rate limits between cosponsor calls

    return {
        "congress": 119,
        "number": bill_number,
        "type": bill_type,
        "title": b.get("title"),
        "latestAction": {
            "text": latest.get("text"),
            "actionDate": latest.get("actionDate"),
        },
        "updateDate": b.get("updateDate"),
        "sponsor": sponsor_name,
        "democratCosponsors": dem,
        "republicanCosponsors": rep,
    }


# ── 1. Bills — 119th Congress ────────────────────────────────────────────────
# Note: pass a space in the sort value so requests encodes it as "+":
#   params={"sort": "updateDate desc"} → ?sort=updateDate+desc  (correct)
#   params={"sort": "updateDate+desc"} → ?sort=updateDate%2Bdesc (wrong)
try:
    resp = congress_get("bill/119", {
        "format": "json",
        "limit": 50,
        "sort": "updateDate desc",
    })
    if not resp.ok:
        log_response_error("bills", resp)
        resp.raise_for_status()

    raw_bills = resp.json().get("bills", [])
    bills = [shape_bill(b) for b in raw_bills]
    save("bills.json", bills)
    status["bills"] = "success"
    print(f"[OK]   bills                   — {len(bills)} records → data/bills.json")

    # ── 2. Recently passed bills — filter HR + S bills by action text ─────────
    bills_passed = []
    for bill_type_param in ("hr", "s", "hjres", "sjres"):
        try:
            pr = congress_get("bill/119", {
                "format": "json",
                "limit": 50,
                "sort": "updateDate desc",
                "billType": bill_type_param,
            })
            if not pr.ok:
                continue
            for b in pr.json().get("bills", []):
                action_text = ((b.get("latestAction") or {}).get("text") or "").lower()
                if any(kw in action_text for kw in (
                    "became public law", "signed by president", "enacted"
                )):
                    bills_passed.append(shape_bill(b))
        except Exception as pe:
            print(f"  [WARN] bills_passed/{bill_type_param}: {pe}")

    save("bills_passed.json", bills_passed)
    print(f"[OK]   bills_passed            — {len(bills_passed)} records → data/bills_passed.json")

except Exception as e:
    print(f"[FAIL] bills                   — {e}")

# ── 3. Campaign finance ────────────────────────────────────────────────────────
try:
    resp = requests.get(
        "https://api.open.fec.gov/v1/schedules/schedule_a/",
        params={
            "sort": "-contribution_receipt_amount",
            "per_page": 100,
            "two_year_transaction_period": 2026,
            "api_key": FEC_API_KEY,
        },
        headers=HEADERS,
        timeout=30,
    )
    if not resp.ok:
        log_response_error("finance", resp)
        resp.raise_for_status()
    raw = resp.json().get("results", [])
    finance = []
    for r in raw:
        committee = r.get("committee") or {}
        finance.append({
            "contributor_name": r.get("contributor_name"),
            "contribution_receipt_amount": r.get("contribution_receipt_amount"),
            "committee_name": committee.get("name"),
            "contribution_receipt_date": r.get("contribution_receipt_date"),
        })
    save("finance.json", finance)
    status["finance"] = "success"
    print(f"[OK]   finance                 — {len(finance)} records → data/finance.json")
except Exception as e:
    print(f"[FAIL] finance                 — {e}")

# ── 4. Congress members — paginated to get ALL current members ─────────────────
try:
    members = []
    limit = 250
    offset = 0
    page = 1

    while True:
        resp = congress_get("member", {
            "format": "json",
            "currentMember": "true",
            "limit": limit,
            "offset": offset,
        })
        if not resp.ok:
            log_response_error(f"members page {page}", resp)
            resp.raise_for_status()

        body = resp.json()
        batch = body.get("members", [])
        if not batch:
            break

        for m in batch:
            # Extract chamber and start year from terms list
            terms = m.get("terms") or {}
            items = terms.get("item") if isinstance(terms, dict) else []
            items = items or []
            chamber = items[-1].get("chamber") if items else None
            start_year = items[0].get("startYear") if items else None

            members.append({
                "bioguideId": m.get("bioguideId"),
                "name": m.get("name"),
                "party": m.get("partyName"),
                "state": m.get("state"),
                "district": m.get("district"),
                "chamber": chamber,
                "startYear": start_year,
            })

        print(f"  [members] page {page}: +{len(batch)} → {len(members)} total")

        # Stop if fewer than limit returned (last page), or no pagination.next
        pagination = body.get("pagination") or {}
        if len(batch) < limit or not pagination.get("next"):
            break
        offset += limit
        page += 1
        time.sleep(0.5)

    save("members.json", members)
    status["members"] = "success"
    print(f"[OK]   members                 — {len(members)} total → data/members.json")
except Exception as e:
    print(f"[FAIL] members                 — {e}")

# ── 5. News via RSS feeds ─────────────────────────────────────────────────────
RSS_FEEDS = [
    ("NPR Politics",    "https://feeds.npr.org/1014/rss.xml"),
    ("Politico",        "https://rss.politico.com/politics-news.rss"),
    ("Washington Post", "https://feeds.washingtonpost.com/rss/politics"),
]

try:
    news = []
    for source_name, feed_url in RSS_FEEDS:
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=30)
            if not resp.ok:
                log_response_error(f"news/{source_name}", resp)
                continue
            root = ET.fromstring(resp.content)
            items = root.findall("./channel/item")
            for item in items:
                def text(tag):
                    el = item.find(tag)
                    return el.text.strip() if el is not None and el.text else None

                pub_date = text("pubDate")
                published_at = None
                if pub_date:
                    try:
                        from email.utils import parsedate_to_datetime
                        published_at = parsedate_to_datetime(pub_date).isoformat()
                    except Exception:
                        published_at = pub_date

                news.append({
                    "title": text("title"),
                    "source": source_name,
                    "description": text("description"),
                    "url": text("link"),
                    "publishedAt": published_at,
                })
            print(f"[OK]   news/{source_name:<18} — {len(items)} items")
        except Exception as feed_err:
            print(f"[FAIL] news/{source_name:<18} — {feed_err}")

    if not news:
        raise RuntimeError("All RSS feeds failed — no news items collected")

    news.sort(key=lambda a: a.get("publishedAt") or "", reverse=True)
    save("news.json", news)
    status["news"] = "success"
    print(f"[OK]   news                    — {len(news)} articles → data/news.json")
except Exception as e:
    print(f"[FAIL] news                    — {e}")

# ── Write last_updated.json ────────────────────────────────────────────────────
last_updated = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": status,
}
save("last_updated.json", last_updated)
print(f"\n[OK]   last_updated            — {last_updated['timestamp']}")
