#!/usr/bin/env python3
"""
One-time migration script: reorganise storage and credentials into per-tenant layout.

After this script runs:
  storage/data/          -> storage/tenants/pl/data/   (symlink keeps old path working)
  storage/output/        -> storage/tenants/pl/output/  (symlink keeps old path working)
  credentials/client_secrets.json -> credentials/pl/client_secrets.json  (symlink)
  credentials/token.json          -> credentials/pl/token.json           (symlink)

The symlinks ensure the application continues to work without any code changes
until Task 03 (storage DI) replaces all hardcoded paths.

Usage:
  python scripts/migrate_to_tenants.py           # perform migration
  python scripts/migrate_to_tenants.py --dry-run  # preview without touching files
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

STORAGE_DIR = PROJECT_ROOT / "storage"
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
WEBAPP_SETTINGS = PROJECT_ROOT / "webapp" / "settings.json"

PL_DATA_DIR = STORAGE_DIR / "tenants" / "pl" / "data"
PL_OUTPUT_DIR = STORAGE_DIR / "tenants" / "pl" / "output"
US_DATA_DIR = STORAGE_DIR / "tenants" / "us" / "data"
US_OUTPUT_DIR = STORAGE_DIR / "tenants" / "us" / "output"
PL_CREDS_DIR = CREDENTIALS_DIR / "pl"
US_CREDS_DIR = CREDENTIALS_DIR / "us"

OLD_DATA_DIR = STORAGE_DIR / "data"
OLD_OUTPUT_DIR = STORAGE_DIR / "output"
OLD_CLIENT_SECRETS = CREDENTIALS_DIR / "client_secrets.json"
OLD_TOKEN = CREDENTIALS_DIR / "token.json"


def log(msg: str, dry_run: bool = False):
    prefix = "[DRY-RUN] " if dry_run else ""
    print(f"{prefix}{msg}")


def move_dir_contents(src: Path, dst: Path, dry_run: bool):
    """Move all items from src into dst. Both must be directories."""
    if not src.exists():
        log(f"  SKIP  {src} does not exist", dry_run)
        return

    items = list(src.iterdir())
    if not items:
        log(f"  SKIP  {src} is already empty", dry_run)
        return

    for item in items:
        dest_item = dst / item.name
        if dest_item.exists() or dest_item.is_symlink():
            log(f"  SKIP  {item} → {dest_item} (destination already exists)", dry_run)
            continue
        log(f"  MOVE  {item} → {dest_item}", dry_run)
        if not dry_run:
            shutil.move(str(item), str(dest_item))


def move_file(src: Path, dst: Path, dry_run: bool):
    """Move a single file from src to dst."""
    if not src.exists() and not src.is_symlink():
        log(f"  SKIP  {src} does not exist", dry_run)
        return
    if src.is_symlink():
        log(f"  SKIP  {src} is already a symlink", dry_run)
        return
    if dst.exists():
        log(f"  SKIP  {dst} already exists", dry_run)
        return
    log(f"  MOVE  {src} → {dst}", dry_run)
    if not dry_run:
        shutil.move(str(src), str(dst))


def make_symlink(link: Path, target_relative: str, dry_run: bool):
    """
    Create a symlink at `link` pointing to `target_relative` (relative path).
    `link` must not already exist as a real dir/file.
    """
    if link.is_symlink():
        log(f"  SKIP  symlink {link} already exists", dry_run)
        return
    if link.exists():
        # It's a real directory/file — only safe to symlink if it's empty
        if link.is_dir() and not any(link.iterdir()):
            log(f"  RMDIR {link} (empty, replacing with symlink)", dry_run)
            if not dry_run:
                link.rmdir()
        else:
            log(f"  SKIP  {link} exists and is not empty — cannot create symlink", dry_run)
            return
    log(f"  LINK  {link} → {target_relative}", dry_run)
    if not dry_run:
        link.symlink_to(target_relative)


def ensure_dir(path: Path, dry_run: bool):
    if path.exists() or path.is_symlink():
        log(f"  EXISTS {path}", dry_run)
        return
    log(f"  MKDIR {path}", dry_run)
    if not dry_run:
        path.mkdir(parents=True, exist_ok=True)


def inject_timezone(settings_path: Path, timezone: str, dry_run: bool):
    if not settings_path.exists():
        log(f"  SKIP  {settings_path} not found — cannot inject timezone", dry_run)
        return
    data = json.loads(settings_path.read_text())
    if "timezone" in data:
        log(f"  SKIP  timezone already set in {settings_path}", dry_run)
        return
    log(f"  PATCH {settings_path} — add timezone={timezone!r}", dry_run)
    if not dry_run:
        data["timezone"] = timezone
        settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def delete_file(path: Path, dry_run: bool):
    if not path.exists():
        log(f"  SKIP  {path} does not exist", dry_run)
        return
    log(f"  DELETE {path}", dry_run)
    if not dry_run:
        path.unlink()


def run(dry_run: bool):
    print(f"\n{'=== DRY RUN — no files will be touched ===' if dry_run else '=== MIGRATING TO TENANT LAYOUT ==='}\n")

    # ── 1. Create tenant data dirs ─────────────────────────────────────────────
    print("[ 1/7 ] Create tenant directories")
    ensure_dir(PL_DATA_DIR, dry_run)
    ensure_dir(PL_OUTPUT_DIR, dry_run)
    ensure_dir(US_DATA_DIR, dry_run)
    ensure_dir(US_OUTPUT_DIR, dry_run)
    ensure_dir(PL_CREDS_DIR, dry_run)
    ensure_dir(US_CREDS_DIR, dry_run)

    # ── 2. Move storage/data/* → storage/tenants/pl/data/ ─────────────────────
    print("\n[ 2/7 ] Move storage/data/ contents → storage/tenants/pl/data/")
    move_dir_contents(OLD_DATA_DIR, PL_DATA_DIR, dry_run)

    # ── 3. Move storage/output/* → storage/tenants/pl/output/ ─────────────────
    print("\n[ 3/7 ] Move storage/output/ contents → storage/tenants/pl/output/")
    move_dir_contents(OLD_OUTPUT_DIR, PL_OUTPUT_DIR, dry_run)

    # ── 4. Create backward-compat symlinks for storage paths ──────────────────
    print("\n[ 4/7 ] Create backward-compat symlinks (storage/data, storage/output)")
    # Remove now-empty src dirs before symlinking
    for old_dir in [OLD_DATA_DIR, OLD_OUTPUT_DIR]:
        if old_dir.exists() and not old_dir.is_symlink() and old_dir.is_dir():
            remaining = list(old_dir.iterdir())
            if not remaining:
                log(f"  RMDIR {old_dir} (empty after move)", dry_run)
                if not dry_run:
                    old_dir.rmdir()
    # Symlink targets are relative to the storage/ directory
    make_symlink(OLD_DATA_DIR, "tenants/pl/data", dry_run)
    make_symlink(OLD_OUTPUT_DIR, "tenants/pl/output", dry_run)

    # ── 5. Move credentials ────────────────────────────────────────────────────
    print("\n[ 5/7 ] Move credentials → credentials/pl/")
    move_file(OLD_CLIENT_SECRETS, PL_CREDS_DIR / "client_secrets.json", dry_run)
    move_file(OLD_TOKEN, PL_CREDS_DIR / "token.json", dry_run)
    # Backward-compat symlinks (relative to credentials/)
    make_symlink(OLD_CLIENT_SECRETS, "pl/client_secrets.json", dry_run)
    make_symlink(OLD_TOKEN, "pl/token.json", dry_run)

    # ── 6. Inject timezone into pl settings.json ───────────────────────────────
    print("\n[ 6/7 ] Inject timezone into pl settings.json")
    inject_timezone(PL_DATA_DIR / "settings.json", "Europe/Warsaw", dry_run)

    # ── 7. Delete stale webapp/settings.json ──────────────────────────────────
    print("\n[ 7/7 ] Delete stale webapp/settings.json")
    delete_file(WEBAPP_SETTINGS, dry_run)

    print(f"\n{'=== DRY RUN complete — run without --dry-run to apply ===' if dry_run else '=== Migration complete ==='}\n")


def verify():
    """Quick sanity check after migration."""
    print("\n=== Verifying migration ===\n")
    checks = [
        (PL_DATA_DIR / "settings.json", "pl settings.json"),
        (PL_DATA_DIR / "prompts", "pl prompts dir"),
        (PL_OUTPUT_DIR, "pl output dir"),
        (PL_CREDS_DIR / "client_secrets.json", "pl client_secrets.json"),
        (PL_CREDS_DIR / "token.json", "pl token.json"),
        (OLD_DATA_DIR, "storage/data symlink"),
        (OLD_OUTPUT_DIR, "storage/output symlink"),
        (OLD_CLIENT_SECRETS, "credentials/client_secrets.json symlink"),
        (OLD_TOKEN, "credentials/token.json symlink"),
        (US_DATA_DIR, "us data dir"),
        (US_OUTPUT_DIR, "us output dir"),
    ]
    all_ok = True
    for path, label in checks:
        exists = path.exists() or path.is_symlink()
        status = "OK " if exists else "MISSING"
        is_link = " (symlink)" if path.is_symlink() else ""
        print(f"  {status}  {label}: {path}{is_link}")
        if not exists:
            all_ok = False

    # Check timezone in settings
    settings_path = PL_DATA_DIR / "settings.json"
    if settings_path.exists():
        data = json.loads(settings_path.read_text())
        tz = data.get("timezone", "MISSING")
        ok = tz == "Europe/Warsaw"
        print(f"  {'OK ' if ok else 'FAIL'} pl settings.timezone = {tz!r}")
        if not ok:
            all_ok = False

    # Check webapp/settings.json is gone
    gone = not WEBAPP_SETTINGS.exists()
    print(f"  {'OK ' if gone else 'FAIL'} webapp/settings.json deleted: {gone}")
    if not gone:
        all_ok = False

    print(f"\n{'All checks passed.' if all_ok else 'Some checks FAILED — review output above.'}\n")
    return all_ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate storage to per-tenant layout")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without touching files")
    parser.add_argument("--verify", action="store_true", help="Run post-migration verification only")
    args = parser.parse_args()

    if args.verify:
        ok = verify()
        sys.exit(0 if ok else 1)

    run(dry_run=args.dry_run)

    if not args.dry_run:
        verify()
