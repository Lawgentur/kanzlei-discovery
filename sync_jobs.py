import pandas as pd
import os
import json
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

# --- KONFIGURATION ---
# BITTE HIER DEINE ID EINTRAGEN:
FOLDER_ID = '197A_upMwFMjERVkMlEIytRNIJidjMYxo' 
MASTER_FILE = 'jobs_master.csv'
ID_COLUMN = 'Link'
DAYS_UNTIL_DELETION = 30 # Erhöht auf 30 Tage Sicherheit

MAPPINGS = {
    'stepstone': {'Job_Titel': 'Titel', 'Titel_url': 'Link', 'Name_des_Unternehmens': 'Kanzlei', 'Standort': 'Stadt'},
    'indeed': {'Job_Title': 'Titel', 'Job_URL': 'Link', 'Company_Name': 'Kanzlei', 'Location': 'Stadt'}
}

def get_drive_service():
    info = json.loads(os.environ['GCP_SERVICE_ACCOUNT_KEY'])
    creds = service_account.Credentials.from_service_account_info(info)
    return build('drive', 'v3', credentials=creds)

def normalize_dataframe(df):
    cols = df.columns.tolist()
    if 'Titel_url' in cols: return df.rename(columns=MAPPINGS['stepstone'])
    if 'Job_URL' in cols: return df.rename(columns=MAPPINGS['indeed'])
    return df

def main():
    service = get_drive_service()
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 1. Master-Datei extrem vorsichtig laden
    cols_needed = ['Titel', 'Link', 'Kanzlei', 'Stadt', 'first_seen', 'last_seen']
    if os.path.exists(MASTER_FILE):
        try:
            # Wir lesen nur die Spalten, die wir wirklich brauchen und ignorieren den Rest
            df_master = pd.read_csv(MASTER_FILE, on_bad_lines='skip', engine='python')
            # Sicherstellen, dass alle Spalten existieren
            for c in cols_needed:
                if c not in df_master.columns:
                    df_master[c] = None
            df_master['last_seen'] = pd.to_datetime(df_master['last_seen'], errors='coerce')
        except Exception as e:
            print(f"CSV war zu kaputt, erstelle neue Struktur: {e}")
            df_master = pd.DataFrame(columns=cols_needed)
    else:
        df_master = pd.DataFrame(columns=cols_needed)

    # 2. Google Drive Abfrage
    try:
        results = service.files().list(
            q=f"'{FOLDER_ID}' in parents and name contains '.xlsx'",
            fields="files(id, name)").execute()
        items = results.get('files', [])
    except Exception as e:
        print(f"Fehler beim Zugriff auf Google Drive: {e}. Ist die FOLDER_ID korrekt?")
        return

    if items:
        new_dfs = []
        for item in items:
            print(f"Lade: {item['name']}")
            request = service.files().get_media(fileId=item['id'])
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            
            df_raw = pd.read_excel(io.BytesIO(fh.getvalue()))
            new_dfs.append(normalize_dataframe(df_raw))

        if new_dfs:
            df_incoming = pd.concat(new_dfs, ignore_index=True)
            for _, row in df_incoming.iterrows():
                url = str(row.get('Link', '')).strip()
                if not url or url == 'nan' or url == '': continue
                
                if url in df_master['Link'].values:
                    df_master.loc[df_master['Link'] == url, 'last_seen'] = today
                else:
                    new_job = {
                        'Titel': row.get('Titel'),
                        'Link': url,
                        'Kanzlei': row.get('Kanzlei'),
                        'Stadt': row.get('Stadt'),
                        'first_seen': today,
                        'last_seen': today
                    }
                    df_master = pd.concat([df_master, pd.DataFrame([new_job])], ignore_index=True)

    # 3. Bereinigung & Speichern
    # Nur Jobs behalten, die ein gültiges Datum haben und nicht zu alt sind
    df_master = df_master.dropna(subset=['Link'])
    df_master['last_seen_dt'] = pd.to_datetime(df_master['last_seen'], errors='coerce')
    cutoff = datetime.now() - timedelta(days=DAYS_UNTIL_DELETION)
    
    # Behalte alles, was neu ist ODER noch nicht abgelaufen
    df_master = df_master[(df_master['last_seen_dt'] >= cutoff) | (df_master['last_seen_dt'].isna())]
    
    # Hilfsspalte wieder entfernen und speichern
    df_master = df_master[cols_needed]
    df_master.to_csv(MASTER_FILE, index=False)
    print(f"Erfolg! Master hat jetzt {len(df_master)} saubere Einträge.")

if __name__ == "__main__":
    main()
