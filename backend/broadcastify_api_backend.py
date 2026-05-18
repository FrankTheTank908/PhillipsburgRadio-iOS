#!/usr/bin/env python3
"""
Broadcastify domain-key backend updater for the Phillipsburg Radio Pi image.

The service reads config from the boot partition, loads the official
Broadcastify embed player for the approved backend domain key, extracts
the current playable audio URL, and writes app JSON locally for the Pi HTTP
server.
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
from typing import Any, Dict, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


DEFAULT_ENV_FILES = [
    "/boot/firmware/phillipsburg-radio.env",
    "/boot/phillipsburg-radio.env",
    "/etc/phillipsburg-radio/backend.env",
]

DEFAULT_AUDIO_API_URL = "https://api.broadcastify.com/audio/"
DEFAULT_EMBED_PLAYER_URL = "https://api.broadcastify.com/embed/player/"
DEFAULT_LISTENERS_URL_TEMPLATE = "http://api.broadcastify.com/listeners/feed/{feed_id}"
DEFAULT_REFERER = "http://example.invalid/"
DEFAULT_FEED_ID = "45951"
DEFAULT_FEED_TITLE = "Default Scanner Feed"
DEFAULT_BITRATE = 32
DEFAULT_OUTPUT_PATH = "/var/lib/phillipsburg-radio/current-feed.json"
DEFAULT_TTL_SECONDS = 300
DEFAULT_TIMEOUT_SECONDS = 20


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Phillipsburg Radio app JSON from the Broadcastify embed player.")
    parser.add_argument("--env-file", action="append", help="Config file to load. Can be provided more than once.")
    parser.add_argument("--dry-run", action="store_true", help="Print JSON after writing the local config file.")
    args = parser.parse_args()

    env_files = args.env_file or DEFAULT_ENV_FILES
    loaded_env_file = load_first_existing_env_file(env_files)

    api_key = required_env("BROADCASTIFY_API_KEY")
    feed_id = os.environ.get("BROADCASTIFY_FEED_ID", DEFAULT_FEED_ID).strip()
    embed_player_url = embed_player_url_from_env()
    output_path = os.environ.get("OUTPUT_JSON_PATH", DEFAULT_OUTPUT_PATH).strip()
    ttl_seconds = int(os.environ.get("STREAM_URL_TTL_SECONDS", str(DEFAULT_TTL_SECONDS)))

    feed_payload = fetch_broadcastify_feed(embed_player_url, api_key, feed_id)
    config = build_feed_config(feed_payload, feed_id, ttl_seconds)
    write_json(output_path, config)

    if args.dry_run:
        print(json.dumps({"loadedEnvFile": loaded_env_file, "config": config}, indent=2))
        return 0

    print(f"Wrote current feed config to {output_path}")
    return 0


def load_first_existing_env_file(paths: Iterable[str]) -> Optional[str]:
    for raw_path in paths:
        path = Path(raw_path)
        if path.exists():
            load_env_file(path)
            return str(path)
    return None


def load_env_file(path: Path) -> None:
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


def embed_player_url_from_env() -> str:
    configured = os.environ.get("BROADCASTIFY_EMBED_PLAYER_URL", "").strip()
    if configured:
        return configured

    legacy = os.environ.get("BROADCASTIFY_API_BASE_URL", "").strip()
    if "/embed/player" in legacy:
        return legacy

    return DEFAULT_EMBED_PLAYER_URL


def fetch_broadcastify_feed(embed_player_url: str, api_key: str, feed_id: str) -> Dict[str, Any]:
    query = urlencode(
        {
            "feedId": feed_id,
            "html5": "1",
            "as": "1",
            "stats": "1",
            "bg": "000000",
            "fg": "FFFFFF",
            "key": api_key,
        }
    )
    separator = "&" if "?" in embed_player_url else "?"
    url = f"{embed_player_url}{separator}{query}"

    player_html = fetch_text(url, embed_headers())
    stream_url = extract_stream_url_from_embed_html(player_html, url)
    listeners = fetch_listener_count(feed_id)

    return {
        "feed": {
            "feedId": feed_id,
            "title": DEFAULT_FEED_TITLE,
            "status": "online",
            "listeners": listeners,
            "bitrate": DEFAULT_BITRATE,
            "streamUrl": stream_url,
        }
    }


def fetch_broadcastify_catalog(
    action: str,
    api_key: str,
    params: Optional[Dict[str, Any]] = None,
    api_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    query_params = {
        "a": action,
        "type": "json",
        "key": api_key,
    }
    for key, value in (params or {}).items():
        if value is None or str(value).strip() == "":
            continue
        query_params[key] = value

    base_url = (api_base_url or os.environ.get("BROADCASTIFY_AUDIO_API_URL", DEFAULT_AUDIO_API_URL)).strip()
    separator = "&" if "?" in base_url else "?"
    url = f"{base_url}{separator}{urlencode(query_params)}"
    body = fetch_text(
        url,
        {
            "Accept": "application/json,*/*",
            "User-Agent": "PhillipsburgRadioBackend/1.0",
        },
    )
    try:
        return json.loads(body)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Broadcastify catalog API did not return JSON: {body[:240]}") from error


def normalize_catalog_response(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_items = find_catalog_items(payload)
    items = [normalize_catalog_item(action, item) for item in raw_items if isinstance(item, dict)]
    return {
        "source": "broadcastify-live-audio-catalog",
        "action": action,
        "count": len(items),
        "items": items,
    }


def find_catalog_items(payload: Any) -> list[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    preferred_keys = [
        "countries",
        "Countries",
        "states",
        "States",
        "counties",
        "Counties",
        "feeds",
        "Feeds",
        "feed",
        "Feed",
        "items",
        "data",
    ]
    for key in preferred_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = find_catalog_items(value)
            if nested:
                return nested

    nested_items: list[Dict[str, Any]] = []
    for value in payload.values():
        if isinstance(value, list):
            nested_items.extend(item for item in value if isinstance(item, dict))
    return nested_items


def normalize_catalog_item(action: str, item: Dict[str, Any]) -> Dict[str, Any]:
    identifier = first_value(
        item,
        [
            "id",
            "feedId",
            "feed_id",
            "coid",
            "countryId",
            "stid",
            "stateId",
            "ctid",
            "countyId",
        ],
    )
    name = first_value(
        item,
        [
            "name",
            "title",
            "descr",
            "description",
            "countryName",
            "stateName",
            "countyName",
        ],
    )
    feed_id = first_value(item, ["feedId", "feed_id", "id"]) if action in {"feeds", "county", "feed"} else None
    return {
        "id": str(identifier or name or ""),
        "name": str(name or identifier or "Unknown"),
        "type": catalog_item_type(action),
        "feedId": str(feed_id) if feed_id is not None else None,
        "countryId": string_or_none(first_value(item, ["coid", "countryId", "country_id"])),
        "stateId": string_or_none(first_value(item, ["stid", "stateId", "state_id"])),
        "countyId": string_or_none(first_value(item, ["ctid", "countyId", "county_id"])),
        "genre": string_or_none(first_value(item, ["genre", "genreName", "genre_name"])),
        "status": string_or_none(first_value(item, ["status", "online"])),
        "listeners": number_or_none(first_value(item, ["listeners", "listenerCount", "listener_count"])),
        "bitrate": number_or_none(first_value(item, ["bitrate", "bitRate", "bit_rate"])),
        "subtitle": string_or_none(first_value(item, ["location", "county", "state", "country", "notes"])),
        "raw": item,
    }


def catalog_item_type(action: str) -> str:
    if action == "countries":
        return "country"
    if action == "states":
        return "state"
    if action == "counties":
        return "county"
    return "feed"


def string_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def embed_headers() -> Dict[str, str]:
    referer = os.environ.get("BROADCASTIFY_REFERER", DEFAULT_REFERER).strip() or DEFAULT_REFERER
    parsed = urlparse(referer)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else "http://example.invalid"
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Origin": origin,
        "Referer": referer,
        "User-Agent": "Mozilla/5.0 PhillipsburgRadioBackend/1.0",
    }


def fetch_text(url: str, headers: Dict[str, str]) -> str:
    request = Request(
        url,
        headers=headers,
    )

    try:
        with urlopen(request, timeout=timeout_seconds()) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Broadcastify embed player returned HTTP {response.status}: {body[:240]}")
            return body
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Broadcastify embed player returned HTTP {error.code}: {detail[:240]}. "
            "If this is 403, confirm the key matches BROADCASTIFY_REFERER."
        ) from error
    except URLError as error:
        raise RuntimeError(f"Could not call Broadcastify embed player: {error.reason}") from error


def extract_stream_url_from_embed_html(player_html: str, base_url: str) -> str:
    normalized = html.unescape(player_html).replace("\\/", "/")
    candidates = []

    attr_patterns = [
        r"""<(?:audio|source)\b[^>]*\bsrc=["']([^"']+)["']""",
        r"""(?:file|src|url)\s*[:=]\s*["']([^"']+)["']""",
    ]
    for pattern in attr_patterns:
        candidates.extend(re.findall(pattern, normalized, flags=re.IGNORECASE))

    candidates.extend(re.findall(r"""https?://[^\s"'<>\\)]+""", normalized, flags=re.IGNORECASE))

    for candidate in candidates:
        resolved = urljoin(base_url, candidate.strip())
        if is_probable_audio_url(resolved):
            return resolved

    raise RuntimeError(
        "Broadcastify embed player loaded, but no playable audio URL was found in the HTML. "
        "Open the feed owner Technicals page and confirm the embed-player code for this feed/key."
    )


def is_probable_audio_url(value: str) -> bool:
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    if not parsed.scheme.startswith("http"):
        return False

    rejected_extensions = (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico")
    if path.endswith(rejected_extensions):
        return False

    rejected_paths = (
        "/embed/player",
        "/feed-status/",
        "/listeners/feed/",
        "/listen/feed/",
    )
    if any(rejected in path for rejected in rejected_paths):
        return False

    if path.endswith((".mp3", ".m3u", ".m3u8", ".pls", ".aac")):
        return True

    return "broadcastify.com" in host and ("listen" in host or "audio" in host)


def fetch_listener_count(feed_id: str) -> Optional[int]:
    template = os.environ.get("BROADCASTIFY_LISTENERS_URL_TEMPLATE", DEFAULT_LISTENERS_URL_TEMPLATE).strip()
    if not template:
        return None

    url = template.format(feed_id=feed_id)
    try:
        body = fetch_text(
            url,
            {
                "Accept": "text/plain,application/json,*/*",
                "User-Agent": "PhillipsburgRadioBackend/1.0",
            },
        ).strip()
    except Exception:
        return None

    try:
        return int(body)
    except ValueError:
        try:
            data = json.loads(body)
            return number_or_none(data.get("listeners"))
        except Exception:
            return None


def build_feed_config(payload: Dict[str, Any], fallback_feed_id: str, ttl_seconds: int) -> Dict[str, Any]:
    feed = find_feed_object(payload)
    if not feed:
        raise RuntimeError("Broadcastify response did not include a feed object.")

    stream_url = resolve_stream_url(feed)
    now = datetime.now(timezone.utc)

    return {
        "feedId": str(first_value(feed, ["id", "feedId", "feed_id"]) or fallback_feed_id),
        "title": first_value(feed, ["descr", "description", "name", "title"]) or DEFAULT_FEED_TITLE,
        "status": normalize_status(first_value(feed, ["status", "online"])),
        "listeners": number_or_none(first_value(feed, ["listeners", "listenerCount", "listener_count"])),
        "bitrate": number_or_none(first_value(feed, ["bitrate", "bitRate", "bit_rate"])),
        "streamUrl": stream_url,
        "updatedAt": iso_z(now),
        "expiresAt": iso_z(now + timedelta(seconds=ttl_seconds)),
        "source": "broadcastify-embed-player-pi-backend",
        "message": None,
    }


def find_feed_object(payload: Any) -> Optional[Dict[str, Any]]:
    candidates = []
    if isinstance(payload, dict):
        candidates.extend(
            [
                payload.get("Feed"),
                payload.get("feed"),
                payload.get("feeds"),
                payload.get("Feeds"),
                payload.get("data"),
            ]
        )
    candidates.append(payload)

    for candidate in candidates:
        if isinstance(candidate, list) and candidate and isinstance(candidate[0], dict):
            return candidate[0]
        if isinstance(candidate, dict):
            nested_keys = {"Feed", "feed", "feeds", "Feeds", "data"}
            if any(key in candidate for key in nested_keys):
                continue
            return candidate
    return None


def resolve_stream_url(feed: Dict[str, Any]) -> str:
    direct_url = first_value(
        feed,
        [
            "streamUrl",
            "streamURL",
            "stream_url",
            "url",
            "listenUrl",
            "listenURL",
            "listen_url",
        ],
    )

    if direct_url and looks_like_url(str(direct_url)):
        return str(direct_url)

    mount = first_value(feed, ["mount", "mountPoint", "mountpoint", "mount_point"])
    relay = first_relay(feed)

    if not mount or not relay or not relay.get("host"):
        raise RuntimeError(
            "Broadcastify response did not include a direct stream URL or relay/mount fields."
        )

    if looks_like_url(str(mount)):
        return str(mount)

    port = str(first_value(relay, ["port"]) or "").strip()
    scheme = "https" if port == "443" else "http"
    host = re.sub(r"^https?://", "", str(relay["host"])).rstrip("/")
    normalized_mount = str(mount) if str(mount).startswith("/") else f"/{mount}"
    port_part = f":{port}" if port and port not in {"80", "443"} else ""
    return f"{scheme}://{host}{port_part}{normalized_mount}"


def first_relay(feed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    relays = first_value(feed, ["Relays", "relays", "Relay", "relay"])
    if isinstance(relays, list) and relays and isinstance(relays[0], dict):
        return relays[0]
    if isinstance(relays, dict):
        return relays

    host = first_value(feed, ["host", "server", "relayHost", "relay_host"])
    port = first_value(feed, ["port", "serverPort", "server_port", "relayPort", "relay_port"])
    if host:
        return {"host": host, "port": port}
    return None


def first_value(mapping: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def normalize_status(value: Any) -> str:
    normalized = str(value).strip().lower()
    if value is True or normalized in {"1", "online", "true"}:
        return "online"
    if value is False or normalized in {"0", "offline", "false"}:
        return "offline"
    return "unknown" if value is None else str(value)


def number_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def looks_like_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def iso_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def write_json(path_value: str, payload: Dict[str, Any]) -> None:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def timeout_seconds() -> int:
    return int(os.environ.get("REQUEST_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
