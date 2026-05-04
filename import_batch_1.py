import csv
import os
from datetime import datetime

MASTER_FILE = 'jobs_master.csv'
today = datetime.now().strftime("%Y-%m-%d")

NEW_JOBS = [
    # BRP Renaud (Kanzlei 7)
    {"Kanzlei": "BRP RENAUD", "Titel": "Auszubildende (m/w/d) zum Rechtsanwaltsfachangestellten", "Standort": "Stuttgart", "URL": "https://brp.de/karriere/stellenangebote/"},
    {"Kanzlei": "BRP RENAUD", "Titel": "Patentanwaltsfachangestellte/r (m/w/d)", "Standort": "Stuttgart", "URL": "https://brp.de/karriere/stellenangebote/"},
    {"Kanzlei": "BRP RENAUD", "Titel": "Rechtsanwältin/Rechtsanwalt (m/w/d) Gesellschaftsrecht", "Standort": "Frankfurt", "URL": "https://brp.de/karriere/stellenangebote/"},
    {"Kanzlei": "BRP RENAUD", "Titel": "Rechtsanwältin/Rechtsanwalt (m/w/d) Gesellschaftsrecht / M&A", "Standort": "Stuttgart", "URL": "https://brp.de/karriere/stellenangebote/"},
    {"Kanzlei": "BRP RENAUD", "Titel": "Rechtsanwaltsfachangestellte (m/w/d) Familien - und Erbrecht", "Standort": "Stuttgart", "URL": "https://brp.de/karriere/stellenangebote/"},
    {"Kanzlei": "BRP RENAUD", "Titel": "Rechtsanwaltsfachangestellte / Sekretariat / Assistenz (m/w/d)", "Standort": "Frankfurt", "URL": "https://brp.de/karriere/stellenangebote/"},
    
    # SZA Schilling, Zutt & Anschütz (Kanzlei 9)
    {"Kanzlei": "SZA Schilling, Zutt & Anschütz", "Titel": "(Senior) Associate (m/w/d) Restrukturierung und Insolvenzrecht", "Standort": "München/Frankfurt/Mannheim", "URL": "https://www.sza.de/de/karriere/offene-stellen"},
    {"Kanzlei": "SZA Schilling, Zutt & Anschütz", "Titel": "Associate (m/w/d) Immobilien und Bauen", "Standort": "Frankfurt/Mannheim", "URL": "https://www.sza.de/de/karriere/offene-stellen"},
    {"Kanzlei": "SZA Schilling, Zutt & Anschütz", "Titel": "Referendariat", "Standort": "Frankfurt/Mannheim/München/Brüssel", "URL": "https://www.sza.de/de/karriere/offene-stellen"},
    {"Kanzlei": "SZA Schilling, Zutt & Anschütz", "Titel": "Wissenschaftliche Mitarbeiter (m/w/d)", "Standort": "Mannheim/Frankfurt/München", "URL": "https://www.sza.de/de/karriere/offene-stellen"}
]

def import_jobs():
    added_count = 0
    with open(MASTER_FILE, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        for job in NEW_JOBS:
            writer.writerow([job["Kanzlei"], job["Titel"], job["Standort"], job["URL"], today])
            added_count += 1
    print(f"Import abgeschlossen: {added_count} Jobs hinzugefügt.")

if __name__ == "__main__":
    import_jobs()
