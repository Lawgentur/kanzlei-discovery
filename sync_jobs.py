import pandas as pd
import os
import json
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

# --- KONFIGURATION ---
# Ersetze dies durch deine echte Folder ID aus der Google Drive URL
FOLDER_ID = '197A_upMwFMjERVkMlEIytRNIJidjMYxo' # Hier deine Ordner-ID eintragen
MASTER_FILE = 'jobs_master.csv'
DAYS_UNTIL_DELETION = 30 

# Spalten-Mapping für verschiedene Quellen (Stepstone & Indeed)
MAPPINGS = {
    'stepstone': {
        'Job_Titel': 'Titel', 
        'Titel_url': 'Link', 
        'Name_des_Unternehmens': 'Kanzlei', 
        'Standort': 'Stadt'
    },
    'indeed': {
        'Job_Title': 'Titel', 
        'Job_URL': 'Link', 
        'Company_Name': 'Kanzlei', 
        'Location': 'Stadt'
    }
}

def get_drive_service():
    """Authentifiziert sich mit dem Service Account Key aus den GitHub Secrets."""
    info = json.loads(os.environ['GCP_SERVICE_ACCOUNT_KEY'])
    creds = service_account.Credentials.from_service_account_info(info)
    return build('drive', 'v3', credentials=creds)

def normalize_dataframe(df):
    """Benennt Spalten je nach Quelle in das Master-Format um."""
    cols = df.columns.tolist()
    if 'Titel_url' in cols:
        return df.rename(columns=MAPPINGS['stepstone'])
    if 'Job_URL' in cols:
        return df.rename(columns=MAPPINGS['indeed'])
    return df

def main():
    service = get_drive_service()
    today = datetime.now().strftime('%Y-%m-%d')
    cols_needed = ['Titel', 'Link', 'Kanzlei', 'Stadt', 'first_seen', 'last_seen']
    
    # 1. Bestehende Master-Datei laden
    if os.path.exists(MASTER_FILE):
        try:
            # Lade CSV, überspringe kaputte Zeilen, nutze Quoting
            df_master = pd.read_csv(MASTER_FILE, on_bad_lines='skip', engine='python')
            # Sicherstellen, dass alle Spalten da sind
            for c in cols_needed:
                if c not in df_master.columns:
                    df_master[c] = ""
            df_master['last_seen'] = pd.to_datetime(df_master['last_seen'], errors='coerce')
        except Exception as e:
            print(f"Fehler beim Laden der CSV: {e}")
            df_master = pd.DataFrame(columns=cols_needed)
    else:
        df_master = pd.DataFrame(columns=cols_needed)

    # 2. Dateien aus Google Drive abrufen 
    # WICHTIG: Die webseiten_jobsuche_master.xlsx wird hier explizit ausgeschlossen!
    query = f"'{FOLDER_ID}' in parents and name contains '.xlsx' and name != 'webseiten_jobsuche_master.xlsx'"
    
    results = service.files().list(
        q=query, 
        fields="files(id, name)"
    ).execute()
    
    items = results.get('files', [])

    if not items:
        print("Keine neuen Dateien zum Mergen gefunden.")
    else:
        new_dfs = []
        for item in items:
            print(f"Verarbeite Datei aus Drive: {item['name']}")
            request = service.files().get_media(fileId=item['id'])
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            
            # Excel laden und normalisieren
            df_raw = pd.read_excel(io.BytesIO(fh.getvalue()))
            df_norm = normalize_dataframe(df_raw)
            new_dfs.append(df_norm)

        if new_dfs:
            df_incoming = pd.concat(new_dfs, ignore_index=True)

            # 3. Logik: Mergen & Deduplizieren (über Titel, Kanzlei, Stadt)
            for _, row in df_incoming.iterrows():
                titel = str(row.get('Titel', '')).strip()
                link = str(row.get('Link', '')).strip()
                kanzlei = str(row.get('Kanzlei', '')).strip()
                stadt = str(row.get('Stadt', '')).strip()
                
                if not titel or len(titel) < 3:
                    continue

                # Abgleich: Existiert dieser Job (Titel+Kanzlei+Stadt) bereits?
                mask = (df_master['Titel'] == titel) & \
                       (df_master['Kanzlei'] == kanzlei) & \
                       (df_master['Stadt'] == stadt)
                
                if mask.any():
                    # Vorhanden: Datum aktualisieren
                    df_master.loc[mask, 'last_seen'] = today
                    # Falls der Link sich geändert hat (z.B. neue ID), Link aktualisieren
                    if link:
                        df_master.loc[mask, 'Link'] = link
                else:
                    # Neu: Hinzufügen
                    new_entry = {
                        'Titel': titel,
                        'Link': link,
                        'Kanzlei': kanzlei,
                        'Stadt': stadt,
                        'first_seen': today,
                        'last_seen': today
                    }
                    df_master = pd.concat([df_master, pd.DataFrame([new_entry])], ignore_index=True)

    # 4. Alte Jobs bereinigen (Cutoff)
    cutoff_date = datetime.now() - timedelta(days=DAYS_UNTIL_DELETION)
    # Nur Jobs behalten, die innerhalb der Frist gesehen wurden
    df_master = df_master[(pd.to_datetime(df_master['last_seen']) >= cutoff_date) | (df_master['last_seen'].isna())]

    # 5. Speichern mit Anführungszeichen für alle Felder (CSV-Stabilität)
    df_master[cols_needed].to_csv(MASTER_FILE, index=False, quoting=1, encoding='utf-8')
    print(f"Synchronisierung erfolgreich beendet. Master hat {len(df_master)} Einträge.")

if __name__ == "__main__":
    main()
