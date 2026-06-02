import csv
import os
from datetime import datetime

def get_master_data(path):
    master_keys = set()
    if not os.path.exists(path):
        return master_keys
    
    with open(path, 'r', encoding='utf-8') as f:
        # Wir lesen die Datei Zeile für Zeile, da kein Header garantiert ist
        # Falls die Datei leer ist oder nur Newlines enthält
        content = f.read().strip()
        if not content:
            return master_keys
        
        f.seek(0)
        # Wir versuchen zu raten, ob es einen Header gibt. 
        # Da wir wissen, dass die Datei existiert und Daten hat, nutzen wir DictReader
        # Wenn der Header fehlt, nutzen wir eine manuelle Spaltenzuordnung
        sample = f.read(1024)
        f.seek(0)
        
        if 'Kanzlei,Jobtitel,Location' in sample or 'Kanzlei' in sample:
            reader = csv.DictReader(f)
            try:
                for row in reader:
                    if not row.get('Jobtitel') or not row.get('Kanzlei'):
                        continue
                    key = (row['Jobtitel'].strip().lower(), 
                           row['Kanzlei'].strip().lower(), 
                           row['Location'].strip().lower())
                    master_keys.add(key)
            except KeyError:
                # Fallback: Manuelle Indizes wenn Header-Namen nicht passen
                f.seek(0)
                reader = csv.reader(f)
                next(reader) # Header überspringen
                for row in reader:
                    if len(row) >= 3:
                        key = (row[1].strip().lower(), row[0].strip().lower(), row[2].strip().lower())
                        master_keys.add(key)
        else:
            # Kein Header erkannt, wir nehmen an: Kanzlei, Jobtitel, Location, Link, Datum, Email
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 3:
                    key = (row[1].strip().lower(), row[0].strip().lower(), row[2].strip().lower())
                    master_keys.add(key)
    return master_keys

def import_stepstone_csv(csv_path, master_path):
    master_keys = get_master_data(master_path)
    today = datetime.now().strftime('%Y-%m-%d')
    new_entries = []
    
    if not os.path.exists(csv_path):
        print(f"Datei {csv_path} nicht gefunden.")
        return

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get('Job_Titel', '').strip()
            company = row.get('Name_des_Unternehmens', '').strip()
            location = row.get('Standort', '').strip()
            url = row.get('Titel_url', '').strip()
            # Datum parsen (2026-04-25T16:03:05+02:00 -> 2026-04-25)
            published_raw = row.get('Erscheinen', today).strip()
            published = published_raw.split('T')[0] if 'T' in published_raw else published_raw
            
            if not title or not company:
                continue

            key = (title.lower(), company.lower(), location.lower())
            
            if key not in master_keys:
                new_entries.append({
                    'Kanzlei': company,
                    'Jobtitel': title,
                    'Location': location,
                    'Link': url,
                    'Erstes_Funddatum': published,
                    'Zuletzt_Gesehen': today,
                    'Email': ''
                })
                master_keys.add(key)

    if new_entries:
        file_exists = os.path.exists(master_path)
        fieldnames = ['Kanzlei', 'Jobtitel', 'Location', 'Link', 'Erstes_Funddatum', 'Zuletzt_Gesehen', 'Email']
        
        # Sicherstellen, dass wir an das Ende anfügen und Umlaute korrekt schreiben
        with open(master_path, 'a', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            # Wenn Datei leer oder neu, Header schreiben
            if not file_exists or os.path.getsize(master_path) == 0:
                writer.writeheader()
            writer.writerows(new_entries)
        print(f"IMPORT_SUCCESS: {len(new_entries)} neue Jobs importiert.")
    else:
        print("IMPORT_NONE: Keine neuen Jobs gefunden.")

def import_indeed_csv(csv_path, master_path):
    master_keys = get_master_data(master_path)
    today = datetime.now().strftime('%Y-%m-%d')
    new_entries = []
    
    if not os.path.exists(csv_path):
        print(f"Datei {csv_path} nicht gefunden.")
        return

    with open(csv_path, 'r', encoding='utf-8') as f:
        # Indeed Spalten: Job_Title, Job_URL, Location, Company_Name, Posted_Date
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get('Job_Title', '').strip()
            company = row.get('Company_Name', '').strip()
            location = row.get('Location', '').strip()
            url = row.get('Job_URL', '').strip()
            published_raw = row.get('Posted_Date', today).strip()
            published = published_raw.split('T')[0] if 'T' in published_raw else published_raw
            
            if not title or not company:
                continue

            key = (title.lower(), company.lower(), location.lower())
            
            if key not in master_keys:
                new_entries.append({
                    'Kanzlei': company,
                    'Jobtitel': title,
                    'Location': location,
                    'Link': url,
                    'Erstes_Funddatum': published,
                    'Zuletzt_Gesehen': today,
                    'Email': ''
                })
                master_keys.add(key)

    if new_entries:
        file_exists = os.path.exists(master_path)
        fieldnames = ['Kanzlei', 'Jobtitel', 'Location', 'Link', 'Erstes_Funddatum', 'Zuletzt_Gesehen', 'Email']
        with open(master_path, 'a', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists or os.path.getsize(master_path) == 0:
                writer.writeheader()
            writer.writerows(new_entries)
        print(f"IMPORT_SUCCESS_INDEED: {len(new_entries)} neue Jobs importiert.")
    else:
        print("IMPORT_NONE_INDEED: Keine neuen Jobs gefunden.")

if __name__ == "__main__":
    import_stepstone_csv('stepstone_import.csv', 'jobs_master.csv')
    import_indeed_csv('indeed_import.csv', 'jobs_master.csv')
