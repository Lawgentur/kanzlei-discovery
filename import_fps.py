import csv
import os
from datetime import datetime

MASTER_FILE = 'jobs_master.csv'
FPS_JOBS = [
    {"Titel": "Rechtsanwalt (m/w/d) Arbeitsrecht", "Standort": "Berlin", "Kanzlei": "FPS Fritze Wicke Seelig", "URL": "https://fps-law.de/de/karriere/jobs", "Datum": "2026-04-30"},
    {"Titel": "Anwaltsassistenz / Sachbearbeiter (m/w/d)", "Standort": "Frankfurt", "Kanzlei": "FPS Fritze Wicke Seelig", "URL": "https://fps-law.de/de/karriere/jobs", "Datum": "2026-04-30"},
    {"Titel": "Rechtsanwalt (m/w/d) Vergabe-, Beihilfe- und Förderrecht", "Standort": "Frankfurt", "Kanzlei": "FPS Fritze Wicke Seelig", "URL": "https://fps-law.de/de/karriere/jobs", "Datum": "2026-04-30"},
    {"Titel": "Rechtsanwalt (m/w/d) Restrukturierung und Insolvenzrecht", "Standort": "Frankfurt oder Düsseldorf", "Kanzlei": "FPS Fritze Wicke Seelig", "URL": "https://fps-law.de/de/karriere/jobs", "Datum": "2026-04-30"},
    {"Titel": "Mitarbeiter (m/w/d) Poststelle in Teilzeit", "Standort": "Berlin", "Kanzlei": "FPS Fritze Wicke Seelig", "URL": "https://fps-law.de/de/karriere/jobs", "Datum": "2026-04-30"},
    {"Titel": "Mitarbeiter (m/w/d) Nachlassverwaltung", "Standort": "Berlin", "Kanzlei": "FPS Fritze Wicke Seelig", "URL": "https://fps-law.de/de/karriere/jobs", "Datum": "2026-04-30"},
    {"Titel": "Notarfachangestellte (m/w/d)", "Standort": "Berlin", "Kanzlei": "FPS Fritze Wicke Seelig", "URL": "https://fps-law.de/de/karriere/jobs", "Datum": "2026-04-30"},
    {"Titel": "Datenschutzkoordinator (m/w/d)", "Standort": "Berlin", "Kanzlei": "FPS Fritze Wicke Seelig", "URL": "https://fps-law.de/de/karriere/jobs", "Datum": "2026-04-30"},
    {"Titel": "Praktikantenprogramm FPS in Practice - Herbst 2026", "Standort": "Frankfurt", "Kanzlei": "FPS Fritze Wicke Seelig", "URL": "https://fps-law.de/de/karriere/jobs", "Datum": "2026-04-30"},
    {"Titel": "Referendare (m/w/d) für alle Rechtsbereiche", "Standort": "München", "Kanzlei": "FPS Fritze Wicke Seelig", "URL": "https://fps-law.de/de/karriere/jobs", "Datum": "2026-04-30"},
    {"Titel": "Referendare (m/w/d) für alle Rechtsbereiche", "Standort": "Hamburg", "Kanzlei": "FPS Fritze Wicke Seelig", "URL": "https://fps-law.de/de/karriere/jobs", "Datum": "2026-04-30"},
    {"Titel": "Referendare (m/w/d) für alle Rechtsbereiche", "Standort": "Düsseldorf", "Kanzlei": "FPS Fritze Wicke Seelig", "URL": "https://fps-law.de/de/karriere/jobs", "Datum": "2026-04-30"},
    {"Titel": "Referendare (m/w/d) für alle Rechtsbereiche", "Standort": "Frankfurt", "Kanzlei": "FPS Fritze Wicke Seelig", "URL": "https://fps-law.de/de/karriere/jobs", "Datum": "2026-04-30"},
    {"Titel": "Referendare (m/w/d) für alle Rechtsbereiche", "Standort": "Berlin", "Kanzlei": "FPS Fritze Wicke Seelig", "URL": "https://fps-law.de/de/karriere/jobs", "Datum": "2026-04-30"}
]

def import_jobs():
    today = datetime.now().strftime("%Y-%m-%d")
    with open(MASTER_FILE, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        for job in FPS_JOBS:
            writer.writerow([job["Kanzlei"], job["Titel"], job["Standort"], job["URL"], today])
    print(f"Import abgeschlossen: {len(FPS_JOBS)} Jobs von FPS hinzugefügt.")

if __name__ == "__main__":
    import_jobs()
