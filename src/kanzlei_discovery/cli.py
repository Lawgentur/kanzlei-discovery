from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

from .pipeline import PipelineConfig, run_pipeline, sanitize_only


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kanzlei Discovery pipeline")
    parser.add_argument("--target-file", default="target_firms_full.csv")
    parser.add_argument("--master-file", default="jobs_master.csv")
    parser.add_argument("--public-export", default="media/jobs_master_public.csv")
    parser.add_argument("--state-file", default="sync_state.json")
    parser.add_argument("--days-until-deletion", type=int, default=int(os.getenv("DAYS_UNTIL_DELETION", "30")))
    parser.add_argument("--scrape", action="store_true", help="Scrape target firms in addition to Drive sync.")
    parser.add_argument("--no-drive", action="store_true", help="Skip Google Drive Excel import even when env vars are present.")
    parser.add_argument("--llm-fallback", action="store_true", help="Use LLM extraction when API/DOM extraction finds no jobs.")
    parser.add_argument("--limit", type=int, help="Limit firm scraping for smoke tests.")
    parser.add_argument("--checkpoint-file", default="state/scrape_checkpoint.json")
    parser.add_argument("--checkpoint-interval", type=int, default=50)
    parser.add_argument("--sanitize-only", action="store_true", help="Only normalize jobs_master and target firms, then export.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = PipelineConfig(
        target_file=Path(args.target_file),
        master_file=Path(args.master_file),
        public_export=Path(args.public_export),
        state_file=Path(args.state_file),
        days_until_deletion=args.days_until_deletion,
        scrape=args.scrape,
        sync_drive=not args.no_drive,
        limit=args.limit,
        llm_fallback=args.llm_fallback,
        checkpoint_file=Path(args.checkpoint_file),
        checkpoint_interval=args.checkpoint_interval,
        today=date.today().isoformat(),
    )

    stats = sanitize_only(config) if args.sanitize_only else run_pipeline(config)
    for key, value in stats.items():
        print(f"{key}: {value}")
    print(f"COMMIT_MSG=Jobs pipeline: +{stats.get('new', 0)} new, ~{stats.get('updated', 0)} updated, -{stats.get('expired', 0)} expired")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
