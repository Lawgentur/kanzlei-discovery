import pandas as pd
import os
import json
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

# --- KONFIGURATION ---
FOLDER_ID = '197A_upMwFMjERVkMlEIytRNIJidjMYxo' 
MASTER_FILE = 'jobs_master.csv'
DAYS_UNTIL_DELETION = 30 

# Spalten-Mapping
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
    cols_needed = ['Titel', 'Link', 'Kanzlei', 'Stadt', 'first_seen', 'last_seen']
    
    if os.path.exists(MASTER_FILE):
        try:
            df_master = pd.read_csv(MASTER_FILE, on_bad_lines='skip', engine='python')
            for c in cols_needed:
                if c not in df_master.columns: df_master[c] = ""
            df_master['last_seen'] = pd.to_datetime(df_master['last_seen'], errors='coerce')
        except:
            df_master = pd.DataFrame(columns=cols_needed)
    else:
        df_master = pd.DataFrame(columns=cols_needed)

    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and name contains '.xlsx'",
        fields="files(id, name)").execute()
    items = results.get('files', [])

    if items:
        new_dfs = []
        for item in items:
            request = service.files().get_media(fileId=item['id'])
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done: _, done = downloader.next_chunk()
            df_raw = pd.read_excel(io.BytesIO(fh.getvalue()))
            new_dfs.append(normalize_dataframe(df_raw))

        if new_dfs:
            df_incoming = pd.concat(new_dfs, ignore_index=True)
            for _, row in df_incoming.iterrows():
                titel = str(row.get('Titel', '')).strip()
                kanzlei = str(row.get('Kanzlei', '')).strip()
                stadt = str(row.get('Stadt', '')).strip()
                link = str(row.get('Link', '')).strip()
                
                if not titel or len(titel) < 3: continue

                # NEUE LOGIK: Abgleich über Titel, Kanzlei UND Stadt
                mask = (df_master['Titel'] == titel) & (df_master['Kanzlei'] == kanzlei) & (df_master['Stadt'] == stadt)
                
                if mask.any():
                    df_master.loc[mask, 'last_seen'] = today
                    df_master.loc[mask, 'Link'] = link # URL aktualisieren falls neu
                else:
                    new_job = {
                        'Titel': titel, 'Link': link, 'Kanzlei': kanzlei, 'Stadt': stadt,
                        'first_seen': today, 'last_seen': today
                    }
                    df_master = pd.concat([df_master, pd.DataFrame([new_job])], ignore_index=True)

    # Bereinigung
    cutoff = datetime.now() - timedelta(days=DAYS_UNTIL_DELETION)
    df_master = df_master[(pd.to_datetime(df_master['last_seen']) >= cutoff) | (df_master['last_seen'].isna())]
    
    df_master[cols_needed].to_csv(MASTER_FILE, index=False, quoting=1) # quoting=1 setzt alles in Anführungszeichen
    print(f"Update beendet. {len(df_master)} Jobs im Master.")

if __name__ == "__main__":
    main()
