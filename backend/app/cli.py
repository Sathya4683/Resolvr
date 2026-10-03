import argparse
import logging

from app.config import settings
from app.db import SessionLocal
from app.logging_setup import setup_logging

log = logging.getLogger("resolvr.cli")


def cmd_seed(args):
    from app.services.seed import run_seed

    if not settings.auto_seed and args.if_empty:
        log.info("AUTO_SEED is off, skipping")
        return
    with SessionLocal() as db:
        run_seed(db, if_empty=args.if_empty)


def cmd_send_digest(args):
    from datetime import date

    from app.services import digest

    with SessionLocal() as db:
        if args.date:
            run = digest.send_scheduled(db, date.fromisoformat(args.date))
        else:
            digest.send_today(db)
            return
        log.info("digest", extra={"status": run.status if run else "already sent"})


def main():
    setup_logging("cli", settings.log_level)
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="load categories, users, kb articles and resolved tickets")
    seed.add_argument("--if-empty", action="store_true", help="skip if the database already has data")
    seed.set_defaults(func=cmd_seed)

    send = sub.add_parser("send-digest", help="send the daily digest email now (same as the cron job)")
    send.add_argument("--date", help="YYYY-MM-DD, defaults to today")
    send.set_defaults(func=cmd_send_digest)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
