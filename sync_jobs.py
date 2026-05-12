import pandas as pd
import os
import json
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

# --- KONFIGURATION ---
FOLDER_ID = 'DEINE_FOLDER_ID_HIER_EINTRAGEN'
MASTER_FILE = 'jobs_master.csv'
ID_COLUMN = 'Link'  # Wir vereinheitlichen alles auf 'Link'
DAYS_UNTIL_DELETION = 21

# Spalten-Mapping für die verschiedenen Quellen
MAPPINGS = {
    'stepstone': {
        'Job_Titel': 'Titel',
        'Titel_url': 'Link',
        'Name_des_Unternehmens': 'Kanzlei',
        'Standort': 'Stadt',
        'Erscheinen': 'funddatum_original'
    },
    'indeed': {
        'Job_Title': 'Titel',
        'Job_URL': 'Link',
        'Company_Name': 'Kanzlei',
        'Location': 'Stadt',
        'Valid_Through': 'funddatum_original'
    }
}

def get_drive_service():
    info = json.loads(os.environ['GCP_SERVICE_ACCOUNT_KEY'])
    creds = service_account.Credentials.from_service_account_info(info)
    return build('drive', 'v3', credentials=creds)

def normalize_dataframe(df):
    """Benennt Spalten basierend auf ihrem Inhalt um."""
    cols = df.columns.tolist()
    
    # Prüfen, ob es Stepstone ist
    if 'Titel_url' in cols:
        return df.rename(columns=MAPPINGS['stepstone'])
    
    # Prüfen, ob es Indeed ist
    if 'Job_URL' in cols:
        return df.rename(columns=MAPPINGS['indeed'])
    
    return df

def main():
    service = get_drive_service()
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 1. Master-Datei laden
    if os.path.exists(MASTER_FILE):
        try:
            df_master = pd.read_csv(MASTER_FILE, on_bad_lines='warn', engine='python')
            df_master['last_seen'] = pd.to_datetime(df_master['last_seen'], errors='coerce')
        except Exception as e:
            print(f"Fehler beim Laden der CSV: {e}")
            df_master = pd.DataFrame(columns=['Titel', 'Link', 'Kanzlei', 'Stadt', 'first_seen', 'last_seen'])
    else:
        df_master = pd.DataFrame(columns=['Titel', 'Link', 'Kanzlei', 'Stadt', 'first_seen', 'last_seen'])

    # 2. Dateien aus Google Drive abrufen
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and name contains '.xlsx'",
        fields="files(id, name)").execute()
    items = results.get('files', [])

    if not items:
        print("Keine neuen Dateien im Drive gefunden.")
        # Wir fahren trotzdem fort, um alte Jobs zu löschen
    else:
        new_data_frames = []
        for item in items:
            print(f"Verarbeite Datei: {item['name']}")
            request = service.files().get_media(fileId=item['id'])
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            
            df_raw = pd.read_excel(io.BytesIO(fh.getvalue()))
            df_norm = normalize_dataframe(df_raw)
            new_data_frames.append(df_norm)
            
            # WICHTIG: Nach dem Testen kannst du hier die Zeile zum Löschen der Datei im Drive aktivieren:
            # service.files().delete(fileId=item['id']).execute()

        if new_data_frames:
            df_incoming = pd.concat(new_data_frames, ignore_index=True)

            # 3. Logik: Mergen & Deduplizieren
            for _, row in df_incoming.iterrows():
                url = row.get('Link')
                if not url or pd.isna(url): continue
                
                if url in df_master['Link'].values:
                    # Update: Job existiert bereits
                    df_master.loc[df_master['Link'] == url, 'last_seen'] = today
                else:
                    # Insert: Neuer Job
                    new_entry = {
                        'Titel': row.get('Titel'),
                        'Link': url,
                        'Kanzlei': row.get('Kanzlei'),
                        'Stadt': row.get('Stadt'),
                        'first_seen': today,
                        'last_seen': today
                    }
                    df_master = pd.concat([df_master, pd.DataFrame([new_entry])], ignore_index=True)

    # 4. Alte Jobs bereinigen
    cutoff_date = datetime.now() - timedelta(days=DAYS_UNTIL_DELETION)
    df_master = df_master[pd.to_datetime(df_master['last_seen']) > cutoff_date]

    # 5. Speichern
    df_master.to_csv(MASTER_FILE, index=False)
    print(f"Synchronisierung abgeschlossen. Master hat jetzt {len(df_master)} Jobs.")

if __name__ == "__main__":
    main()
