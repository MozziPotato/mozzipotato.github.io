#!/usr/bin/env python3
"""Blog automation system CLI entry point.

Usage:
    python main.py setup     # Initial setup (DB, seed keywords)
    python main.py daily     # Daily pipeline (keyword → write → publish)
    python main.py weekly    # Weekly pipeline (keyword research)
    python main.py cost      # Show monthly API cost
    python main.py generate  # Generate a single post (for testing)
    python main.py tv-scout  # Scout TV broadcast previews for keywords
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import load_config, get_project_root
from src.database import init_db


def setup_logging():
    config = load_config()
    log_file = get_project_root() / config["logging"]["file"]
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, config["logging"]["level"]),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def cmd_setup(args):
    from src.orchestrator import run_setup
    init_db()
    run_setup()


def cmd_daily(args):
    init_db()
    from src.orchestrator import run_daily
    run_daily()


def cmd_weekly(args):
    init_db()
    from src.orchestrator import run_weekly
    run_weekly()


def cmd_cost(args):
    init_db()
    from src.orchestrator import show_cost
    show_cost()


def cmd_tv_scout(args):
    """Run TV keyword scout to find keywords from broadcast previews."""
    init_db()
    from src.tv_keyword_scout import scout_tv_keywords

    print("Scouting TV broadcast previews for keywords...")
    keywords = scout_tv_keywords()

    if keywords:
        print(f"\nFound {len(keywords)} new keywords:")
        for kw in keywords:
            urgency = kw.get("urgency", "N/A")
            source = kw.get("source_program", "N/A")
            print(f"  [{urgency.upper()}] {kw['keyword']} (from: {source})")
            print(f"         → {kw.get('reason', '')}")
    else:
        print("\nNo new keywords found from TV previews.")


def cmd_generate(args):
    """Generate a single post for testing."""
    init_db()
    from src.database import get_approved_keywords
    from src.content_writer import generate_post

    keywords = get_approved_keywords(limit=1)
    if not keywords:
        print("No approved keywords. Run 'python main.py setup' first.")
        return

    kw = keywords[0]
    print(f"Generating post for: {kw['keyword']}")
    result = generate_post(kw["id"], kw["keyword"])

    print(f"\nTitle: {result['title']}")
    print(f"File: {result['file_path']}")
    print(f"Characters: {result['word_count']}")

    if result["warnings"]:
        print("\nSEO Warnings:")
        for w in result["warnings"]:
            print(f"  - {w}")
    else:
        print("\nSEO: All checks passed")


def main():
    parser = argparse.ArgumentParser(description="Blog Automation System")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("setup", help="Initial setup")
    subparsers.add_parser("daily", help="Run daily pipeline")
    subparsers.add_parser("weekly", help="Run weekly pipeline")
    subparsers.add_parser("cost", help="Show API cost")
    subparsers.add_parser("generate", help="Generate a single test post")
    subparsers.add_parser("tv-scout", help="Scout TV broadcast previews for keywords")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    setup_logging()

    commands = {
        "setup": cmd_setup,
        "daily": cmd_daily,
        "weekly": cmd_weekly,
        "cost": cmd_cost,
        "generate": cmd_generate,
        "tv-scout": cmd_tv_scout,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
