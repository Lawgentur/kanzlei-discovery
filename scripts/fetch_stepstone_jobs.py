from __future__ import annotations

import argparse
from collections import OrderedDict
from datetime import date
from pathlib import Path

from kanzlei_discovery.stepstone import (
    StepstoneClient,
    empty_stats,
    load_resumable_checkpoint,
    load_searches,
    merge_search_rows,
    safe_console,
    save_checkpoint,
    search_fingerprint,
    write_export_atomic,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Stepstone job searches directly into the existing board-import format."
    )
    parser.add_argument("--config", default="config/stepstone_searches.json")
    parser.add_argument("--imports-dir", default="IMPORTS")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--checkpoint-file", default="state/stepstone_checkpoint.json")
    parser.add_argument("--delay-seconds", type=float, default=0.5)
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--limit-queries", type=int, default=0)
    parser.add_argument(
        "--minimum-rows",
        type=int,
        default=1000,
        help="Fail before export when fewer unique rows were collected.",
    )
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()

    searches = load_searches(Path(args.config))
    if args.limit_queries:
        searches = searches[: args.limit_queries]
    fingerprint = search_fingerprint(searches)
    checkpoint_file = Path(args.checkpoint_file)
    if args.fresh:
        start_index, rows_by_id, stats = 0, OrderedDict(), empty_stats()
    else:
        start_index, rows_by_id, stats = load_resumable_checkpoint(
            checkpoint_file, args.date, fingerprint
        )
    if start_index:
        print(
            f"STEPSTONE_RESUME query={start_index}/{len(searches)} "
            f"rows={len(rows_by_id)}"
        )

    client = StepstoneClient(
        delay_seconds=args.delay_seconds,
        timeout_seconds=args.timeout_seconds,
        retries=args.retries,
    )
    for index in range(start_index, len(searches)):
        search = searches[index]
        result = client.fetch_search(
            search,
            args.date,
            max_pages=args.max_pages or None,
        )
        cross_query_duplicates = merge_search_rows(rows_by_id, result.rows)
        stats["queries"] += 1
        stats["pages"] += min(result.pages, args.max_pages or result.pages)
        stats["raw_rows"] += result.raw_rows
        stats["duplicates"] += result.duplicates + cross_query_duplicates
        save_checkpoint(
            checkpoint_file,
            scrape_date=args.date,
            fingerprint=fingerprint,
            next_query_index=index + 1,
            rows=rows_by_id.values(),
            stats=stats,
            completed=False,
        )
        print(
            f"STEPSTONE_QUERY query={safe_console(search.name)} "
            f"raw={result.raw_rows} unique_total={len(rows_by_id)}"
        )

    if len(rows_by_id) < args.minimum_rows:
        raise RuntimeError(
            f"Stepstone returned only {len(rows_by_id)} unique rows; "
            f"minimum is {args.minimum_rows}"
        )
    output = Path(args.imports_dir) / f"Stepstone Direct {args.date}.csv"
    write_export_atomic(output, rows_by_id.values())
    save_checkpoint(
        checkpoint_file,
        scrape_date=args.date,
        fingerprint=fingerprint,
        next_query_index=len(searches),
        rows=(),
        stats=stats,
        completed=True,
    )
    print(
        f"STEPSTONE_COMPLETE rows={len(rows_by_id)} raw={stats['raw_rows']} "
        f"duplicates={stats['duplicates']} pages={stats['pages']} file={output.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
