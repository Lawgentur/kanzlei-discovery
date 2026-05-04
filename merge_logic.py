import csv
import os
import re

# Pfade
TARGET_FILE = 'target_firms_full.csv'
IMPORT_FILE = 'temp_import.csv'
OUTPUT_FILE = 'target_firms_updated.csv'

def normalize_domain(url):
    if not url: return ""
    url = url.lower().strip()
    # Protokoll und www entfernen
    url = re.sub(r'https?://(www\.)?', '', url)
    # Nur die Basis-Domain nehmen (bis zum ersten /)
    domain = url.split('/')[0]
    return domain

def merge_lists():
    # 1. Bestehende Liste laden
    firms = []
    with open(TARGET_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if 'Jobboard_URL' not in fieldnames:
            fieldnames.append('Jobboard_URL')
        firms = list(reader)

    # Index erstellen (Domain -> Firm)
    domain_to_firm = {f['Domainname des Unternehmens'].lower().strip(): f for f in firms}

    # 2. Neue Liste laden und zuordnen
    matched_count = 0
    with open(IMPORT_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            kanzlei = row['kanzlei']
            url = row['url']
            
            domain = normalize_domain(url)
            if not domain: continue

            # Suche nach Treffer in der Domain-Liste
            matched = False
            if domain in domain_to_firm:
                domain_to_firm[domain]['Jobboard_URL'] = url
                matched = True
            else:
                # Suche nach Teil-Übereinstimmungen (z.B. "wfw.com" in "wfw.com/careers")
                for d in domain_to_firm:
                    if d in domain or domain in d:
                        domain_to_firm[d]['Jobboard_URL'] = url
                        matched = True
                        break
            
            if matched:
                matched_count += 1

    # 3. Speichern
    with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(firms)

    print(f"Merge abgeschlossen.")
    print(f"Treffer über Domain: {matched_count}")
    print(f"Neue Datei erstellt: {OUTPUT_FILE}")

if __name__ == "__main__":
    merge_lists()
