import csv
import os
from datetime import datetime

master_file = 'jobs_master.csv'
target_file = 'target_firms_full.csv'
output_file = f'media/jobs_weekly_{datetime.now().strftime("%Y-%m-%d")}.csv'

def perform_scrape():
    print(f"Scraping {target_file}...")
    
    # 1. Firmenliste laden
    firms = []
    with open(target_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        firms = list(reader)
        fieldnames_firms = reader.fieldnames

    # 2. Bestehende Jobs laden
    jobs = []
    if os.path.exists(master_file):
        with open(master_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            jobs = list(reader)

    # 3. Logik für jede Firma
    updated_firms = False
    for firm in firms:
        jobboard_url = firm.get('Jobboard_URL', '')
        main_domain = firm.get('Domainname des Unternehmens', '')

        if jobboard_url:
            # OPTION A: Direkt das Jobboard scannen
            # print(f"Scanning Jobboard: {jobboard_url}")
            pass
        else:
            # OPTION B: Auf Haupt-Domain suchen UND Jobboard_URL befüllen falls gefunden
            # print(f"Searching Career-Link on: {main_domain}")
            # Falls wir hier einen Link finden:
            # found_url = "https://..."
            # firm['Jobboard_URL'] = found_url
            # updated_firms = True
            pass

    # 4. Falls neue Jobboard-Links gefunden wurden, Firmenliste aktualisieren
    if updated_firms:
        with open(target_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames_firms)
            writer.writeheader()
            writer.writerows(firms)

    print("Updates complete.")
    
    # Create the download file
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        if jobs:
            writer = csv.DictWriter(f, fieldnames=jobs[0].keys())
            writer.writeheader()
            writer.writerows(jobs)
    
    print(f"MEDIA:{output_file}")

if __name__ == "__main__":
    perform_scrape()
