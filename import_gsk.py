import csv
import os
import json
from datetime import datetime

MASTER_FILE = 'jobs_master.csv'

# Manuelle Extraktion aus den API-Antworten
GSK_STANDORTE = {
    21: "Berlin", 33: "Frankfurt am Main", 28: "Hamburg", 30: "Heidelberg", 
    27: "München", 31: "Mönchengladbach", 29: "London"
}

GSK_JOBS_RAW = [
    {"title": "Rechtsanwalt (m/w/d) im Bereich öffentliches Baurecht/Immobilien-Projektentwicklung", "url": "https://career.gsk.de/stellenangebote/rechtsanwalt-m-w-d-im-bereich-oeffentliches-baurecht-immobilien-projektentwicklung/", "standort_ids": [21]},
    {"title": "GSK INSIGHT – Praktikantenprogramm", "url": "https://career.gsk.de/stellenangebote/gsk-insight-praktikantenprogramm/", "standort_ids": [21, 33, 28, 30, 27]},
    {"title": "Legaltech Softwareentwickler (m/w/d)", "url": "https://career.gsk.de/stellenangebote/legaltech-softwareentwickler-m-w-d/", "standort_ids": [21, 31]}
]

def import_jobs():
    today = datetime.now().strftime("%Y-%m-%d")
    added_count = 0
    with open(MASTER_FILE, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        for job in GSK_JOBS_RAW:
            standorte = ", ".join([GSK_STANDORTE.get(sid, "Unbekannt") for sid in job["standort_ids"]])
            writer.writerow(["GSK Stockmann", job["title"], standorte, job["url"], today])
            added_count += 1
    print(f"Import abgeschlossen: {added_count} Jobs von GSK Stockmann hinzugefügt.")

if __name__ == "__main__":
    import_jobs()
