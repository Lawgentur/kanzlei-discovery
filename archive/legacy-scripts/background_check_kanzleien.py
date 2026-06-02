import csv
import re
import urllib.request
import urllib.error
import os
import time

INPUT_FILE = 'alte_kanzleien_raw.csv'
OUTPUT_FILE = 'alte_kanzleien_final_report.csv'

def clean_url(raw_url):
    if not raw_url: return None
    urls = re.findall(r'https?://[^\s,]+', str(raw_url))
    if urls:
        return urls[0].strip('", ')
    domain_match = re.search(r'([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}', str(raw_url), re.I)
    if domain_match:
        return "https://" + domain_match.group(0)
    return None

def check_url(url):
    if not url:
        return "Fehler: Keine URL", None
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return "Aktiv/Gefunden", response.geturl()
    except urllib.error.HTTPError as e:
        return f"Fehler: {e.code}", url
    except Exception:
        return "Fehler: Nicht erreichbar", url

def run_resumable_check():
    processed_names = set()
    file_exists = os.path.exists(OUTPUT_FILE)
    
    if file_exists:
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                processed_names.add(row['Kanzleiname'])
    
    mode = 'a' if file_exists else 'w'
    with open(OUTPUT_FILE, mode, encoding='utf-8', newline='') as f:
        fieldnames = ['Kanzleiname', 'Status', 'Validierte_URL', 'Original_Input']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        
        with open(INPUT_FILE, 'r', encoding='utf-8') as f_in:
            reader = csv.DictReader(f_in)
            count = len(processed_names)
            for row in reader:
                name = row.get('Kanzleiname', 'Unbekannt')
                if name in processed_names:
                    continue
                    
                raw_url = row.get('URL', '')
                cleaned = clean_url(raw_url)
                status, final_url = check_url(cleaned)
                writer.writerow({
                    'Kanzleiname': name,
                    'Status': status,
                    'Validierte_URL': final_url or cleaned,
                    'Original_Input': raw_url
                })
                count += 1
                if count % 20 == 0:
                    print(f"Progress: {count} processed...")
                    f.flush()
                # Tiny sleep to avoid aggressive hammering
                time.sleep(0.1)

    print("FINISHED_PROCESSING")

if __name__ == "__main__":
    run_resumable_check()
