#!/usr/bin/env python3
"""Delete forecast files from this repository once the challenge has them on its S3 storage.

The challenge reads each new file in forecasts/ once and publishes what it did with every
file, for each model, at <S3_BASE_URL>/submission_results/<model_id>.csv: the file's path,
its git blob SHA (the fingerprint git keeps of the file's contents) and a status. A
forecast is deleted here only when that list says the challenge has processed *this exact
file*: the same path with the same SHA and the status "processed". A file the challenge has
not processed yet, one it rejected, and one that was changed after it was processed (the
challenge ignores such edits) are all kept, and the reason is printed. If the list cannot
be read, nothing is deleted.

Run from the repository root:
  python cleanup_forecasts.py [--dry-run] [--keep N] [--keep-days D]
Needs the packages in requirements.txt (pip install -r requirements.txt).

  --dry-run      only say what would be deleted
  --keep N       keep the newest N forecasts the challenge has (default 0)
  --keep-days D  keep every forecast from the last D days, whether or not the challenge
                 has it (default 0: nothing is kept for its age). A forecast's age is
                 today minus the date in its file name (its reference date), so
                 --keep-days 7 keeps the files dated 7 days ago or later.
  --today DATE   treat DATE (YYYY-MM-DD) as today, for testing (default: today, UTC)

The two protections are independent: a forecast is kept if it is among the newest N the
challenge has or is from the last D days.

Environment variables (all optional)
  S3_BASE_URL  the challenge's bucket (default: the template challenge's)
  CHALLENGE    the challenge's project_id, to pick its block of challenge-model.yaml
  S3_KEY, S3_SECRET  a key that can read the challenge's bucket. Set both when the bucket is
               private (ask the challenge for a read-only key).
"""
import argparse
import datetime
import hashlib
import os
import re
import sys
from pathlib import Path

import yaml

from challenge_s3 import read_csv

S3_BASE_URL = os.environ.get("S3_BASE_URL") or "https://s3.us-east-005.backblazeb2.com/template-challenge"
CHALLENGE = os.environ.get("CHALLENGE") or "templatecast"


def git_blob_sha(path):
    """The SHA git gives a file's contents (what `git hash-object` prints)."""
    data = Path(path).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def models_in(path="challenge-model.yaml"):
    """The (model_id, folder) pairs that challenge-model.yaml lists for this challenge."""
    parsed = yaml.safe_load(Path(path).read_text())
    blocks = [parsed] if isinstance(parsed, dict) else parsed
    models = []
    for block in blocks:
        if isinstance(block, dict) and block.get("challenge") == CHALLENGE:
            for model in block.get("models") or []:
                models.append((model["model_id"], str(model.get("path") or "forecasts/")))
    if not models:
        sys.exit(f"No models for the challenge '{CHALLENGE}' in {path}.")
    return models


def forecast_files(model_id, folder):
    """The model's forecast files in `folder`, oldest first (the date is in the name)."""
    pattern = re.compile(rf"^[^-]+-\d{{4}}-\d{{2}}-\d{{2}}-{re.escape(model_id)}\.csv(\.gz)?$")
    root = Path(folder)
    return sorted(p for p in root.glob("*") if p.is_file() and pattern.match(p.name))


def file_date(path):
    """The reference date in a forecast's file name, <theme>-<YYYY-MM-DD>-<model_id>.csv."""
    return datetime.date.fromisoformat(re.search(r"-(\d{4}-\d{2}-\d{2})-", path.name).group(1))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="only say what would be deleted")
    parser.add_argument("--keep", type=int, default=0,
                        help="keep the newest N forecasts the challenge has")
    parser.add_argument("--keep-days", type=int, default=0,
                        help="keep every forecast from the last D days, on S3 or not")
    parser.add_argument("--today", help="treat this date (YYYY-MM-DD) as today, for testing")
    args = parser.parse_args()
    today = (datetime.date.fromisoformat(args.today) if args.today
             else datetime.datetime.now(datetime.timezone.utc).date())
    oldest_kept = today - datetime.timedelta(days=args.keep_days)

    deletable, kept = [], []
    for model_id, folder in models_in():
        url = f"{S3_BASE_URL.rstrip('/')}/submission_results/{model_id}.csv"
        try:
            results = read_csv(url)
        except Exception as error:                  # a missing list is not "nothing processed"
            sys.exit(f"Could not read {url}: {error}\nNothing was deleted.")
        done = results[results["status"] == "processed"]
        processed = {(row.file, row.sha) for row in done.itertuples()}
        known = {}                                  # path -> statuses, to explain what is kept
        for row in results.itertuples():
            known.setdefault(row.file, set()).add(row.status)

        candidates = []
        for path in forecast_files(model_id, folder):
            name = path.as_posix()
            if (name, git_blob_sha(path)) in processed:
                candidates.append(path)
            elif name in {file for file, _ in processed}:
                kept.append((name, "changed since the challenge processed it"))
            elif name in known:
                kept.append((name, "the challenge's status: " + ", ".join(sorted(known[name]))))
            else:
                kept.append((name, "not processed by the challenge yet"))
        newest = candidates[len(candidates) - args.keep:] if args.keep > 0 else []
        for path in candidates:
            if path in newest:
                kept.append((path.as_posix(), f"kept as one of the newest {args.keep}"))
            elif args.keep_days > 0 and file_date(path) >= oldest_kept:
                kept.append((path.as_posix(),
                             f"from the last {args.keep_days} days, kept whether or not it is on S3"))
            else:
                deletable.append(path)

    for path in deletable:
        print(f"{'would delete' if args.dry_run else 'deleting'}: {path.as_posix()}")
        if not args.dry_run:
            path.unlink()
    for name, reason in kept:
        print(f"keeping: {name} ({reason})")
    print(f"{len(deletable)} file(s) {'to delete' if args.dry_run else 'deleted'}, {len(kept)} kept.")


if __name__ == "__main__":
    main()
