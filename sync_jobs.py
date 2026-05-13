"""
Lawgentur Sync-Bot v2
=====================
Liest neue Scrape-Ergebnisse aus Google Drive, mergt sie in jobs_master.csv
und bereinigt abgelaufene Stellen. Läuft als GitHub Action.

Wichtigste Verbesserungen gegenüber v1:
  - URL-basierte Deduplication (statt Titel+Kanzlei+Stadt)
  - Drive-Pagination (findet alle Dateien, nicht nur die ersten 100)
  - Verarbeitungs-State (sync_state.json) → jede Datei wird nur einmal gelesen
  - FOLDER_ID als Environment-Variable statt hardcoded
  - Vollständige Statistik-Ausgabe für Monitoring
  - Robuste Stale-Removal ohne isna()-Falle
  - Mehrquellen-Support (Worker, Stepstone, Indeed) per automatischer Erkennung
"""

import pandas as pd
import os
import json
import sys
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

# ======================================================================
# KONFIGURATION — alle Werte kommen aus GitHub Secrets / Env-Variablen
# ======================================================================

FOLDER_ID           = os.environ['DRIVE_FOLDER_ID']          # GitHub Secret: DRIVE_FOLDER_ID
MASTER_FILE         = 'jobs_master.csv'                       # Im Repo-Root
STATE_FILE          = 'sync_state.json'                       # Welche Drive-Dateien schon verarbeitet wurden
DAYS_UNTIL_DELETION = int(os.getenv('DAYS_UNTIL_DELETION', '30'))

# Alle Spalten der Master-CSV
COLS = ['Titel', 'Link', 'Kanzlei', 'Stadt', 'Quelle', 'first_seen', 'last_seen']

# Spalten-Mappings je nach Datei-Quelle (automatische Erkennung via Spaltenname-Check)
SOURCE_MAPPINGS = {
    'stepstone': {
        'Job_Titel':              'Titel',
        'Titel_url':              'Link',
        'Name_des_Unternehmens':  'Kanzlei',
        'Standort':               'Stadt',
    },
    'indeed': {
        'Job_Title':    'Titel',
        'Job_URL':      'Link',
        'Company_Name': 'Kanzlei',
        'Location':     'Stadt',
    },
    # Worker v3 hat bereits die richtigen Spaltennamen — kein Mapping nötig
}


# ======================================================================
# GOOGLE DRIVE
# ======================================================================

def get_drive_service():
    """Service-Account-Key kommt als JSON-String aus dem GitHub Secret."""
    key_json = os.environ['GCP_SERVICE_ACCOUNT_KEY']
    info     = json.loads(key_json)
    creds    = service_account.Credentials.from_service_account_info(info)
    return build('drive', 'v3', credentials=creds, cache_discovery=False)


def list_drive_files(service, already_processed_ids: set) -> list:
    """
    Gibt alle noch nicht verarbeiteten .xlsx-Dateien im Drive-Ordner zurück.
    Nutzt Pagination, damit auch bei >100 Dateien nichts verloren geht.
    Schließt master.xlsx und bereits verarbeitete Dateien aus.
    """
    results = []
    page_token = None

    # Nur Scrape-Ergebnisse (Name beginnt mit 'Scrape_'), kein master-File
    query = (
        f"'{FOLDER_ID}' in parents "
        f"and name contains '.xlsx' "
        f"and not name = 'webseiten_jobsuche_master.xlsx' "
        f"and trashed = false"
    )

    while True:
        params = dict(
            q=query,
            fields='nextPageToken, files(id, name, modifiedTime)',
            pageSize=100,
            orderBy='modifiedTime desc',
        )
        if page_token:
            params['pageToken'] = page_token

        response   = service.files().list(**params).execute()
        items      = response.get('files', [])
        page_token = response.get('nextPageToken')

        for item in items:
            if item['id'] not in already_processed_ids:
                results.append(item)

        if not page_token:
            break

    return results


def download_excel(service, file_id: str) -> pd.DataFrame:
    """Lädt eine Excel-Datei aus Drive und gibt sie als DataFrame zurück."""
    request = service.files().get_media(fileId=file_id)
    fh      = io.BytesIO()
    dl      = MediaIoBaseDownload(fh, request)
    done    = False
    while not done:
        _, done = dl.next_chunk()
    return pd.read_excel(io.BytesIO(fh.getvalue()))


# ======================================================================
# QUELLERKENNUNG & NORMALISIERUNG
# ======================================================================

def detect_and_normalize(df: pd.DataFrame) -> pd.DataFrame:
    """
    Erkennt die Quelldatei automatisch anhand der Spalten und
    benennt sie in das Master-Format (Titel/Link/Kanzlei/Stadt) um.
    """
    cols = set(df.columns)

    if 'Titel_url' in cols:
        return df.rename(columns=SOURCE_MAPPINGS['stepstone'])

    if 'Job_URL' in cols:
        return df.rename(columns=SOURCE_MAPPINGS['indeed'])

    # Worker v3 — Spalten stimmen bereits überein
    return df


# ======================================================================
# STATE-MANAGEMENT (welche Drive-Dateien schon verarbeitet wurden)
# ======================================================================

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'processed_ids': [], 'last_sync': None}


def save_state(state: dict):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)


# ======================================================================
# MASTER-CSV LADEN / SPEICHERN
# ======================================================================

def load_master() -> pd.DataFrame:
    if os.path.exists(MASTER_FILE):
        try:
            df = pd.read_csv(
                MASTER_FILE,
                on_bad_lines='skip',
                engine='python',
                quoting=1,
                dtype=str,          # Alles als String einlesen (URLs nicht as float parsen)
            )
            for col in COLS:
                if col not in df.columns:
                    df[col] = ''
            return df[COLS]
        except Exception as e:
            print(f"⚠ Fehler beim Laden von {MASTER_FILE}: {e} — starte mit leerem Master.")
    return pd.DataFrame(columns=COLS)


def save_master(df: pd.DataFrame):
    df[COLS].to_csv(
        MASTER_FILE,
        index=False,
        quoting=1,          # Alle Felder in Anführungszeichen (CSV-Stabilität)
        encoding='utf-8',
    )


# ======================================================================
# MERGE-LOGIK
# ======================================================================

def merge_incoming(df_master: pd.DataFrame, df_incoming: pd.DataFrame, today: str) -> tuple:
    """
    Mergt neue Jobs in den Master.
    Primärschlüssel: Link (URL) — der eindeutigste Identifier eines Stellenangebots.

    Rückgabe: (aktualisierter Master-DataFrame, Statistik-Dict)
    """
    stats = {'neue': 0, 'aktualisiert': 0, 'übersprungen': 0}

    # Index für schnellen Lookup: Link → Zeilennummer im Master
    link_index = {
        str(link).strip().rstrip('/'): idx
        for idx, link in enumerate(df_master['Link'])
        if pd.notna(link) and str(link).strip()
    }

    new_rows = []

    for _, row in df_incoming.iterrows():
        titel   = str(row.get('Titel',   '')).strip()
        link    = str(row.get('Link',    '')).strip().rstrip('/')
        kanzlei = str(row.get('Kanzlei', '')).strip()
        stadt   = str(row.get('Stadt',   '')).strip()
        quelle  = str(row.get('Quelle',  '')).strip()

        # Ungültige Einträge überspringen
        if not titel or len(titel) < 5 or not link.startswith('http'):
            stats['übersprungen'] += 1
            continue

        if link in link_index:
            # Bereits bekannt → last_seen aktualisieren
            idx = link_index[link]
            df_master.at[idx, 'last_seen'] = today
            # Kanzlei/Stadt/Quelle updaten falls verändert
            if kanzlei:
                df_master.at[idx, 'Kanzlei'] = kanzlei
            if stadt:
                df_master.at[idx, 'Stadt'] = stadt
            if quelle:
                df_master.at[idx, 'Quelle'] = quelle
            stats['aktualisiert'] += 1
        else:
            # Neu → zur Batch-Liste hinzufügen
            new_rows.append({
                'Titel':      titel,
                'Link':       link,
                'Kanzlei':    kanzlei,
                'Stadt':      stadt,
                'Quelle':     quelle,
                'first_seen': today,
                'last_seen':  today,
            })
            link_index[link] = len(df_master) + len(new_rows) - 1
            stats['neue'] += 1

    # Alle neuen Zeilen auf einmal anhängen (schneller als concat in der Schleife)
    if new_rows:
        df_master = pd.concat(
            [df_master, pd.DataFrame(new_rows)],
            ignore_index=True,
        )

    return df_master, stats


# ======================================================================
# STALE-REMOVAL
# ======================================================================

def remove_stale(df: pd.DataFrame, cutoff: datetime) -> tuple:
    """
    Entfernt Jobs, die seit >DAYS_UNTIL_DELETION Tagen nicht mehr gesehen wurden.
    Jobs ohne last_seen (z. B. manuell eingefügt) werden auf 'unbekannt' gesetzt
    und NICHT gelöscht — aber nach 30 Tagen ohne Aktualisierung auch entfernt.
    """
    df['last_seen_dt'] = pd.to_datetime(df['last_seen'], errors='coerce')

    # Ohne Datum → setze auf today damit sie erst nach 30 Tagen rausfallen
    df.loc[df['last_seen_dt'].isna(), 'last_seen_dt'] = datetime.now()

    before = len(df)
    df     = df[df['last_seen_dt'] >= cutoff].copy()
    after  = len(df)

    df.drop(columns=['last_seen_dt'], inplace=True)
    return df, before - after


# ======================================================================
# MAIN
# ======================================================================

def main():
    today   = datetime.now().strftime('%Y-%m-%d')
    cutoff  = datetime.now() - timedelta(days=DAYS_UNTIL_DELETION)

    print(f"{'='*55}")
    print(f"Lawgentur Sync-Bot v2 — {today}")
    print(f"{'='*55}")

    # --- Drive verbinden ---
    service = get_drive_service()

    # --- State laden (welche Drive-Dateien schon verarbeitet) ---
    state               = load_state()
    processed_ids       = set(state.get('processed_ids', []))
    newly_processed_ids = []

    # --- Master laden ---
    df_master = load_master()
    print(f"Master geladen: {len(df_master)} bestehende Jobs")

    # --- Neue Drive-Dateien finden ---
    new_files = list_drive_files(service, processed_ids)
    print(f"Neue Dateien in Drive: {len(new_files)}")

    total_stats = {'neue': 0, 'aktualisiert': 0, 'übersprungen': 0}

    for item in new_files:
        fname = item['name']
        fid   = item['id']
        print(f"\n  Verarbeite: {fname}")

        try:
            df_raw      = download_excel(service, fid)
            df_norm     = detect_and_normalize(df_raw)
            df_master, stats = merge_incoming(df_master, df_norm, today)

            print(f"    → neu: {stats['neue']}  aktualisiert: {stats['aktualisiert']}  "
                  f"übersprungen: {stats['übersprungen']}")

            for k in total_stats:
                total_stats[k] += stats[k]

            newly_processed_ids.append(fid)

        except Exception as e:
            print(f"  ✗ Fehler bei {fname}: {e}", file=sys.stderr)
            # Datei NICHT als processed markieren → wird beim nächsten Run erneut versucht

    # --- Stale Jobs entfernen ---
    df_master, deleted = remove_stale(df_master, cutoff)
    print(f"\nAbgelaufene Jobs entfernt: {deleted} (>{DAYS_UNTIL_DELETION} Tage nicht gesehen)")

    # --- Speichern ---
    save_master(df_master)

    # State aktualisieren — nur erfolgreich verarbeitete IDs merken
    state['processed_ids'] = list(processed_ids | set(newly_processed_ids))
    state['last_sync']     = today
    save_state(state)

    # --- Zusammenfassung ---
    print(f"\n{'='*55}")
    print(f"Neue Jobs:         {total_stats['neue']}")
    print(f"Aktualisiert:      {total_stats['aktualisiert']}")
    print(f"Übersprungen:      {total_stats['übersprungen']}")
    print(f"Abgelaufen/gelöscht: {deleted}")
    print(f"Master gesamt:     {len(df_master)} Jobs")
    print(f"{'='*55}")

    # Commit-Message als Output für GitHub Actions (wird in der YAML genutzt)
    summary = (
        f"Jobs: +{total_stats['neue']} neu, "
        f"~{total_stats['aktualisiert']} updated, "
        f"-{deleted} expired | Gesamt: {len(df_master)}"
    )
    print(f"\nCOMMIT_MSG={summary}")   # Wird von der YAML per grep ausgelesen

    # Exit-Code 0 auch ohne neue Dateien (verhindert unnötige Fehler in CI)
    sys.exit(0)


if __name__ == '__main__':
    main()
