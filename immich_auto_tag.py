#!/usr/bin/env python3
"""
immich_auto_tag.py

Creates hierarchical tags in Immich based on an external library's folder
structure. Unlike immich-folder-album-creator (which flattens folder levels
into one album name), this script preserves Immich's native "/" tag nesting,
so e.g. a folder structure Trip/2026/06 can become the nested tag Trip/2026,
with the "06" level skipped.

Configuration is via environment variables (see .env.example / README.md).
"""

import os
import re
import sys
import fnmatch
import logging
from collections import defaultdict

import requests

# --- Configuration via environment variables ---
API_URL = os.environ.get("API_URL", "").rstrip("/")
API_KEY = os.environ.get("API_KEY", "")
ROOT_PATH = os.environ.get("ROOT_PATH", "/mnt/photos").rstrip("/")

# How many folder levels (from the top) to turn into nested tags.
# 1 = only the top-level folder becomes a tag.
# 2 = top-level + one sub-level (default), etc.
TAG_LEVELS = int(os.environ.get("TAG_LEVELS", "2"))

# Optional per-level regex filters: TAG_LEVEL_2_REGEX, TAG_LEVEL_3_REGEX, ...
# If set for a given level, that folder name is only added to the tag
# hierarchy when it matches; if it does NOT match, the hierarchy stops
# at the previous level for that asset (deeper levels are never tagged).
# Example: TAG_LEVEL_2_REGEX=^\d{4}$  -> only year-looking folders become
# part of the tag; a "06" (month) folder underneath is ignored, and the
# asset is tagged with just the level-1 tag instead.
LEVEL_REGEXES = {}
for i in range(1, TAG_LEVELS + 1):
    pattern = os.environ.get(f"TAG_LEVEL_{i}_REGEX")
    if pattern:
        LEVEL_REGEXES[i] = re.compile(pattern)

# Colon-separated glob-style patterns (or plain literals, matched as
# substrings anywhere in the path) to exclude assets entirely.
IGNORE_PATTERNS = [p for p in os.environ.get("IGNORE", "").split(":") if p]

# Colon-separated glob-style patterns to include only matching assets.
# If empty, all assets under ROOT_PATH are considered.
PATH_FILTER_PATTERNS = [p for p in os.environ.get("PATH_FILTER", "").split(":") if p]

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "50"))
PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "1000"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s level=%(levelname)s msg=%(message)s",
)
log = logging.getLogger("immich-auto-tag")

if not API_URL or not API_KEY:
    log.error("API_URL and API_KEY must be set")
    sys.exit(1)

HEADERS = {
    "x-api-key": API_KEY,
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def glob_to_regex(pattern: str) -> re.Pattern:
    """Convert a literal or glob-style pattern to a compiled regex.
    A plain literal (no wildcard chars) is treated as matching anywhere
    in the path, like immich-folder-album-creator does: '--ignore Feb'
    behaves like '--ignore **/*Feb*/**'.
    """
    if not any(c in pattern for c in "*?["):
        pattern = f"**/*{pattern}*/**"
    # fnmatch.translate handles *, ?, [seq] but not **; expand ** first.
    parts = pattern.split("**")
    regex_parts = [fnmatch.translate(p).replace(r"\Z", "").rstrip("$") for p in parts]
    regex = ".*".join(regex_parts) + r"\Z"
    return re.compile(regex, re.DOTALL)


IGNORE_REGEXES = [glob_to_regex(p) for p in IGNORE_PATTERNS]
PATH_FILTER_REGEXES = [glob_to_regex(p) for p in PATH_FILTER_PATTERNS]


def fetch_all_assets():
    assets = []
    page = 1
    while True:
        resp = requests.post(
            f"{API_URL}/search/metadata",
            headers=HEADERS,
            json={"page": page, "size": PAGE_SIZE},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("assets", {}).get("items", [])
        if not items:
            break
        assets.extend(items)
        next_page = data.get("assets", {}).get("nextPage")
        log.info("Fetched page %s, %s assets so far", page, len(assets))
        if not next_page:
            break
        page = int(next_page)
    return assets


def compute_tag(relative_path: str):
    """Return the tag name (with '/' nesting) for a relative asset path,
    or None if the asset should be skipped entirely."""
    parts = relative_path.split("/")[:-1]  # drop filename
    if not parts:
        return None

    tag_parts = []
    for level, name in enumerate(parts, start=1):
        if level > TAG_LEVELS:
            break
        regex = LEVEL_REGEXES.get(level)
        if regex and not regex.match(name):
            # this level doesn't qualify -> stop building the hierarchy here
            break
        tag_parts.append(name)

    if not tag_parts:
        return None
    return "/".join(tag_parts)


def is_ignored(relative_path: str) -> bool:
    return any(r.match(relative_path) for r in IGNORE_REGEXES)


def passes_path_filter(relative_path: str) -> bool:
    if not PATH_FILTER_REGEXES:
        return True
    return any(r.match(relative_path) for r in PATH_FILTER_REGEXES)


def upsert_tag(tag_name: str) -> str:
    resp = requests.put(
        f"{API_URL}/tags",
        headers=HEADERS,
        json={"tags": [tag_name]},
        timeout=20,
    )
    resp.raise_for_status()
    result = resp.json()
    for tag in result:
        if tag.get("value") == tag_name:
            return tag["id"]
    return result[0]["id"]


def bulk_tag_assets(tag_id: str, asset_ids: list):
    for i in range(0, len(asset_ids), CHUNK_SIZE):
        chunk = asset_ids[i:i + CHUNK_SIZE]
        if DRY_RUN:
            log.info("[DRY RUN] Would tag %s assets (chunk %s-%s)", len(chunk), i, i + len(chunk))
            continue
        resp = requests.put(
            f"{API_URL}/tags/assets",
            headers=HEADERS,
            json={"tagIds": [tag_id], "assetIds": chunk},
            timeout=60,
        )
        resp.raise_for_status()
        log.info("Tagged %s assets (chunk %s-%s)", len(chunk), i, i + len(chunk))


def main():
    log.info("Config: ROOT_PATH=%s TAG_LEVELS=%s LEVEL_REGEXES=%s IGNORE=%s PATH_FILTER=%s DRY_RUN=%s",
              ROOT_PATH, TAG_LEVELS, {k: p.pattern for k, p in LEVEL_REGEXES.items()},
              IGNORE_PATTERNS, PATH_FILTER_PATTERNS, DRY_RUN)

    log.info("Fetching all assets from %s", API_URL)
    assets = fetch_all_assets()
    log.info("%s assets fetched", len(assets))

    tag_to_assets = defaultdict(list)
    skipped = 0
    for asset in assets:
        original_path = asset.get("originalPath") or asset.get("exifInfo", {}).get("originalPath")
        if not original_path or not original_path.startswith(ROOT_PATH + "/"):
            skipped += 1
            continue
        relative = original_path[len(ROOT_PATH) + 1:]

        if is_ignored(relative):
            skipped += 1
            continue
        if not passes_path_filter(relative):
            skipped += 1
            continue

        tag = compute_tag(relative)
        if tag is None:
            skipped += 1
            continue
        tag_to_assets[tag].append(asset["id"])

    log.info("%s distinct tags to create/update, %s assets skipped",
              len(tag_to_assets), skipped)

    for tag_name, asset_ids in tag_to_assets.items():
        log.info("Tag '%s': %s assets", tag_name, len(asset_ids))
        if DRY_RUN:
            continue
        tag_id = upsert_tag(tag_name)
        bulk_tag_assets(tag_id, asset_ids)

    log.info("Done!")


if __name__ == "__main__":
    main()
