import csv
import os
from datetime import datetime

# Konfiguration
MASTER_FILE = 'jobs_master.csv'
LUTHER_JOBS = [
    {"Titel": "Assistenz, Sekretärin, Rechtsanwaltsfachangestellte (m/w/d)", "Standort": "München", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2025-050.html"},
    {"Titel": "Auszubildende (m/w/d) zur Rechtsanwaltsfachangestellten", "Standort": "Hamburg", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2025-090.html"},
    {"Titel": "Hotelfachmann / Gastronomie-Fachkraft (m/w/d)", "Standort": "Essen", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2026-025.html"},
    {"Titel": "IT Application Specialist (m/w/d) - ERP & Data Analytics", "Standort": "Köln, Leipzig", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2025-104.html"},
    {"Titel": "IT-Support (m/w/d) – First-Level-Support", "Standort": "Berlin, Stuttgart", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2025-070.html"},
    {"Titel": "Notarfachangestellte/ Notarfachwirtin / Notarfachreferentin (m/w/d)", "Standort": "Essen", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2024-003.html"},
    {"Titel": "Rechtsanwalt / Associate (m/w/d) Arbeitsrecht", "Standort": "Frankfurt am Main", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2025-072.html"},
    {"Titel": "Rechtsanwalt / Associate (m/w/d) Arbeitsrecht", "Standort": "Hamburg", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2026-029.html"},
    {"Titel": "Rechtsanwalt (m/w/d) Arbeitsrecht", "Standort": "Köln", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2026-019.html"},
    {"Titel": "Rechtsanwalt (m/w/d) Arbeitsrecht", "Standort": "Stuttgart", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2026-022.html"},
    {"Titel": "Rechtsanwalt (m/w/d) Arbeitsrecht mit Berufserfahrung", "Standort": "Hamburg", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2026-017.html"},
    {"Titel": "Rechtsanwalt (m/w/d) Arbeitsrecht mit Berufserfahrung", "Standort": "Frankfurt am Main", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2026-015.html"},
    {"Titel": "Rechtsanwalt (m/w/d) Corporate / M&A", "Standort": "Leipzig", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2025-067.html"},
    {"Titel": "Rechtsanwalt (m/w/d) Corporate / M&A / Private Equity / Venture Capital", "Standort": "München", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2025-055.html"},
    {"Titel": "Rechtsanwalt (m/w/d) Corporate / M&A mit Berufserfahrung", "Standort": "Leipzig", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2025-054.html"},
    {"Titel": "Rechtsanwalt (m/w/d) Energierecht", "Standort": "Berlin, Düsseldorf", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2026-032.html"},
    {"Titel": "Rechtsanwalt (m/w/d) Medizinrecht / Health Care mit Berufserfahrung", "Standort": "Berlin", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2026-014.html"},
    {"Titel": "Rechtsanwalt (m/w/d) öffentliches Bau- und Wirtschaftsrecht mit Berufserfahrung", "Standort": "Essen", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2026-028.html"},
    {"Titel": "Rechtsanwalt (m/w/d) Privates Bau- und Architektenrecht", "Standort": "Essen", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2024-062.html"},
    {"Titel": "Rechtsanwalt (m/w/d) White Collar – Compliance – Investigations", "Standort": "München", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2025-084.html"},
    {"Titel": "Rechtsanwalt (w/m/d) Öffentliches Recht / Umweltrecht", "Standort": "Leipzig", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2026-011.html"},
    {"Titel": "Rechtsanwaltsfachangestellte, Assistenz, Sekretärin (m/w/d)", "Standort": "Hannover", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2025-064.html"},
    {"Titel": "Rechtsanwaltsfachangestellte (m/w/d)", "Standort": "Köln", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2026-013.html"},
    {"Titel": "Rechtsanwaltsfachangestellte (m/w/d)", "Standort": "München", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2025-065.html"},
    {"Titel": "Rechtsanwaltsfachangestellte (m/w/d) Vollzeit / Vollzeit", "Standort": "Hamburg", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2026-030.html"},
    {"Titel": "Rechtsanwalts- und Notarfachangestellte/ Notarfachwirtin / Notarfachreferentin (m/w/d)", "Standort": "Berlin", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2025-034.html"},
    {"Titel": "Referendar (Anwalts-/Wahlstation) (m/w/d) Berlin", "Standort": "Berlin", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2024-023.html"},
    {"Titel": "Referendar (Anwalts-/Wahlstation) (m/w/d) Brüssel", "Standort": "Brüssel", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2024-040.html"},
    {"Titel": "Referendar (Anwalts-/Wahlstation) (m/w/d) Düsseldorf", "Standort": "Düsseldorf", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2024-021.html"},
    {"Titel": "Referendar (Anwalts-/Wahlstation) (m/w/d) Essen", "Standort": "Essen", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2024-022.html"},
    {"Titel": "Referendar (Anwalts-/Wahlstation) (m/w/d) Frankfurt", "Standort": "Frankfurt am Main", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2024-024.html"},
    {"Titel": "Referendar (Anwalts-/Wahlstation) (m/w/d) Hamburg", "Standort": "Hamburg", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2024-025.html"},
    {"Titel": "Referendar (Anwalts-/Wahlstation) (m/w/d) Hannover", "Standort": "Hannover", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2024-026.html"},
    {"Titel": "Referendar (Anwalts-/Wahlstation) (m/w/d) Köln", "Standort": "Köln", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2024-019.html"},
    {"Titel": "Referendar (Anwalts-/Wahlstation) (m/w/d) Leipzig", "Standort": "Leipzig", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2024-027.html"},
    {"Titel": "Referendar (Anwalts-/Wahlstation) (m/w/d) München", "Standort": "München", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2024-028.html"},
    {"Titel": "Referendar (Anwalts-/Wahlstation) (m/w/d) Stuttgart", "Standort": "Stuttgart", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2024-029.html"},
    {"Titel": "Referent Business Development (m/w/d)", "Standort": "Köln", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2025-077.html"},
    {"Titel": "Referent Business Development | Legal Submissions (m/w/d)", "Standort": "Köln", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2025-082.html"},
    {"Titel": "Wissenschaftlicher Mitarbeiter (m/w/d) Arbeitsrecht Essen", "Standort": "Essen", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2026-031.html"},
    {"Titel": "Wissenschaftlicher Mitarbeiter (m/w/d) Corporate / M&A Leipzig", "Standort": "Leipzig", "Kanzlei": "Luther Rechtsanwaltsgesellschaft mbH", "URL": "https://jobs.luther-lawfirm.com/jobportal/luther/viewAusschreibung/2026-021.html"}
]

def import_jobs():
    today = datetime.now().strftime("%Y-%m-%d")
    added_count = 0
    # Wir nutzen das csv-Modul, um saubere Quoting-Regeln einzuhalten
    with open(MASTER_FILE, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        for job in LUTHER_JOBS:
            writer.writerow([job["Kanzlei"], job["Titel"], job["Standort"], job["URL"], today])
            added_count += 1
    print(f"Import abgeschlossen: {added_count} neue Jobs von Luther hinzugefügt.")

if __name__ == "__main__":
    import_jobs()
