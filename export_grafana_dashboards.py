import os
import json
import argparse
import urllib.request
import urllib.error
from base64 import b64encode
from datetime import datetime

GRAFANA_URL = "http://localhost:3000"
GRAFANA_USER = "admin"
GRAFANA_PASSWORD = "admin"
OUTPUT_DIR = "./grafana/dashboards"


def auth_header():
    token = b64encode(f"{GRAFANA_USER}:{GRAFANA_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def get(path):
    req = urllib.request.Request(f"{GRAFANA_URL}{path}", headers=auth_header())
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def list_dashboards():
    results = get("/api/search?type=dash-db&limit=500")
    return [{"uid": r["uid"], "title": r["title"], "folder": r.get("folderTitle", "General")} for r in results]


def export_dashboard(uid):
    data = get(f"/api/dashboards/uid/{uid}")
    dashboard = data["dashboard"]
    meta = data["meta"]
    return {
        "dashboard": dashboard,
        "folderId": meta.get("folderId", 0),
        "folderUid": meta.get("folderUid", ""),
        "overwrite": True,
    }


def safe_filename(title):
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip().replace(" ", "_").lower()


def run(watch=False, interval=300, flat=False):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    def export_all():
        try:
            dashboards = list_dashboards()
        except urllib.error.URLError as e:
            print(f"Cannot reach Grafana at {GRAFANA_URL}: {e}")
            return

        if not dashboards:
            print("No dashboards found.")
            return

        exported = []
        for db in dashboards:
            try:
                payload = export_dashboard(db["uid"])
                filename = f"{safe_filename(db['title'])}.json"
                filepath = os.path.join(OUTPUT_DIR, filename)
                out_obj = payload["dashboard"] if flat else payload
                with open(filepath, "w") as f:
                    json.dump(out_obj, f, indent=2)
                exported.append((db["title"], filepath))
            except Exception as e:
                print(f"  Failed to export '{db['title']}': {e}")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] Exported {len(exported)}/{len(dashboards)} dashboards → {OUTPUT_DIR}/")
        for title, path in exported:
            print(f"  {title:40s}  →  {path}")

    export_all()

    if watch:
        import time
        print(f"\nWatching — re-exporting every {interval}s. Ctrl+C to stop.")
        while True:
            time.sleep(interval)
            export_all()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export all Grafana dashboards as JSON files.")
    parser.add_argument("--url",      default=GRAFANA_URL,      help="Grafana base URL")
    parser.add_argument("--user",     default=GRAFANA_USER,     help="Grafana username")
    parser.add_argument("--password", default=GRAFANA_PASSWORD, help="Grafana password")
    parser.add_argument("--out",      default=OUTPUT_DIR,       help="Output directory")
    parser.add_argument("--watch",    action="store_true",       help="Re-export on interval")
    parser.add_argument("--interval", type=int, default=300,    help="Watch interval in seconds (default 300)")
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Write inner dashboard JSON only (for grafana/provisioning file dashboards)",
    )
    args = parser.parse_args()

    GRAFANA_URL      = args.url
    GRAFANA_USER     = args.user
    GRAFANA_PASSWORD = args.password
    OUTPUT_DIR       = args.out

    run(watch=args.watch, interval=args.interval, flat=args.flat)
