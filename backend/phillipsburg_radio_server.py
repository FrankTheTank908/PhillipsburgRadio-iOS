#!/usr/bin/env python3
"""
Phillipsburg Radio local backend server.

Runs on the Raspberry Pi image at http://0.0.0.0:80 by default and serves:
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
import uuid
import base64
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from broadcastify_api_backend import (
    DEFAULT_AUDIO_API_URL,
    DEFAULT_EMBED_PLAYER_URL,
    DEFAULT_ENV_FILES,
    DEFAULT_FEED_ID,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_TTL_SECONDS,
    build_feed_config,
    embed_player_url_from_env,
    fetch_broadcastify_catalog,
    fetch_broadcastify_feed,
    load_first_existing_env_file,
    normalize_catalog_response,
    write_json,
)
from radioreference_api import (
    METHOD_SPECS,
    RadioReferenceClient,
    method_catalog,
    redact_secret_fields,
)


DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_PORT = 80
DEFAULT_TRANSCRIPTS_PATH = "/var/lib/phillipsburg-radio/transcripts.jsonl"
DEFAULT_INCIDENTS_PATH = "/var/lib/phillipsburg-radio/incidents.jsonl"
DEFAULT_INCIDENT_STATE_PATH = "/var/lib/phillipsburg-radio/incident-state.json"
DEFAULT_ENTITLEMENTS_PATH = "/var/lib/phillipsburg-radio/entitlements.json"
DEFAULT_PLAY_SESSIONS_PATH = "/var/lib/phillipsburg-radio/play-sessions.json"
DEFAULT_PIPELINE_STATUS_PATH = "/var/lib/phillipsburg-radio/transcript-pipeline-status.json"
DEFAULT_MAX_TRANSCRIPTS = 200
DEFAULT_MAX_INCIDENTS = 200
DEFAULT_CACHE_SECONDS = 60
DEFAULT_PUBLIC_BASE_URL = "http://example.invalid"


class BackendState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.loaded_env_file = load_first_existing_env_file(DEFAULT_ENV_FILES)
        self.api_key = required_env("BROADCASTIFY_API_KEY")
        self.catalog_api_key = os.environ.get("BROADCASTIFY_CATALOG_API_KEY", "").strip() or self.api_key
        self.feed_id = os.environ.get("BROADCASTIFY_FEED_ID", DEFAULT_FEED_ID).strip()
        self.catalog_api_url = os.environ.get("BROADCASTIFY_AUDIO_API_URL", DEFAULT_AUDIO_API_URL).strip() or DEFAULT_AUDIO_API_URL
        self.embed_player_url = embed_player_url_from_env() or DEFAULT_EMBED_PLAYER_URL
        self.output_path = os.environ.get("OUTPUT_JSON_PATH", DEFAULT_OUTPUT_PATH).strip()
        self.transcripts_path = os.environ.get("TRANSCRIPTS_PATH", DEFAULT_TRANSCRIPTS_PATH).strip()
        self.incidents_path = os.environ.get("INCIDENTS_PATH", DEFAULT_INCIDENTS_PATH).strip()
        self.incident_state_path = os.environ.get("INCIDENT_STATE_PATH", DEFAULT_INCIDENT_STATE_PATH).strip()
        self.entitlements_path = os.environ.get("ENTITLEMENTS_PATH", DEFAULT_ENTITLEMENTS_PATH).strip()
        self.play_sessions_path = os.environ.get("PLAY_SESSIONS_PATH", DEFAULT_PLAY_SESSIONS_PATH).strip()
        self.pipeline_status_path = os.environ.get("PIPELINE_STATUS_PATH", DEFAULT_PIPELINE_STATUS_PATH).strip()
        self.ttl_seconds = int(os.environ.get("STREAM_URL_TTL_SECONDS", str(DEFAULT_TTL_SECONDS)))
        self.cache_seconds = int(os.environ.get("CACHE_SECONDS", str(DEFAULT_CACHE_SECONDS)))
        self.public_base_url = os.environ.get("PUBLIC_BASE_URL", DEFAULT_PUBLIC_BASE_URL).strip() or DEFAULT_PUBLIC_BASE_URL
        self.admin_token = os.environ.get("BACKEND_ADMIN_TOKEN", "").strip()
        self.allow_debug_admin_without_token = env_bool("ALLOW_DEBUG_ADMIN_WITHOUT_TOKEN", True)
        self.allow_debug_ad_access = env_bool("ALLOW_DEBUG_AD_ACCESS", True)
        self.require_play_token_for_stream = env_bool("REQUIRE_PLAY_TOKEN_FOR_STREAM", False)
        self.app_store_debug_trust_client = env_bool("APP_STORE_DEBUG_TRUST_CLIENT", False)
        self.premium_product_ids = {
            value.strip()
            for value in os.environ.get("PREMIUM_PRODUCT_IDS", "com.frankpinheiro.scanner.premium.monthly").split(",")
            if value.strip()
        }
        self.radio_reference = RadioReferenceClient.from_env()
        self.last_config: Optional[Dict[str, Any]] = read_json_if_exists(self.output_path)
        self.feed_config_cache: Dict[str, Dict[str, Any]] = {}
        if self.last_config:
            self.feed_config_cache[str(self.last_config.get("feedId") or self.feed_id)] = self.last_config
        self.catalog_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
        self.last_refresh_epoch = 0.0
        self.last_error: Optional[str] = None
        self.logs: List[Dict[str, str]] = []
        self.log("info", "Backend initialized")

    def get_config(self, force: bool = False, feed_id: Optional[str] = None, play_token: Optional[str] = None) -> Dict[str, Any]:
        now = time.time()
        requested_feed_id = str(feed_id or self.feed_id).strip() or self.feed_id
        if self.require_play_token_for_stream and not self.is_play_token_valid(str(play_token or ""), requested_feed_id):
            raise PermissionError("A valid play session is required for this feed.")
        with self.lock:
            cached = self.feed_config_cache.get(requested_feed_id)
            if cached and not force and now - self.last_refresh_epoch < self.cache_seconds:
                return cached

        try:
            payload = fetch_broadcastify_feed(self.embed_player_url, self.api_key, requested_feed_id)
            config = build_feed_config(payload, requested_feed_id, self.ttl_seconds)
            if requested_feed_id == self.feed_id:
                write_json(self.output_path, config)

            with self.lock:
                self.last_config = config
                self.feed_config_cache[requested_feed_id] = config
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
                "hasDomainKey": bool(self.api_key),
                "hasApiKey": bool(self.api_key),
                "hasCatalogApiKey": bool(self.catalog_api_key),
                "hasRadioReferenceAuth": self.radio_reference.has_auth,
                "hasOpenAIKey": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
                "debugAdminNoAuth": self.allow_debug_admin_without_token,
                "debugAdAccess": self.allow_debug_ad_access,
                "requiresPlayToken": self.require_play_token_for_stream,
                "transcriptPipeline": self.pipeline_status(),
                "lastRefreshEpoch": self.last_refresh_epoch,
                "lastError": self.last_error,
                "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }

    def metadata(self) -> Dict[str, Any]:
        catalog = method_catalog()
        return {
            "service": "phillipsburg-radio-backend",
            "publicBaseUrl": self.public_base_url,
            "localFeedId": self.feed_id,
            "liveAudioSource": "Broadcastify approved domain-key embed player",
            "radioReference": {
                "configured": self.radio_reference.has_auth,
                "endpoint": self.radio_reference.endpoint,
                "wsdl": catalog["docs"]["wsdl"],
                "wiki": catalog["docs"]["wiki"],
                "methods": catalog["methods"],
            },
            "routes": [
                "/health",
                "/current-feed.json",
                "/current-feed.json?feedId=45951",
                "/catalog/countries",
                "/catalog/states?coid=1",
                "/catalog/counties?stid=34",
                "/catalog/feeds?ctid=1778",
                "/catalog/feed?feedId=45951",
                "/metadata",
                "/transcripts",
                "/incidents",
                "/access/play-session",
                "/entitlements/apple/verify",
                "/radio-reference/methods",
                "/radio-reference/countries",
                "/radio-reference/country?coid=1",
                "/radio-reference/state?stid=34",
                "/radio-reference/county?ctid=1778",
                "/radio-reference/zipcode?zipcode=08865",
                "/radio-reference/user-feeds",
            ],
            "notes": [
                "The iPhone app only talks to this Pi backend.",
                "RadioReference SOAP is for database metadata and account feed details.",
                "Completed-call transcripts are produced by the Pi transcript pipeline when OPENAI_API_KEY is configured.",
                "Broadcastify live audio and AI/ML use are subject to Broadcastify licensing.",
                "Purchase validation must be server-side before this becomes a public freemium app.",
            ],
        }

    def catalog(self, action: str, params: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
        cache_key = json.dumps({"action": action, "params": params}, sort_keys=True)
        now = time.time()
        with self.lock:
            cached = self.catalog_cache.get(cache_key)
            if cached and not force and now - cached[0] < self.cache_seconds:
                return cached[1]

        payload = fetch_broadcastify_catalog(action, self.catalog_api_key, params, self.catalog_api_url)
        normalized = normalize_catalog_response(action, payload)
        normalized["query"] = params
        with self.lock:
            self.catalog_cache[cache_key] = (now, normalized)
            self.log("info", f"Catalog refreshed action={action} count={normalized.get('count')}")
        return normalized

    def read_transcripts(self, limit: int = 50) -> List[Dict[str, Any]]:
        return read_jsonl_tail(self.transcripts_path, limit)

    def read_incident_summaries(self, limit: int = 25) -> List[Dict[str, Any]]:
        state = read_json_if_exists(self.incident_state_path) or {}
        incidents = state.get("incidents") if isinstance(state.get("incidents"), list) else []
        return incidents[:limit]

    def pipeline_status(self) -> Dict[str, Any]:
        return read_json_if_exists(self.pipeline_status_path) or {
            "ok": False,
            "state": "not-started",
            "message": "Transcript pipeline has not written status yet.",
        }

    def add_transcript(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        event = {
            "id": payload.get("id") or str(uuid.uuid4()),
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

    def read_incidents(self, limit: int = 50) -> List[Dict[str, Any]]:
        return read_jsonl_tail(self.incidents_path, limit)

    def add_incident(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        message = {
            "id": payload.get("id") or str(uuid.uuid4()),
            "timestamp": payload.get("timestamp") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "author": str(payload.get("author") or "Local Debug").strip(),
            "text": str(payload.get("text") or "").strip(),
            "tags": payload.get("tags") if isinstance(payload.get("tags"), list) else [],
            "channel": payload.get("channel") or "Incident Chat",
        }

        if not message["text"]:
            raise ValueError("Incident message text is required")

        path = Path(self.incidents_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(message) + "\n")

        self.log("info", "Incident message saved")
        return message

    def verify_apple_entitlement(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        signed_transaction = str(payload.get("signedTransactionInfo") or "").strip()
        product_id = str(payload.get("productId") or "").strip()
        transaction_id = str(payload.get("transactionId") or "").strip()
        account_token = str(payload.get("appAccountToken") or payload.get("deviceAccountToken") or "").strip()

        if not signed_transaction:
            raise ValueError("signedTransactionInfo is required")
        if product_id and product_id not in self.premium_product_ids:
            raise ValueError("Unknown premium product id")

        decoded_payload = decode_unverified_jws_payload(signed_transaction)
        product_id = product_id or str(decoded_payload.get("productId") or "")
        transaction_id = transaction_id or str(decoded_payload.get("transactionId") or "")
        original_transaction_id = str(decoded_payload.get("originalTransactionId") or transaction_id)
        expires_ms = int(decoded_payload.get("expiresDate") or 0)
        expires_at = iso_from_millis(expires_ms) if expires_ms else None
        is_known_product = product_id in self.premium_product_ids
        is_expired = bool(expires_ms and expires_ms < int(time.time() * 1000))
        active = bool(is_known_product and not is_expired and self.app_store_debug_trust_client)
        verification_state = "debug-client-trusted" if self.app_store_debug_trust_client else "server-validation-required"

        record = {
            "accountToken": account_token,
            "productId": product_id,
            "transactionId": transaction_id,
            "originalTransactionId": original_transaction_id,
            "expiresAt": expires_at,
            "active": active,
            "verificationState": verification_state,
            "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        if active:
            entitlements = read_json_if_exists(self.entitlements_path) or {"apple": {}}
            apple = entitlements.setdefault("apple", {})
            apple[account_token or original_transaction_id] = record
            write_json(self.entitlements_path, entitlements)

        message = (
            "Debug trust accepted the StoreKit transaction."
            if active
            else "Server-side Apple transaction validation is not configured; do not grant production entitlement from client data."
        )
        self.log("info", f"Apple entitlement checked product={product_id} state={verification_state}")
        return {"ok": True, "active": active, "message": message, "entitlement": record}

    def play_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        account_token = str(payload.get("appAccountToken") or payload.get("deviceAccountToken") or "").strip()
        feed_id = str(payload.get("feedId") or self.feed_id).strip()
        if self.has_active_entitlement(account_token):
            return self.create_play_session(feed_id=feed_id, account_token=account_token, reason="premium")
        if self.allow_debug_ad_access:
            return self.create_play_session(feed_id=feed_id, account_token=account_token, reason="debug-ad-session")
        return {"ok": True, "allowed": False, "reason": "premium-or-rewarded-ad-required", "feedId": feed_id}

    def create_play_session(self, feed_id: str, account_token: str, reason: str) -> Dict[str, Any]:
        expires_ms = int(time.time() * 1000) + 30 * 60 * 1000
        token = uuid.uuid4().hex
        sessions = read_json_if_exists(self.play_sessions_path) or {"sessions": {}}
        session = {
            "token": token,
            "feedId": feed_id,
            "accountToken": account_token,
            "reason": reason,
            "expiresAt": iso_from_millis(expires_ms),
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        sessions.setdefault("sessions", {})[token] = session
        write_json(self.play_sessions_path, sessions)
        self.log("info", f"Play session issued feed={feed_id} reason={reason}")
        return {
            "ok": True,
            "allowed": True,
            "reason": reason,
            "feedId": feed_id,
            "playToken": token,
            "expiresAt": session["expiresAt"],
        }

    def is_play_token_valid(self, token: str, feed_id: str) -> bool:
        if not token:
            return False
        sessions = read_json_if_exists(self.play_sessions_path) or {}
        session = (sessions.get("sessions") or {}).get(token)
        if not isinstance(session, dict):
            return False
        if str(session.get("feedId") or "") != feed_id:
            return False
        try:
            expires_at = str(session.get("expiresAt") or "").replace("Z", "+00:00")
            return datetime.fromisoformat(expires_at) > datetime.now(timezone.utc)
        except ValueError:
            return False

    def has_active_entitlement(self, account_token: str) -> bool:
        if not account_token:
            return False
        entitlements = read_json_if_exists(self.entitlements_path) or {}
        record = (entitlements.get("apple") or {}).get(account_token)
        if not isinstance(record, dict) or not record.get("active"):
            return False
        expires_at = record.get("expiresAt")
        if not expires_at:
            return True
        try:
            normalized = expires_at.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized) > datetime.now(timezone.utc)
        except ValueError:
            return False

    def radio_reference_methods(self) -> Dict[str, Any]:
        catalog = method_catalog()
        catalog["configured"] = self.radio_reference.has_auth
        return catalog

    def call_radio_reference(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        data = self.radio_reference.call_method(method, params)
        return {
            "method": method,
            "data": redact_secret_fields(data),
        }

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
                feed_id = query.get("feedId", query.get("feed_id", [""]))[0].strip() or None
                play_token = query.get("playToken", query.get("play_token", [""]))[0].strip() or None
                self.respond_json(STATE.get_config(force=force, feed_id=feed_id, play_token=play_token))
                return

            if parsed.path.startswith("/catalog/"):
                self.respond_json(self.handle_catalog_get(parsed.path, query))
                return

            if parsed.path in {"/metadata", "/radio-reference", "/radioreference"}:
                self.respond_json(STATE.metadata())
                return

            if parsed.path.startswith("/radio-reference/") or parsed.path.startswith("/radioreference/"):
                self.respond_json(self.handle_radio_reference_get(parsed.path, query))
                return

            if parsed.path == "/transcripts":
                limit = int(query.get("limit", ["50"])[0])
                limit = max(1, min(limit, DEFAULT_MAX_TRANSCRIPTS))
                incident_limit = int(query.get("incidentLimit", ["25"])[0])
                incident_limit = max(1, min(incident_limit, DEFAULT_MAX_INCIDENTS))
                self.respond_json(
                    {
                        "events": STATE.read_transcripts(limit=limit),
                        "incidents": STATE.read_incident_summaries(limit=incident_limit),
                        "pipeline": STATE.pipeline_status(),
                    }
                )
                return

            if parsed.path == "/incidents":
                limit = int(query.get("limit", ["50"])[0])
                limit = max(1, min(limit, DEFAULT_MAX_INCIDENTS))
                self.respond_json({"messages": STATE.read_incidents(limit=limit)})
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
        except PermissionError as error:
            self.respond_json({"error": str(error)}, HTTPStatus.FORBIDDEN)
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

            if parsed.path == "/incidents":
                if not self.is_admin_authorized():
                    self.respond_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                    return

                payload = self.read_json_body()
                message = STATE.add_incident(payload)
                self.respond_json({"ok": True, "message": message})
                return

            if parsed.path == "/admin/refresh":
                if not self.is_admin_authorized():
                    self.respond_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                    return
                payload = self.read_json_body()
                feed_id = str(payload.get("feedId") or "").strip() or None
                self.respond_json({"ok": True, "config": STATE.get_config(force=True, feed_id=feed_id)})
                return

            if parsed.path == "/entitlements/apple/verify":
                payload = self.read_json_body()
                self.respond_json(STATE.verify_apple_entitlement(payload))
                return

            if parsed.path == "/access/play-session":
                payload = self.read_json_body()
                self.respond_json(STATE.play_session(payload))
                return

            self.respond_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except ValueError as error:
            self.respond_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except PermissionError as error:
            self.respond_json({"error": str(error)}, HTTPStatus.FORBIDDEN)
        except Exception as error:
            STATE.log("error", f"POST failed for {self.path}: {error}")
            self.respond_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_radio_reference_get(self, path: str, query: Dict[str, List[str]]) -> Dict[str, Any]:
        name = path.strip("/").split("/", 1)[1]

        if name == "methods":
            return STATE.radio_reference_methods()

        if name == "countries":
            return STATE.call_radio_reference("getCountryList", {})

        if name == "country":
            return STATE.call_radio_reference("getCountryInfo", {"coid": query_required_int(query, "coid")})

        if name == "state":
            return STATE.call_radio_reference("getStateInfo", {"stid": query_required_int(query, "stid")})

        if name == "county":
            return STATE.call_radio_reference("getCountyInfo", {"ctid": query_required_int(query, "ctid")})

        if name in {"zipcode", "zip"}:
            return STATE.call_radio_reference("getZipcodeInfo", {"zipcode": query_required_int(query, "zipcode")})

        if name == "user-feeds":
            return STATE.call_radio_reference("getUserFeedBroadcasts", {})

        if name == "search":
            return STATE.call_radio_reference(*radio_reference_search_params(query))

        if name == "call":
            method = query_required(query, "method")
            if method not in METHOD_SPECS:
                raise ValueError(f"Unsupported RadioReference method: {method}")
            params = query_params_for_method(method, query)
            return STATE.call_radio_reference(method, params)

        raise ValueError(f"Unsupported RadioReference route: {name}")

    def handle_catalog_get(self, path: str, query: Dict[str, List[str]]) -> Dict[str, Any]:
        name = path.strip("/").split("/", 1)[1]
        force = query.get("refresh", ["0"])[0] == "1" or query.get("force", ["0"])[0] == "1"

        if name == "countries":
            return STATE.catalog("countries", {}, force=force)

        if name == "states":
            return STATE.catalog("states", {"coid": query_required_int(query, "coid")}, force=force)

        if name == "counties":
            return STATE.catalog("counties", {"stid": query_required_int(query, "stid")}, force=force)

        if name == "feeds":
            params: Dict[str, Any] = {}
            copy_optional_query(query, params, ["coid", "stid", "ctid", "top", "new", "s", "genre"])
            if "ctid" in params:
                return STATE.catalog("county", {"ctid": params["ctid"]}, force=force)
            return STATE.catalog("feeds", params, force=force)

        if name == "feed":
            return STATE.catalog("feed", {"feedId": query_required(query, "feedId")}, force=force)

        raise ValueError(f"Unsupported catalog route: {name}")

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
        if STATE.allow_debug_admin_without_token:
            return True
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


def read_jsonl_tail(path_value: str, limit: int) -> List[Dict[str, Any]]:
    path = Path(path_value)
    if not path.exists():
        return []

    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def query_required(query: Dict[str, List[str]], name: str) -> str:
    value = query.get(name, [""])[0].strip()
    if not value:
        raise ValueError(f"Missing required query parameter: {name}")
    return value


def query_required_int(query: Dict[str, List[str]], name: str) -> int:
    return int(query_required(query, name))


def copy_optional_query(query: Dict[str, List[str]], target: Dict[str, Any], names: List[str]) -> None:
    for name in names:
        value = query.get(name, [""])[0].strip()
        if value:
            target[name] = value


def radio_reference_search_params(query: Dict[str, List[str]]) -> tuple[str, Dict[str, Any]]:
    scope = query.get("scope", ["county"])[0].strip().lower()
    freq = query_required(query, "freq")
    tone = query.get("tone", [""])[0].strip()

    if scope == "county":
        return "searchCountyFreq", {"ctid": query_required_int(query, "ctid"), "freq": freq, "tone": tone}
    if scope == "state":
        return "searchStateFreq", {"stid": query_required_int(query, "stid"), "freq": freq, "tone": tone}
    if scope == "metro":
        return "searchMetroFreq", {"mid": query_required_int(query, "mid"), "freq": freq, "tone": tone}

    raise ValueError("RadioReference search scope must be county, state, or metro")


def query_params_for_method(method: str, query: Dict[str, List[str]]) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for param in METHOD_SPECS[method].params:
        name = param["name"]
        if name == "authInfo":
            continue
        params[name] = query_required(query, name)
    return params


def server_port() -> int:
    return int(os.environ.get("BACKEND_PORT", str(DEFAULT_PORT)))


def decode_unverified_jws_payload(jws_value: str) -> Dict[str, Any]:
    parts = jws_value.split(".")
    if len(parts) != 3:
        raise ValueError("signedTransactionInfo must be a compact JWS")
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode((payload + padding).encode("utf-8"))
    data = json.loads(decoded.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("signedTransactionInfo payload is not a JSON object")
    return data


def iso_from_millis(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


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
