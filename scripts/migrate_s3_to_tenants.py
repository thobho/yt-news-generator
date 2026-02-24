#!/usr/bin/env python3
"""
S3 migration: copy existing data into the per-tenant key layout.

Old layout (used by main branch — NEVER DELETED):
  data/*              → settings, prompts, scheduler_config, etc.
  output/*            → run directories

New layout (used by feature/multi-tenant):
  tenants/pl/data/*
  tenants/pl/output/*
  tenants/us/data/.keep   (scaffold)
  tenants/us/output/.keep (scaffold)

IMPORTANT: originals are NOT deleted so the existing app on main
continues to work unchanged.

Usage:
  python scripts/migrate_s3_to_tenants.py --dry-run
  python scripts/migrate_s3_to_tenants.py
  python scripts/migrate_s3_to_tenants.py --bucket my-bucket --region eu-west-1
"""

import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError
except ImportError:
    print("ERROR: boto3 not installed. Run: pip install boto3")
    sys.exit(1)

THREADS = 50
_print_lock = threading.Lock()


def log(msg: str, dry_run: bool = False):
    prefix = "[DRY-RUN] " if dry_run else ""
    with _print_lock:
        print(f"{prefix}{msg}")


def list_keys(s3, bucket: str, prefix: str) -> list[str]:
    """Return all S3 keys under a given prefix."""
    paginator = s3.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def key_exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise


def copy_key(s3, bucket: str, src_key: str, dst_key: str, dry_run: bool):
    if key_exists(s3, bucket, dst_key):
        log(f"  SKIP  s3://{bucket}/{dst_key}  (already exists)", dry_run)
        return False
    log(f"  COPY  s3://{bucket}/{src_key}", dry_run)
    log(f"        → s3://{bucket}/{dst_key}", dry_run)
    if not dry_run:
        s3.copy_object(
            Bucket=bucket,
            CopySource={"Bucket": bucket, "Key": src_key},
            Key=dst_key,
        )
    return True


def put_placeholder(s3, bucket: str, key: str, dry_run: bool):
    if key_exists(s3, bucket, key):
        log(f"  SKIP  s3://{bucket}/{key}  (already exists)", dry_run)
        return
    log(f"  PUT   s3://{bucket}/{key}  (scaffold placeholder)", dry_run)
    if not dry_run:
        s3.put_object(Bucket=bucket, Key=key, Body=b"")


def inject_timezone(s3, bucket: str, key: str, timezone: str, dry_run: bool):
    """Read settings.json from S3, add timezone if missing, write back."""
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        data = json.loads(obj["Body"].read())
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            log(f"  SKIP  {key} not found — cannot inject timezone", dry_run)
            return
        raise

    if "timezone" in data:
        log(f"  SKIP  timezone already set in {key} ({data['timezone']!r})", dry_run)
        return

    log(f"  PATCH s3://{bucket}/{key} — add timezone={timezone!r}", dry_run)
    if not dry_run:
        data["timezone"] = timezone
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(data, indent=2, ensure_ascii=False).encode(),
            ContentType="application/json",
        )


def _copy_pair(bucket: str, region: str, src_key: str, dst_key: str, dry_run: bool) -> bool:
    """Copy a single key using a thread-local S3 client. Returns True if copied."""
    s3 = boto3.client("s3", region_name=region, config=Config(max_pool_connections=THREADS))
    return copy_key(s3, bucket, src_key, dst_key, dry_run)


def copy_keys_parallel(bucket: str, region: str, pairs: list[tuple[str, str]], dry_run: bool) -> tuple[int, int]:
    """Copy (src, dst) pairs in parallel. Returns (copied, skipped)."""
    copied = 0
    skipped = 0
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = {
            executor.submit(_copy_pair, bucket, region, src, dst, dry_run): (src, dst)
            for src, dst in pairs
        }
        for future in as_completed(futures):
            try:
                if future.result():
                    copied += 1
                else:
                    skipped += 1
            except Exception as exc:
                src, dst = futures[future]
                with _print_lock:
                    print(f"  ERROR  {src} → {dst}: {exc}")
    return copied, skipped


def run(bucket: str, region: str, dry_run: bool):
    print(f"\n{'=== DRY RUN — no S3 objects will be changed ===' if dry_run else '=== S3 MIGRATION TO TENANT LAYOUT ==='}")
    print(f"    bucket: {bucket}  region: {region}  threads: {THREADS}\n")

    s3 = boto3.client("s3", region_name=region)

    copied = 0
    skipped = 0

    # ── 1. Copy data/* → tenants/pl/data/* ────────────────────────────────────
    print("[ 1/4 ] Copy data/* → tenants/pl/data/")
    src_keys = list_keys(s3, bucket, "data/")
    if not src_keys:
        print("  WARN  No keys found under data/ — nothing to copy")
    pairs = [(k, f"tenants/pl/data/{k[len('data/'):]}") for k in src_keys]
    c, s = copy_keys_parallel(bucket, region, pairs, dry_run)
    copied += c
    skipped += s

    # ── 2. Copy output/* → tenants/pl/output/* ────────────────────────────────
    print("\n[ 2/4 ] Copy output/* → tenants/pl/output/")
    src_keys = list_keys(s3, bucket, "output/")
    if not src_keys:
        print("  WARN  No keys found under output/ — nothing to copy")
    pairs = [(k, f"tenants/pl/output/{k[len('output/'):]}") for k in src_keys]
    c, s = copy_keys_parallel(bucket, region, pairs, dry_run)
    copied += c
    skipped += s

    # ── 3. Inject timezone into tenants/pl/data/settings.json ─────────────────
    print("\n[ 3/4 ] Inject timezone into tenants/pl/data/settings.json")
    inject_timezone(s3, bucket, "tenants/pl/data/settings.json", "Europe/Warsaw", dry_run)

    # ── 4. Scaffold us tenant directories ─────────────────────────────────────
    print("\n[ 4/4 ] Scaffold us tenant directories")
    put_placeholder(s3, bucket, "tenants/us/data/.keep", dry_run)
    put_placeholder(s3, bucket, "tenants/us/output/.keep", dry_run)

    print(f"\n{'=== DRY RUN complete ===' if dry_run else '=== Migration complete ==='}")
    print(f"    copied: {copied}   skipped: {skipped}\n")

    if dry_run:
        print("Run without --dry-run to apply.\n")
    else:
        verify(s3, bucket)


def verify(s3, bucket: str):
    print("=== Verifying ===\n")
    checks = [
        "tenants/pl/data/settings.json",
        "tenants/pl/data/prompts/",
        "tenants/us/data/.keep",
        "tenants/us/output/.keep",
    ]
    all_ok = True
    for key in checks:
        # For prefixes ending in /, just check at least one key exists
        if key.endswith("/"):
            keys = list_keys(s3, bucket, key)
            exists = len(keys) > 0
        else:
            exists = key_exists(s3, bucket, key)
        status = "OK  " if exists else "MISS"
        print(f"  {status}  s3://{bucket}/{key}")
        if not exists:
            all_ok = False

    # Check timezone
    try:
        obj = s3.get_object(Bucket=bucket, Key="tenants/pl/data/settings.json")
        data = json.loads(obj["Body"].read())
        tz = data.get("timezone", "MISSING")
        ok = tz == "Europe/Warsaw"
        print(f"  {'OK  ' if ok else 'FAIL'}  timezone = {tz!r}")
        if not ok:
            all_ok = False
    except ClientError:
        print("  FAIL  Could not read settings.json")
        all_ok = False

    # Confirm originals still intact
    print("\n  Confirming originals untouched (main branch safety):")
    for key in ["data/settings.json", "output/"]:
        if key.endswith("/"):
            keys = list_keys(s3, bucket, key)
            exists = len(keys) > 0
        else:
            exists = key_exists(s3, bucket, key)
        status = "OK  " if exists else "GONE"
        print(f"  {status}  s3://{bucket}/{key}  {'(intact)' if exists else '(MISSING — main branch may break!)'}")

    print(f"\n{'All checks passed.' if all_ok else 'Some checks FAILED.'}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Copy S3 data to per-tenant layout (originals kept)")
    parser.add_argument("--bucket", default=os.environ.get("S3_BUCKET", "yt-news-generator"))
    parser.add_argument("--region", default=os.environ.get("S3_REGION", "us-east-1"))
    parser.add_argument("--dry-run", action="store_true", help="Preview without touching S3")
    parser.add_argument("--verify", action="store_true", help="Run verification only")
    args = parser.parse_args()

    if args.verify:
        s3 = boto3.client("s3", region_name=args.region)
        verify(s3, args.bucket)
        sys.exit(0)

    run(bucket=args.bucket, region=args.region, dry_run=args.dry_run)
