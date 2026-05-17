#!/usr/bin/env python3
"""
Fetch a Broadcastify feed page, extract the current .mp3 stream URL, build the
app's JSON config, and upload it to the Cloudflare Worker.

This script intentionally uses only the Python standard library so it can run on
a Raspberry Pi without installing packages.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


MP3_URL_PATTERN = re.compile(
    r"(?P<url>(?:https?:)?//[^\s\"'<>]+?\.mp3(?:\?[^\s\"'<>]+)?)",
    re.IGNORECASE,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve and upload the current Broadcastify .mp3 URL.")
    parser.add_argument("--env-file", default="pi/broadcastify-resolver.env", help="Optional env file path.")
    parser.add_argument("--dry-run", action="store_true", help="Print JSON without uploading it.")
    parser.add_argument("--validate-stream", action="store_true", help="Open the extracted stream URL once to verify it responds.")
    args = parser.parse_args()

    load_env_file(args.env_file)

    feed_page_url = required_env("BROADCASTIFY_FEED_PAGE_URL")
    upload_url = os.environ.get("CONFIG_UPLOAD_URL", "").strip()
    upload_token = os.environ.get("CONFIG_UPLOAD_TOKEN", "").strip()
    feed_id = os.environ.get("FEED_ID", "phillipsburg_easton_public_safety").strip()
    source = os.environ.get("SOURCE", "broadcastify-page-resolver").strip()
    expires_seconds = int(os.environ.get("EXPIRES_SECONDS", "300"))
    output_json_path = os.environ.get("OUTPUT_JSON_PATH", "current-feed.json").strip()
    should_validate = args.validate_stream or env_bool("VALIDATE_STREAM", default=False)

    page_source = fetch_text(feed_page_url)
    stream_url = extract_mp3_url(page_source)

    if should_validate:
        validate_stream_url(stream_url)

    now = datetime.now(timezone.utc)
    config = {
        "feedId": feed_id,
        "streamUrl": stream_url,
        "updatedAt": now.isoformat().replace("+00:00", "Z"),
        "expiresAt": (now + timedelta(seconds=expires_seconds)).isoformat().replace("+00:00", "Z"),
        "source": source,
    }

    write_json(output_json_path, config)

    if args.dry_run:
        print(json.dumps(config, indent=2))
        return 0

    if not upload_url:
        raise RuntimeError("CONFIG_UPLOAD_URL is required unless --dry-run is used.")

    if not upload_token:
        raise RuntimeError("CONFIG_UPLOAD_TOKEN is required unless --dry-run is used.")

    upload_config(upload_url, upload_token, config)
    print(f"Uploaded current stream URL to {upload_url}")
    return 0


def load_env_file(path_value: str) -> None:
    path = Path(path_value)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required.")
    return value


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def fetch_text(url: str) -> str:
    request = Request(url, headers=request_headers(accept="text/html,application/xhtml+xml"))

    try:
        with urlopen(request, timeout=timeout_seconds()) as response:
            content_type = response.headers.get("content-type", "")
            charset = "utf-8"
            match = re.search(r"charset=([^;\s]+)", content_type, re.IGNORECASE)
            if match:
                charset = match.group(1)
            return response.read().decode(charset, errors="replace")
    except HTTPError as error:
        raise RuntimeError(f"Broadcastify page returned HTTP {error.code}.") from error
    except URLError as error:
        raise RuntimeError(f"Could not fetch Broadcastify page: {error.reason}") from error


def extract_mp3_url(page_source: str) -> str:
    normalized = html.unescape(page_source)
    normalized = normalized.replace("\\/", "/")

    matches = []
    seen = set()
    for match in MP3_URL_PATTERN.finditer(normalized):
        url = match.group("url").rstrip("\\")
        if url.startswith("//"):
            url = "https:" + url
        url = html.unescape(url)
        if url not in seen:
            seen.add(url)
            matches.append(url)

    if not matches:
        raise RuntimeError("No .mp3 URL was found in the Broadcastify page source.")

    if len(matches) > 1:
        print(f"Found {len(matches)} .mp3 URLs; using the first one.", file=sys.stderr)

    return matches[0]


def validate_stream_url(stream_url: str) -> None:
    parsed = urlparse(stream_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"Invalid stream URL: {stream_url}")

    request = Request(
        stream_url,
        headers={**request_headers(accept="audio/mpeg,*/*"), "Range": "bytes=0-1"},
        method="GET",
    )

    try:
        with urlopen(request, timeout=timeout_seconds()) as response:
            if response.status < 200 or response.status >= 400:
                raise RuntimeError(f"Stream URL returned HTTP {response.status}.")
    except HTTPError as error:
        raise RuntimeError(f"Stream URL returned HTTP {error.code}.") from error
    except URLError as error:
        raise RuntimeError(f"Could not validate stream URL: {error.reason}") from error


def write_json(path_value: str, config: Dict[str, str]) -> None:
    path = Path(path_value)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def upload_config(upload_url: str, token: str, config: Dict[str, str]) -> None:
    payload = json.dumps(config).encode("utf-8")
    request = Request(
        upload_url,
        data=payload,
        method="POST",
        headers={
            **request_headers(accept="application/json"),
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds()) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Config upload returned HTTP {response.status}.")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Config upload returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Could not upload config: {error.reason}") from error


def request_headers(accept: str) -> Dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": os.environ.get(
            "BROADCASTIFY_USER_AGENT",
            "PhillipsburgRadioResolver/1.0 (+https://github.com)",
        ),
    }

    cookie = os.environ.get("BROADCASTIFY_COOKIE", "").strip()
    if cookie:
        headers["Cookie"] = cookie

    return headers


def timeout_seconds() -> int:
    return int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "20"))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
