import csv
import re
import urllib.request
import urllib.error

INPUT_FILE = 'alte_kanzleien_raw.csv'
OUTPUT_FILE = 'alte_kanzleien_checked.csv'

def clean_url(raw_url):
    urls = re.findall(r'https?://[^\s,]+', raw_url)
    if urls:
        return urls[0].strip('", ')
    domain_match = re.search(r'([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}', raw_url, re.I)
    if domain_match:
        return "https://" + domain_match.group(0)
    return None

def check_url(url):
    if not url:
        return "Fehler: Keine URL", None
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return "Aktiv/Gefunden", response.geturl()
    except urllib.error.HTTPError as e:
        return f"Fehler: {e.code}", url
    except Exception:
        return "Fehler: Nicht erreichbar", url

def process():
    # Only process first 10 for status update to avoid long wait
    results = []
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            if count >= 10: break
            name = row['Kanzleiname']
            raw_url = row['URL']
            cleaned = clean_url(raw_url)
            status, final_url = check_url(cleaned)
            results.append({
                'Kanzleiname': name,
                'Status': status,
                'Gereinigte_URL': final_url or cleaned,
                'Original_URL': raw_url
            })
            print(f"Processed: {name} -> {status}")
            count += 1
    
    # Rest will be done in background if needed, but for now show I started


if __name__ == "__main__":
    process()
