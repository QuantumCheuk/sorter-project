#!/usr/bin/env python3
# sorter/db/cli.py
# CLI for HUSKY-SORTER-001 batch database and report generation
# Author: Little Husky 🐕 | Date: 2026-05-02

import argparse
import json
import sys
from pathlib import Path

from sorter.db.database import Database
from sorter.db.report_generator import BatchReportGenerator, ReportFormat


def cmd_init(args):
    db = Database(db_path=args.db)
    stats = db.get_system_stats()
    print(f"✅ Database initialized: {stats['db_path']}")
    print(f"   Batches: {stats['total_batches']} | Beans: {stats['total_beans']} | "
          f"Critical Events: {stats['critical_events']} | DB Size: {stats['db_size_kb']} KB")


def cmd_stats(args):
    db = Database(db_path=args.db)
    stats = db.get_system_stats()
    print("─" * 40)
    print(f"  Database         : {stats['db_path']}")
    print(f"  Size             : {stats['db_size_kb']} KB")
    print(f"  Total Batches    : {stats['total_batches']}")
    print(f"  Total Beans      : {stats['total_beans']}")
    print(f"  Calibrations     : {stats['calibrations']}")
    print(f"  Critical Events  : {stats['critical_events']}")
    print("─" * 40)


def cmd_list_batches(args):
    db = Database(db_path=args.db)
    state_map = {0: "PENDING", 1: "RUNNING", 2: "COMPLETED", 3: "ABORTED", 4: "ARCHIVED"}
    batches = db.list_batches(
        limit=args.limit,
        state=args.state if hasattr(args, "state") and args.state else None,
    )
    if not batches:
        print("No batches found.")
        return
    print(f"{'Batch ID':<12} {'Origin':<15} {'State':<10} {'Beans':>7} {'Defect%':>7} "
          f"{'GradeA%':>7} {'Weight(g)':>9}  Started (UTC)")
    print("─" * 80)
    for b in batches:
        print(
            f"{b.batch_id[:12]:<12} {b.origin[:15]:<15} "
            f"{state_map.get(b.state, str(b.state)):<10} "
            f"{b.total_beans:>7,} "
            f"{b.defect_rate_pct():>6.1f}% "
            f"{b.grade_yield_pct(__import__('sorter.db.models', fromlist=['SortGrade']).SortGrade.GRADE_A):>6.1f}% "
            f"{b.total_weight_g:>9.1f}  {b.started_at_utc[:19]}"
        )


def cmd_batch_report(args):
    db = Database(db_path=args.db)
    gen = BatchReportGenerator(db)

    if args.format == "text":
        print(gen.generate_text(args.batch_id))
    elif args.format == "csv":
        csv_data = gen.generate_csv(args.batch_id)
        if args.output:
            Path(args.output).write_text(csv_data, encoding="utf-8")
            print(f"✅ CSV saved to {args.output}")
        else:
            print(csv_data)
    else:
        report = gen.generate_json(args.batch_id, include_beans=args.include_beans)
        if args.output:
            Path(args.output).write_text(
                json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"✅ JSON saved to {args.output}")
        else:
            print(json.dumps(report, indent=2, ensure_ascii=False))


def cmd_summary(args):
    db = Database(db_path=args.db)
    gen = BatchReportGenerator(db)
    report = gen.generate_multi_batch_summary(origin=args.origin, limit=args.limit)
    print(json.dumps(report, indent=2, ensure_ascii=False))


def cmd_export(args):
    db = Database(db_path=args.db)
    gen = BatchReportGenerator(db)

    batches = db.list_batches(limit=args.limit)
    if not batches:
        print("No batches to export.")
        return

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for batch in batches:
        try:
            fp, summary = gen.save_report(
                batch.batch_id,
                str(output_dir),
                fmt=args.format,
                include_beans=args.include_beans,
            )
            results.append(summary)
            print(f"  ✅ {summary}")
        except Exception as e:
            print(f"  ❌ {batch.batch_id}: {e}")

    print(f"\n✅ Exported {len(results)} reports to {output_dir}")


def cmd_events(args):
    db = Database(db_path=args.db)
    events = db.get_events(
        severity=args.severity,
        component=args.component,
        since_utc=args.since,
        limit=args.limit,
    )
    if not events:
        print("No events found.")
        return
    print(f"{'Timestamp (UTC)':<28} {'Severity':<10} {'Component':<12} Message")
    print("─" * 90)
    for e in events:
        print(f"{e.timestamp_utc:<28} {e.severity:<10} {e.component:<12} {e.message[:50]}")


def main():
    parser = argparse.ArgumentParser(
        description="HUSKY-SORTER-001 Batch Database CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", default=None, help="Path to SQLite database file")

    sub = parser.add_subparsers(dest="cmd", required=True)

    # init
    p = sub.add_parser("init", help="Initialize database and show stats")

    # stats
    p = sub.add_parser("stats", help="Show database statistics")

    # list
    p = sub.add_parser("list", help="List recent batches")
    p.add_argument("--limit", type=int, default=20)

    # report
    p = sub.add_parser("report", help="Generate report for a batch")
    p.add_argument("batch_id", help="Batch ID")
    p.add_argument("--format", choices=["json", "csv", "text"], default="text")
    p.add_argument("--include-beans", action="store_true", help="Include per-bean records")
    p.add_argument("--output", help="Save to file instead of printing")

    # summary
    p = sub.add_parser("summary", help="Multi-batch summary report")
    p.add_argument("--origin", default=None, help="Filter by origin")
    p.add_argument("--limit", type=int, default=30)

    # export
    p = sub.add_parser("export", help="Export multiple batch reports")
    p.add_argument("--format", choices=["json", "csv", "text"], default="json")
    p.add_argument("--output-dir", default="./reports", help="Output directory")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--include-beans", action="store_true", help="Include per-bean records")

    # events
    p = sub.add_parser("events", help="Query system events")
    p.add_argument("--severity", choices=["INFO", "WARNING", "ERROR", "CRITICAL"])
    p.add_argument("--component", help="Filter by component")
    p.add_argument("--since", help="ISO-8601 timestamp (UTC)")
    p.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()

    handlers = {
        "init": cmd_init,
        "stats": cmd_stats,
        "list": cmd_list_batches,
        "report": cmd_batch_report,
        "summary": cmd_summary,
        "export": cmd_export,
        "events": cmd_events,
    }

    handlers[args.cmd](args)


if __name__ == "__main__":
    main()
