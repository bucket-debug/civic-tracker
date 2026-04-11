import json
import os
from datetime import datetime, timezone

import requests

CONGRESS_API_KEY = os.environ.get("CONGRESS_API_KEY")
FEC_API_KEY = os.environ.get("FEC_API_KEY")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

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


# 1. Congress bills
try:
    url = (
        "https://api.congress.gov/v3/bill"
        f"?sort=updateDate&direction=desc&limit=20&api_key={CONGRESS_API_KEY}"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    raw = resp.json().get("bills", [])
    bills = [
        {
            "billNumber": b.get("number"),
            "title": b.get("title"),
            "sponsor": b.get("sponsors", [{}])[0].get("fullName") if b.get("sponsors") else None,
            "latestActionText": b.get("latestAction", {}).get("text"),
            "latestActionDate": b.get("latestAction", {}).get("actionDate"),
            "updateDate": b.get("updateDate"),
            "type": b.get("type"),
        }
        for b in raw
    ]
    save("bills.json", bills)
    status["bills"] = "success"
    print(f"[OK]   bills       — {len(bills)} records saved to data/bills.json")
except Exception as e:
    print(f"[FAIL] bills       — {e}")

# 2. Campaign finance
try:
    url = (
        "https://api.open.fec.gov/v1/schedules/schedule_a/"
        f"?sort=-contribution_receipt_amount&per_page=100"
        f"&two_year_transaction_period=2026&api_key={FEC_API_KEY}"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    raw = resp.json().get("results", [])
    finance = [
        {
            "contributor_name": r.get("contributor_name"),
            "contribution_receipt_amount": r.get("contribution_receipt_amount"),
            "committee_name": r.get("committee", {}).get("name") if r.get("committee") else None,
            "contribution_receipt_date": r.get("contribution_receipt_date"),
        }
        for r in raw
    ]
    save("finance.json", finance)
    status["finance"] = "success"
    print(f"[OK]   finance     — {len(finance)} records saved to data/finance.json")
except Exception as e:
    print(f"[FAIL] finance     — {e}")

# 3. Congress members
try:
    url = (
        "https://api.congress.gov/v3/member"
        f"?currentMember=true&limit=250&api_key={CONGRESS_API_KEY}"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    raw = resp.json().get("members", [])
    members = [
        {
            "name": m.get("name"),
            "party": m.get("partyName"),
            "state": m.get("state"),
            "district": m.get("district"),
            "chamber": m.get("terms", {}).get("item", [{}])[-1].get("chamber")
            if m.get("terms", {}).get("item")
            else None,
        }
        for m in raw
    ]
    save("members.json", members)
    status["members"] = "success"
    print(f"[OK]   members     — {len(members)} records saved to data/members.json")
except Exception as e:
    print(f"[FAIL] members     — {e}")

# 4. News headlines
try:
    url = (
        "https://newsapi.org/v2/top-headlines"
        f"?country=us&category=politics&pageSize=30&apiKey={NEWS_API_KEY}"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    raw = resp.json().get("articles", [])
    news = [
        {
            "title": a.get("title"),
            "source": a.get("source", {}).get("name"),
            "description": a.get("description"),
            "url": a.get("url"),
            "publishedAt": a.get("publishedAt"),
        }
        for a in raw
    ]
    save("news.json", news)
    status["news"] = "success"
    print(f"[OK]   news        — {len(news)} records saved to data/news.json")
except Exception as e:
    print(f"[FAIL] news        — {e}")

# Write last_updated.json
last_updated = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": status,
}
save("last_updated.json", last_updated)
print(f"\n[OK]   last_updated — data/last_updated.json written at {last_updated['timestamp']}")
