import json
import os
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
    """Print HTTP status and a snippet of the response body to help debug failures."""
    try:
        body = resp.text[:500]
    except Exception:
        body = "(unreadable)"
    print(f"[FAIL] {label:<12} — HTTP {resp.status_code}: {body}")


# 1. Congress bills
# Note: requests encodes "+" in params values as "%2B"; to send "updateDate+desc"
# (which congress.gov requires), pass a space — requests encodes space as "+".
try:
    resp = requests.get(
        "https://api.congress.gov/v3/bill",
        params={
            "sort": "updateDate desc",
            "limit": 20,
            "api_key": CONGRESS_API_KEY,
        },
        headers=HEADERS,
        timeout=30,
    )
    if not resp.ok:
        log_response_error("bills", resp)
        resp.raise_for_status()
    raw = resp.json().get("bills", [])
    bills = []
    for b in raw:
        sponsors = b.get("sponsors") or []
        sponsor_name = sponsors[0].get("fullName") if sponsors else None
        latest = b.get("latestAction") or {}
        bills.append({
            "billNumber": b.get("number"),
            "title": b.get("title"),
            "sponsor": sponsor_name,
            "latestActionText": latest.get("text"),
            "latestActionDate": latest.get("actionDate"),
            "updateDate": b.get("updateDate"),
            "type": b.get("type"),
        })
    save("bills.json", bills)
    status["bills"] = "success"
    print(f"[OK]   bills        — {len(bills)} records saved to data/bills.json")
except Exception as e:
    print(f"[FAIL] bills        — {e}")

# 2. Campaign finance
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
    print(f"[OK]   finance      — {len(finance)} records saved to data/finance.json")
except Exception as e:
    print(f"[FAIL] finance      — {e}")

# 3. Congress members
try:
    resp = requests.get(
        "https://api.congress.gov/v3/member",
        params={
            "currentMember": "true",
            "limit": 250,
            "api_key": CONGRESS_API_KEY,
        },
        headers=HEADERS,
        timeout=30,
    )
    if not resp.ok:
        log_response_error("members", resp)
        resp.raise_for_status()
    raw = resp.json().get("members", [])
    members = []
    for m in raw:
        terms = m.get("terms") or {}
        items = terms.get("item") if isinstance(terms, dict) else None
        chamber = items[-1].get("chamber") if items else None
        members.append({
            "name": m.get("name"),
            "party": m.get("partyName"),
            "state": m.get("state"),
            "district": m.get("district"),
            "chamber": chamber,
        })
    save("members.json", members)
    status["members"] = "success"
    print(f"[OK]   members      — {len(members)} records saved to data/members.json")
except Exception as e:
    print(f"[FAIL] members      — {e}")

# 4. News via RSS feeds (replaces NewsAPI — free-tier developer keys block server requests)
# Pulls from three reliable public RSS feeds; parses with stdlib xml.etree.ElementTree.
RSS_FEEDS = [
    ("NPR Politics",       "https://feeds.npr.org/1014/rss.xml"),
    ("Politico",           "https://rss.politico.com/politics-news.rss"),
    ("Washington Post",    "https://feeds.washingtonpost.com/rss/politics"),
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
            # RSS 2.0: items live under channel/item
            items = root.findall("./channel/item")
            for item in items:
                def text(tag):
                    el = item.find(tag)
                    return el.text.strip() if el is not None and el.text else None

                pub_date = text("pubDate")
                # Normalise pubDate → ISO-8601 if possible
                published_at = None
                if pub_date:
                    try:
                        from email.utils import parsedate_to_datetime
                        published_at = parsedate_to_datetime(pub_date).isoformat()
                    except Exception:
                        published_at = pub_date  # keep raw if parse fails

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

    # Sort newest-first across all feeds
    news.sort(key=lambda a: a.get("publishedAt") or "", reverse=True)
    save("news.json", news)
    status["news"] = "success"
    print(f"[OK]   news         — {len(news)} records saved to data/news.json")
except Exception as e:
    print(f"[FAIL] news         — {e}")

# Write last_updated.json
last_updated = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": status,
}
save("last_updated.json", last_updated)
print(f"\n[OK]   last_updated  — data/last_updated.json written at {last_updated['timestamp']}")
