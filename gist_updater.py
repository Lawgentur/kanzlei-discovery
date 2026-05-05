import json
import os
import csv
from datetime import datetime
import urllib.request
import urllib.parse

# Konfiguration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GIST_ID_FILE = "state/gist_id.txt"
CSV_FILE = "jobs_master.csv"
FILENAME = "jobs_master_public.csv"

def update_gist():
    if not os.path.exists(CSV_FILE):
        print(f"Fehler: {CSV_FILE} nicht gefunden.")
        return

    # CSV Inhalt lesen
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }

    gist_id = None
    if os.path.exists(GIST_ID_FILE):
        with open(GIST_ID_FILE, 'r') as f:
            gist_id = f.read().strip()

    payload = {
        "description": f"Daily Law Firm Jobs Export (Updated: {datetime.now().isoformat()})",
        "public": True,
        "files": {
            FILENAME: {
                "content": content
            }
        }
    }

    data = json.dumps(payload).encode('utf-8')
    
    try:
        if gist_id:
            # Update bestehendes Gist (PATCH via Method-Override oder Request-Objekt)
            url = f"https://api.github.com/gists/{gist_id}"
            req = urllib.request.Request(url, data=data, headers=headers, method='PATCH')
        else:
            # Erstelle neues Gist
            url = "https://api.github.com/gists"
            req = urllib.request.Request(url, data=data, headers=headers, method='POST')

        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode('utf-8')
            gist_data = json.loads(res_body)
            
            if not gist_id:
                gist_id = gist_data['id']
                os.makedirs("state", exist_ok=True)
                with open(GIST_ID_FILE, 'w') as f:
                    f.write(gist_id)

            raw_url = gist_data['files'][FILENAME]['raw_url']
            print(f"GIST_UPDATE_SUCCESS")
            print(f"Gist ID: {gist_id}")
            print(f"Raw URL: {raw_url}")
            return raw_url

    except Exception as e:
        print(f"GIST_UPDATE_ERROR: {e}")
        return None

if __name__ == "__main__":
    update_gist()
