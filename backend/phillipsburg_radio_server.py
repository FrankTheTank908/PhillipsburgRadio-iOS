#!/usr/bin/env python3
"""
Phillipsburg Radio local backend server.

Runs on the Raspberry Pi image at http://0.0.0.0:5214 and serves:
- /health
- /current-feed.json
- /transcripts
- /events

Audio still comes from Broadcastify. This server only gives the app the current
Broadcastify audio URL and a foundation for transcript delivery.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from broadcastify_api_backend import (
    DEFAULT_API_BASE_URL,
    DEFAULT_ENV_FILES,
    DEFAULT_FEED_ID,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_TTL_SECONDS,
    build_feed_config,
    fetch_broadcastify_feed,
    load_first_existing_env_file,
    write_json,
)


DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_PORT = 5214
DEFAULT_TRANSCRIPTS_PATH = "/var/lib/phillipsburg-radio/transcripts.jsonl"
DEFAULT_MAX_TRANSCRIPTS = 200
DEFAULT_CACHE_SECONDS = 60


class BackendState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.loaded_env_file = load_first_existing_env_file(DEFAULT_ENV_FILES)
        self.api_key = required_env("BROADCASTIFY_API_KEY")
        self.feed_id = os.environ.get("BROADCASTIFY_FEED_ID", DEFAULT_FEED_ID).strip()
        self.api_base_url = os.environ.get("BROADCASTIFY_API_BASE_URL", DEFAULT_API_BASE_URL).strip()
        self.output_path = os.environ.get("OUTPUT_JSON_PATH", DEFAULT_OUTPUT_PATH).strip()
        self.transcripts_path = os.environ.get("TRANSCRIPTS_PATH", DEFAULT_TRANSCRIPTS_PATH).strip()
        self.ttl_seconds = int(os.environ.get("STREAM_URL_TTL_SECONDS", str(DEFAULT_TTL_SECONDS)))
        self.cache_seconds = int(os.environ.get("CACHE_SECONDS", str(DEFAULT_CACHE_SECONDS)))
        self.admin_token = os.environ.get("BACKEND_ADMIN_TOKEN", "").strip()
        self.last_config: Optional[Dict[str, Any]] = read_json_if_exists(self.output_path)
        self.last_refresh_epoch = 0.0
        self.last_error: Optional[str] = None
        self.logs: List[Dict[str, str]] = []
        self.log("info", "Backend initialized")

    def get_config(self, force: bool = False) -> Dict[str, Any]:
        now = time.time()
        with self.lock:
            if self.last_config and not force and now - self.last_refresh_epoch < self.cache_seconds:
                return self.last_config

        try:
            payload = fetch_broadcastify_feed(self.api_base_url, self.api_key, self.feed_id)
            config = build_feed_config(payload, self.feed_id, self.ttl_seconds)
            write_json(self.output_path, config)

            with self.lock:
                self.last_config = config
                self.last_refresh_epoch = now
                self.last_error = None
                self.log("info", f"Feed config refreshed for feed {config.get('feedId')}")

            return config
        except Exception as error:
            with self.lock:
                self.last_error = str(error)
                self.log("error", f"Feed config refresh failed: {error}")
                if self.last_config:
                    config = dict(self.last_config)
                    config["message"] = f"Using cached feed config because refresh failed: {error}"
                    return config
            raise

    def health(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "ok": self.last_error is None,
                "service": "phillipsburg-radio-backend",
                "feedId": self.feed_id,
                "port": server_port(),
                "loadedEnvFile": self.loaded_env_file,
                "hasApiKey": bool(self.api_key),
                "lastRefreshEpoch": self.last_refresh_epoch,
                "lastError": self.last_error,
                "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }

    def read_transcripts(self, limit: int = 50) -> List[Dict[str, Any]]:
        path = Path(self.transcripts_path)
        if not path.exists():
            return []

        rows: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def add_transcript(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        event = {
            "timestamp": payload.get("timestamp") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "text": str(payload.get("text") or "").strip(),
            "confidence": payload.get("confidence"),
            "keywords": payload.get("keywords") if isinstance(payload.get("keywords"), list) else [],
            "channel": payload.get("channel") or "Scanner",
        }

        if not event["text"]:
            raise ValueError("Transcript text is required")

        path = Path(self.transcripts_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

        self.log("info", "Transcript event saved")
        return event

    def log(self, level: str, message: str) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": level,
            "message": message,
        }
        self.logs.append(entry)
        if len(self.logs) > 250:
            del self.logs[: len(self.logs) - 250]


class Handler(BaseHTTPRequestHandler):
    server_version = "PhillipsburgRadioBackend/1.0"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_common_headers("text/plain")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        try:
            if parsed.path in {"/", "/health"}:
                self.respond_json(STATE.health())
                return

            if parsed.path in {"/current-feed.json", "/config"}:
                force = query.get("refresh", ["0"])[0] == "1" or query.get("force", ["0"])[0] == "1"
                self.respond_json(STATE.get_config(force=force))
                return

            if parsed.path == "/transcripts":
                limit = int(query.get("limit", ["50"])[0])
                limit = max(1, min(limit, DEFAULT_MAX_TRANSCRIPTS))
                self.respond_json({"events": STATE.read_transcripts(limit=limit)})
                return

            if parsed.path == "/events":
                self.respond_sse()
                return

            if parsed.path == "/admin/logs":
                if not self.is_admin_authorized():
                    self.respond_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                    return
                self.respond_json({"logs": STATE.logs[-100:]})
                return

            self.respond_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as error:
            STATE.log("error", f"Request failed for {self.path}: {error}")
            self.respond_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        try:
            if parsed.path == "/transcripts":
                if not self.is_admin_authorized():
                    self.respond_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                    return

                payload = self.read_json_body()
                event = STATE.add_transcript(payload)
                self.respond_json({"ok": True, "event": event})
                return

            if parsed.path == "/admin/refresh":
                if not self.is_admin_authorized():
                    self.respond_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                    return
                self.respond_json({"ok": True, "config": STATE.get_config(force=True)})
                return

            self.respond_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except ValueError as error:
            self.respond_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except Exception as error:
            STATE.log("error", f"POST failed for {self.path}: {error}")
            self.respond_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def respond_sse(self) -> None:
        events = STATE.read_transcripts(limit=25)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.send_common_headers(None)
        self.end_headers()

        if not events:
            self.wfile.write(b"event: heartbeat\n")
            self.wfile.write(b"data: {\"ok\":true}\n\n")
            return

        for event in events:
            self.wfile.write(b"event: transcript\n")
            self.wfile.write(f"data: {json.dumps(event)}\n\n".encode("utf-8"))

    def respond_json(self, payload: Dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_common_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_common_headers(self, content_type: Optional[str]) -> None:
        if content_type:
            self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Admin-Token")

    def read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        return json.loads(body)

    def is_admin_authorized(self) -> bool:
        expected = STATE.admin_token
        if not expected:
            return False

        authorization = self.headers.get("Authorization", "")
        bearer = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
        header_token = self.headers.get("X-Admin-Token", "")
        return bearer == expected or header_token == expected

    def log_message(self, format: str, *args: Any) -> None:
        STATE.log("info", format % args)


def read_json_if_exists(path_value: str) -> Optional[Dict[str, Any]]:
    path = Path(path_value)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def server_port() -> int:
    return int(os.environ.get("BACKEND_PORT", str(DEFAULT_PORT)))


def run() -> int:
    host = os.environ.get("BACKEND_BIND_HOST", DEFAULT_BIND_HOST)
    port = server_port()
    server = ThreadingHTTPServer((host, port), Handler)
    STATE.log("info", f"Listening on {host}:{port}")
    server.serve_forever()
    return 0


try:
    STATE = BackendState()
except Exception as startup_error:
    print(f"ERROR: {startup_error}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(run())
