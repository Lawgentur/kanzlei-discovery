# Kanzlei Discovery

Pipeline for collecting open job postings from German law firm career pages, normalizing them into one master CSV, and exporting a stable public CSV for the connected frontend.

## Current Contract

The canonical master file is `jobs_master.csv` with these columns:

```text
Titel, Link, Kanzlei, Stadt, Quelle, first_seen, last_seen
```

The frontend-safe export is written to:

```text
media/jobs_master_public.csv
```

The target firm list is `target_firms_full.csv` with:

```text
Unternehmensname, Domainname des Unternehmens, Jobboard_URL
```

## Run Locally

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Sanitize current CSV data and refresh the public export:

```bash
kanzlei-discovery --sanitize-only
```

Run Drive sync when `GCP_SERVICE_ACCOUNT_KEY` and `DRIVE_FOLDER_ID` are present:

```bash
kanzlei-discovery
```

Scrape a small sample of target firms:

```bash
kanzlei-discovery --no-drive --scrape --limit 20
```

Enable LLM fallback only when an API key is configured:

```bash
kanzlei-discovery --no-drive --scrape --llm-fallback
```

Place new Octoparse Indeed or Stepstone exports in `IMPORTS/`. Both `.csv` and
`.xlsx` files are supported; already processed files are skipped by checksum.
The weekly task waits three minutes and only imports files whose size and
modification time remain unchanged during that interval.

## Project Layout

- `src/kanzlei_discovery/`: production pipeline code.
- `tests/`: parser, merge, and quality tests.
- `archive/`: old OpenClaw, import, simulation, and broken scraper artifacts kept for reference.
- `media/`: frontend-facing static/export files.
