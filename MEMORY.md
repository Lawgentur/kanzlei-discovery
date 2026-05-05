# MEMORY.md - Long-Term Project Memory

## Kanzlei Discovery Project

### Status (2026-05-04)
- **Hauptliste:** 3.378 Kanzleien (target_firms_full.csv) werden täglich um 05:00 UTC gecrawlt.
- **Cronjob:** ID `f1502c9f-23b5-4110-9930-055fcde46292` aktualisiert `jobs_master.csv`. Er ist auf `sessionTarget: current` gestellt, um Berichte in diese Sitzung zu senden.
- **Aktuelles Teilprojekt:** "Alte Kanzleien" (13.477 Einträge).
  - Skript: `background_check_kanzleien.py` läuft im Hintergrund.
  - Ziel: Erreichbarkeitsprüfung und URL-Bereinigung.
  - Dokumentation: Ergebnisse landen in `alte_kanzleien_final_report.csv`.
  - Regel: KEIN automatischer Merge in die Hauptliste ohne manuelle Freigabe des Nutzers.

### Infrastruktur & Sicherheit
- **Git Repository:** Lokales Repo in `/home/ubuntu/.openclaw/workspace` initialisiert.
- **Checkpoints:** Skripte und CSV-Stände werden bei wichtigen Meilensteinen committed.
- **Recovery:** Falls diese Session abstürzt, kann ein neuer Agent via `MEMORY.md` und `git log` den Faden sofort wieder aufnehmen.
