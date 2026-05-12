import pandas as pd
import os
import json
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

# --- KONFIGURATION ---
FOLDER_ID = '197A_upMwFMjERVkMlEIytRNIJidjMYxo' # <-- Deine Folder ID einsetzen!
MASTER_FILE = 'jobs_master.csv'
ID_COLUMN = 'Link' # Die URL als eindeutiger Identifikator
DAYS_UNTIL_DELETION = 14 # Jobs, die 2 Wochen nicht gesehen wurden, fliegen raus

def get_drive_service():
    info = json.loads(os.environ['GCP_SERVICE_ACCOUNT_KEY'])
    creds = service_account.Credentials.from_service_account_info(info)
    return build('drive', 'v3', credentials=creds)

def main():
    service = get_drive_service()
    
    # 1. Master-Datei laden
    if os.path.exists(MASTER_FILE):
        df_master = pd.read_csv(MASTER_FILE)
        df_master['last_seen'] = pd.to_datetime(df_master['last_seen'])
    else:
        df_master = pd.DataFrame(columns=[ID_COLUMN, 'first_seen', 'last_seen'])

    # 2. Neue Dateien aus Google Drive abrufen
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and name str_endswith '.xlsx'",
        fields="files(id, name)").execute()
    items = results.get('files', [])

    if not items:
        print("Keine neuen Dateien gefunden.")
        return

    new_data_frames = []
    for item in items:
        request = service.files().get_media(fileId=item['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        
        df_new = pd.read_excel(io.BytesIO(fh.getvalue()))
        new_data_frames.append(df_new)
        # Optional: Datei nach Verarbeitung in Drive löschen (Vorsicht beim Testen!)
        # service.files().delete(fileId=item['id']).execute()

    if new_data_frames:
        df_incoming = pd.concat(new_data_frames, ignore_index=True)
        today = datetime.now().strftime('%Y-%m-%d')

        # 3. Logik: Mergen & Deduplizieren
        for _, row in df_incoming.iterrows():
            url = row[ID_COLUMN]
            if url in df_master[ID_COLUMN].values:
                # Vorhanden: Nur last_seen aktualisieren
                df_master.loc[df_master[ID_COLUMN] == url, 'last_seen'] = today
            else:
                # Neu: Hinzufügen mit first_seen und last_seen
                new_job = row.to_dict()
                new_job['first_seen'] = today
                new_job['last_seen'] = today
                df_master = pd.concat([df_master, pd.DataFrame([new_job])], ignore_index=True)

    # 4. Alte Jobs löschen (optional, basierend auf deiner Vorgabe)
    # Entfernt Jobs, die länger als X Tage nicht im Scrape auftauchten
    cutoff_date = datetime.now() - timedelta(days=DAYS_UNTIL_DELETION)
    df_master = df_master[pd.to_datetime(df_master['last_seen']) > cutoff_date]

    # 5. Speichern
    df_master.to_csv(MASTER_FILE, index=False)
    print(f"Master-Datei aktualisiert: {len(df_master)} Jobs enthalten.")

if __name__ == "__main__":
    main()
