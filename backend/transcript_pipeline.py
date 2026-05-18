#!/usr/bin/env python3
"""
Completed-call recording, cleanup, transcription, and incident grouping.

This is intentionally post-call oriented. The live iPhone player keeps using the
Broadcastify stream URL directly, while this worker records short completed
chunks on the Pi, cleans radio noise with ffmpeg, skips silence, transcribes the
finished audio, and groups related chunks into recent incident records.
"""

from __future__ import annotations

import argparse
import json
import math
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from broadcastify_api_backend import (
    DEFAULT_EMBED_PLAYER_URL,
    DEFAULT_ENV_FILES,
    DEFAULT_FEED_ID,
    build_feed_config,
    embed_player_url_from_env,
    fetch_broadcastify_feed,
    load_first_existing_env_file,
)


DEFAULT_DATA_DIR = "/var/lib/phillipsburg-radio"
DEFAULT_RECORDINGS_DIR = f"{DEFAULT_DATA_DIR}/recordings"
DEFAULT_TRANSCRIPTS_PATH = f"{DEFAULT_DATA_DIR}/transcripts.jsonl"
DEFAULT_INCIDENT_STATE_PATH = f"{DEFAULT_DATA_DIR}/incident-state.json"
DEFAULT_PIPELINE_STATUS_PATH = f"{DEFAULT_DATA_DIR}/transcript-pipeline-status.json"
DEFAULT_ARCHIVE_STATE_PATH = f"{DEFAULT_DATA_DIR}/archive-state.json"
DEFAULT_CHUNK_SECONDS = 25
DEFAULT_SLEEP_SECONDS = 4
DEFAULT_MIN_SPEECH_SECONDS = 3.0
DEFAULT_MAX_INCIDENT_AGE_SECONDS = 45 * 60
DEFAULT_ARCHIVE_LOOKBACK_HOURS = 12
DEFAULT_ARCHIVE_POLL_SECONDS = 20 * 60
DEFAULT_OWNER_API_BASE_URL = "https://api.broadcastify.com/owner/"
DEFAULT_TRANSCRIBE_MODEL = "gpt-4o-transcribe"
DEFAULT_INCIDENT_MODEL = "gpt-5.5"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_AUDIO_FILTER = "highpass=f=250,lowpass=f=3600,afftdn=nf=-28,loudnorm=I=-18:TP=-2:LRA=11"
DEFAULT_CONTEXT_PROMPT = (
    "Public safety scanner audio. "
    "It may include police, fire, EMS, dispatch, units, street names, mile markers, channels, and incident updates. "
    "Transcribe uncertain words conservatively and do not invent details."
)


INCIDENT_TERMS = {
    "accident",
    "alarm",
    "ambulance",
    "arrest",
    "assist",
    "bridge",
    "cardiac",
    "chest",
    "crash",
    "domestic",
    "ems",
    "engine",
    "fall",
    "fire",
    "injury",
    "medical",
    "medic",
    "mva",
    "overdose",
    "police",
    "rescue",
    "smoke",
    "station",
    "structure",
    "traffic",
    "unconscious",
    "wires",
}

STOP_WORDS = {
    "a",
    "about",
    "all",
    "and",
    "are",
    "at",
    "be",
    "by",
    "for",
    "from",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "with",
    "you",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Record completed scanner chunks and build recent incidents.")
    parser.add_argument("--env-file", action="append", help="Config file to load. Can be provided more than once.")
    parser.add_argument("--once", action="store_true", help="Run one record/transcribe/analyze cycle.")
    parser.add_argument("--archive-once", action="store_true", help="Run one archive backfill cycle.")
    parser.add_argument("--skip-record", help="Process an existing audio file instead of recording a new chunk.")
    args = parser.parse_args()

    load_first_existing_env_file(args.env_file or DEFAULT_ENV_FILES)
    pipeline = TranscriptPipeline(PipelineConfig.from_env())

    if args.skip_record:
        pipeline.process_audio_file(Path(args.skip_record), started_at=utc_now(), ended_at=utc_now())
        return 0

    if args.archive_once:
        pipeline.process_archives_once()
        return 0

    if args.once:
        pipeline.run_once()
        return 0

    pipeline.run_forever()
    return 0


@dataclass(frozen=True)
class PipelineConfig:
    feed_id: str
    broadcastify_api_key: str
    embed_player_url: str
    recordings_dir: Path
    transcripts_path: Path
    incident_state_path: Path
    status_path: Path
    archive_state_path: Path
    chunk_seconds: int
    sleep_seconds: int
    min_speech_seconds: float
    max_incident_age_seconds: int
    archive_lookback_hours: int
    archive_poll_seconds: int
    openai_api_key: str
    openai_base_url: str
    transcribe_model: str
    incident_model: str
    audio_filter: str
    context_prompt: str
    enable_incident_ai: bool
    broadcastify_username: str
    broadcastify_password: str
    owner_api_base_url: str

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        return cls(
            feed_id=os.environ.get("BROADCASTIFY_FEED_ID", DEFAULT_FEED_ID).strip() or DEFAULT_FEED_ID,
            broadcastify_api_key=required_env("BROADCASTIFY_API_KEY"),
            embed_player_url=embed_player_url_from_env() or DEFAULT_EMBED_PLAYER_URL,
            recordings_dir=Path(os.environ.get("RECORDINGS_DIR", DEFAULT_RECORDINGS_DIR)),
            transcripts_path=Path(os.environ.get("TRANSCRIPTS_PATH", DEFAULT_TRANSCRIPTS_PATH)),
            incident_state_path=Path(os.environ.get("INCIDENT_STATE_PATH", DEFAULT_INCIDENT_STATE_PATH)),
            status_path=Path(os.environ.get("PIPELINE_STATUS_PATH", DEFAULT_PIPELINE_STATUS_PATH)),
            archive_state_path=Path(os.environ.get("ARCHIVE_STATE_PATH", DEFAULT_ARCHIVE_STATE_PATH)),
            chunk_seconds=int(os.environ.get("TRANSCRIPT_CHUNK_SECONDS", str(DEFAULT_CHUNK_SECONDS))),
            sleep_seconds=int(os.environ.get("TRANSCRIPT_SLEEP_SECONDS", str(DEFAULT_SLEEP_SECONDS))),
            min_speech_seconds=float(os.environ.get("MIN_SPEECH_SECONDS", str(DEFAULT_MIN_SPEECH_SECONDS))),
            max_incident_age_seconds=int(
                os.environ.get("MAX_INCIDENT_AGE_SECONDS", str(DEFAULT_MAX_INCIDENT_AGE_SECONDS))
            ),
            archive_lookback_hours=int(os.environ.get("ARCHIVE_LOOKBACK_HOURS", str(DEFAULT_ARCHIVE_LOOKBACK_HOURS))),
            archive_poll_seconds=int(os.environ.get("ARCHIVE_POLL_SECONDS", str(DEFAULT_ARCHIVE_POLL_SECONDS))),
            openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            openai_base_url=os.environ.get("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).rstrip("/"),
            transcribe_model=os.environ.get("OPENAI_TRANSCRIBE_MODEL", DEFAULT_TRANSCRIBE_MODEL).strip()
            or DEFAULT_TRANSCRIBE_MODEL,
            incident_model=os.environ.get("OPENAI_INCIDENT_MODEL", DEFAULT_INCIDENT_MODEL).strip()
            or DEFAULT_INCIDENT_MODEL,
            audio_filter=os.environ.get("AUDIO_CLEANUP_FILTER", DEFAULT_AUDIO_FILTER).strip() or DEFAULT_AUDIO_FILTER,
            context_prompt=os.environ.get("TRANSCRIPTION_CONTEXT_PROMPT", DEFAULT_CONTEXT_PROMPT).strip()
            or DEFAULT_CONTEXT_PROMPT,
            enable_incident_ai=env_bool("ENABLE_OPENAI_INCIDENT_ANALYSIS", True),
            broadcastify_username=(
                os.environ.get("BROADCASTIFY_USERNAME", "").strip()
                or os.environ.get("RADIOREFERENCE_USERNAME", "").strip()
            ),
            broadcastify_password=(
                os.environ.get("BROADCASTIFY_PASSWORD", "").strip()
                or os.environ.get("RADIOREFERENCE_PASSWORD", "").strip()
            ),
            owner_api_base_url=os.environ.get("BROADCASTIFY_OWNER_API_BASE_URL", DEFAULT_OWNER_API_BASE_URL).strip()
            or DEFAULT_OWNER_API_BASE_URL,
        )


class TranscriptPipeline:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.config.recordings_dir.mkdir(parents=True, exist_ok=True)
        self.config.transcripts_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.incident_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.archive_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.last_archive_poll = 0.0

    def run_forever(self) -> None:
        self.write_status("starting", "Transcript pipeline started")
        while True:
            try:
                self.run_once()
                if time.time() - self.last_archive_poll >= self.config.archive_poll_seconds:
                    self.process_archives_once()
                    self.last_archive_poll = time.time()
            except Exception as error:
                self.write_status("error", str(error))
            time.sleep(self.config.sleep_seconds)

    def run_once(self) -> Optional[Dict[str, Any]]:
        if not self.config.openai_api_key:
            self.write_status("waiting", "OPENAI_API_KEY is not configured; completed-call transcripts are paused.")
            return None

        started_at = utc_now()
        stream_url = self.current_stream_url()
        raw_path = self.record_chunk(stream_url, started_at)
        cleaned_path = self.clean_audio(raw_path)
        ended_at = utc_now()
        return self.process_audio_file(cleaned_path, started_at, ended_at, raw_path=raw_path)

    def process_archives_once(self) -> List[Dict[str, Any]]:
        if not self.config.openai_api_key:
            self.write_status("waiting", "OPENAI_API_KEY is not configured; archive transcripts are paused.")
            return []

        if not self.config.broadcastify_username or not self.config.broadcastify_password:
            self.write_status(
                "waiting",
                "Broadcastify owner username/password are not configured; archive backfill is paused.",
            )
            return []

        archive_state = load_archive_state(self.config.archive_state_path)
        processed_ids = set(archive_state.get("processedArchiveIds") or [])
        archives = self.fetch_recent_archives()
        processed: List[Dict[str, Any]] = []

        for archive in archives:
            archive_id = archive_identity(archive)
            if archive_id in processed_ids:
                continue

            download_url = archive.get("downloadUrl")
            if not download_url:
                processed_ids.add(archive_id)
                continue

            started_at = parse_iso(archive.get("startedAt")) or utc_now()
            ended_at = parse_iso(archive.get("endedAt")) or started_at
            audio_path = self.download_archive_audio(download_url, archive_id)
            cleaned_path = self.clean_audio(audio_path)
            try:
                event = self.process_audio_file(
                    cleaned_path,
                    started_at=started_at,
                    ended_at=ended_at,
                    raw_path=audio_path,
                    extra_fields={"archiveId": archive_id, "sourceArchive": archive},
                )
            except Exception as error:
                self.write_status("warning", f"Archive {archive_id} failed: {error}")
                continue

            processed_ids.add(archive_id)
            if event:
                processed.append(event)

        archive_state["processedArchiveIds"] = sorted(processed_ids)[-1000:]
        archive_state["updatedAt"] = iso_z(utc_now())
        save_json(self.config.archive_state_path, archive_state)

        if processed:
            self.write_status("archive-backfill", f"Processed {len(processed)} archive transcript(s)")
        else:
            self.write_status("archive-backfill", "No new archive audio to process")

        return processed

    def fetch_recent_archives(self) -> List[Dict[str, Any]]:
        dates = archive_dates_for_lookback(self.config.archive_lookback_hours)
        archives: List[Dict[str, Any]] = []
        for day in dates:
            payload = self.fetch_archive_day(day)
            archives.extend(normalize_archive_listing(payload, day))
        return sorted(archives, key=lambda item: item.get("startedAt") or "")

    def fetch_archive_day(self, day: str) -> Any:
        query = urlencode(
            {
                "a": "archives",
                "feedId": self.config.feed_id,
                "day": day,
                "type": "json",
                "u": self.config.broadcastify_username,
                "p": self.config.broadcastify_password,
            }
        )
        separator = "&" if "?" in self.config.owner_api_base_url else "?"
        request = Request(
            f"{self.config.owner_api_base_url}{separator}{query}",
            headers={
                "Accept": "application/json",
                "User-Agent": "PhillipsburgRadioBackend/1.0",
            },
        )
        return read_json_request(request, timeout=45)

    def download_archive_audio(self, url: str, archive_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", archive_id).strip("-")
        path = self.config.recordings_dir / f"archive-{safe_id}.mp3"
        if path.exists() and path.stat().st_size > 0:
            return path

        request = Request(url, headers={"User-Agent": "PhillipsburgRadioBackend/1.0"})
        try:
            with urlopen(request, timeout=120) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"Archive download returned HTTP {response.status}")
                path.write_bytes(response.read())
                return path
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Archive download returned HTTP {error.code}: {detail[:240]}") from error
        except URLError as error:
            raise RuntimeError(f"Archive download failed: {error.reason}") from error

    def process_audio_file(
        self,
        audio_path: Path,
        started_at: datetime,
        ended_at: datetime,
        raw_path: Optional[Path] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        duration = audio_duration_seconds(audio_path)
        speech_seconds = estimate_speech_seconds(audio_path, duration)
        if speech_seconds < self.config.min_speech_seconds:
            self.write_status("idle", f"Skipped mostly silent audio chunk: {speech_seconds:.1f}s speech")
            return None

        transcription = self.transcribe_audio(audio_path)
        text = normalize_transcript_text(transcription.get("text", ""))
        if not text:
            self.write_status("idle", "Skipped audio chunk with empty transcript")
            return None

        incident_state = load_incident_state(self.config.incident_state_path)
        incident = choose_or_create_incident(
            state=incident_state,
            transcript_text=text,
            timestamp=ended_at,
            max_age_seconds=self.config.max_incident_age_seconds,
        )

        event = {
            "id": str(uuid.uuid4()),
            "timestamp": iso_z(ended_at),
            "startedAt": iso_z(started_at),
            "endedAt": iso_z(ended_at),
            "text": text,
            "confidence": transcription.get("confidence"),
            "keywords": sorted(extract_keywords(text))[:16],
            "channel": "Scanner Recording",
            "incidentId": incident["id"],
            "incidentTitle": incident.get("title"),
            "durationSeconds": round(duration, 2),
            "speechSeconds": round(speech_seconds, 2),
            "audioFile": str(audio_path),
            "rawAudioFile": str(raw_path) if raw_path else None,
            "source": transcription.get("source"),
            "status": "transcribed",
        }
        if extra_fields:
            event.update(extra_fields)

        append_jsonl(self.config.transcripts_path, event)
        update_incident_with_event(incident_state, incident, event)

        ai_update = self.try_ai_incident_update(incident_state, incident, event)
        if ai_update:
            incident.update(ai_update)

        save_incident_state(self.config.incident_state_path, incident_state)
        self.write_status("transcribed", f"Added transcript to {incident['id']}", extra={"incidentId": incident["id"]})
        return event

    def current_stream_url(self) -> str:
        payload = fetch_broadcastify_feed(
            self.config.embed_player_url,
            self.config.broadcastify_api_key,
            self.config.feed_id,
        )
        config = build_feed_config(payload, self.config.feed_id, 300)
        return str(config["streamUrl"])

    def record_chunk(self, stream_url: str, started_at: datetime) -> Path:
        require_command("ffmpeg")
        timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
        path = self.config.recordings_dir / f"raw-{timestamp}.mp3"
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            stream_url,
            "-t",
            str(self.config.chunk_seconds),
            "-c:a",
            "copy",
            str(path),
        ]
        run_command(command, timeout=self.config.chunk_seconds + 25)
        return path

    def clean_audio(self, raw_path: Path) -> Path:
        require_command("ffmpeg")
        clean_path = raw_path.with_name(raw_path.stem.replace("raw-", "clean-") + ".wav")
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(raw_path),
            "-af",
            self.config.audio_filter,
            "-ar",
            "16000",
            "-ac",
            "1",
            str(clean_path),
        ]
        run_command(command, timeout=max(60, self.config.chunk_seconds * 3))
        return clean_path

    def transcribe_audio(self, audio_path: Path) -> Dict[str, Any]:
        if not self.config.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for automatic completed-call transcripts.")

        fields = {
            "model": self.config.transcribe_model,
            "response_format": "diarized_json"
            if self.config.transcribe_model == "gpt-4o-transcribe-diarize"
            else "json",
        }
        if self.config.transcribe_model == "gpt-4o-transcribe-diarize":
            fields["chunking_strategy"] = "auto"
        else:
            fields["prompt"] = self.config.context_prompt

        response = openai_multipart(
            api_key=self.config.openai_api_key,
            url=f"{self.config.openai_base_url}/audio/transcriptions",
            fields=fields,
            file_field="file",
            file_path=audio_path,
        )
        text = transcript_text_from_openai_response(response)
        return {
            "text": text,
            "raw": response,
            "source": f"openai:{self.config.transcribe_model}",
        }

    def try_ai_incident_update(
        self,
        state: Dict[str, Any],
        incident: Dict[str, Any],
        event: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self.config.openai_api_key or not self.config.enable_incident_ai:
            return None

        try:
            nearby = compact_recent_incidents(state.get("incidents", []), exclude_id=incident["id"])
            prompt = {
                "currentIncident": compact_incident(incident),
                "nearbyIncidents": nearby,
                "newTranscript": {
                    "timestamp": event["timestamp"],
                    "text": event["text"],
                    "keywords": event["keywords"],
                },
            }
            result = openai_json_response(
                api_key=self.config.openai_api_key,
                base_url=self.config.openai_base_url,
                model=self.config.incident_model,
                payload=prompt,
            )
            title = clean_short_text(result.get("title")) or incident.get("title")
            summary = clean_short_text(result.get("summary"), max_len=500) or incident.get("summary")
            status = clean_short_text(result.get("status"), max_len=40) or incident.get("status")
            return {
                "title": title,
                "summary": summary,
                "status": status,
                "aiReviewedAt": iso_z(utc_now()),
                "aiModel": self.config.incident_model,
            }
        except Exception as error:
            self.write_status("warning", f"Incident AI analysis failed: {error}")
            return None

    def write_status(self, state: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        payload = {
            "ok": state not in {"error"},
            "state": state,
            "message": message,
            "updatedAt": iso_z(utc_now()),
            "hasOpenAIKey": bool(self.config.openai_api_key),
            "transcribeModel": self.config.transcribe_model,
            "incidentModel": self.config.incident_model,
            "recordingsDir": str(self.config.recordings_dir),
            "hasArchiveAuth": bool(self.config.broadcastify_username and self.config.broadcastify_password),
        }
        if extra:
            payload.update(extra)
        self.config.status_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def openai_multipart(
    api_key: str,
    url: str,
    fields: Dict[str, str],
    file_field: str,
    file_path: Path,
) -> Dict[str, Any]:
    boundary = f"----PhillipsburgRadio{uuid.uuid4().hex}"
    body = bytearray()

    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")

    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode("utf-8")
    )
    body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
    body.extend(file_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    request = Request(
        url,
        data=bytes(body),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )
    return read_json_request(request, timeout=120)


def openai_json_response(api_key: str, base_url: str, model: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "status": {"type": "string", "enum": ["active", "updated", "resolved", "unknown"]},
        },
        "required": ["title", "summary", "status"],
    }
    body = {
        "model": model,
        "reasoning": {"effort": "low"},
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "incident_summary",
                "schema": schema,
                "strict": True,
            },
        },
        "input": [
            {
                "role": "system",
                "content": (
                    "You maintain a public safety scanner incident log. "
                    "Use only the transcript text provided. Do not invent addresses, injuries, units, or outcomes. "
                    "Return a concise title, a factual summary, and status."
                ),
            },
            {"role": "user", "content": json.dumps(payload, separators=(",", ":"))},
        ],
    }
    request = Request(
        f"{base_url.rstrip('/')}/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    response = read_json_request(request, timeout=90)
    text = extract_response_text(response)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def read_json_request(request: Request, timeout: int) -> Dict[str, Any]:
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"HTTP {response.status}: {body[:300]}")
            return json.loads(body)
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {detail[:300]}") from error
    except URLError as error:
        raise RuntimeError(f"Network error: {error.reason}") from error


def normalize_archive_listing(payload: Any, day: str) -> List[Dict[str, Any]]:
    rows = archive_rows_from_payload(payload)
    archives = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        download_url = first_value(
            row,
            [
                "downloadUrl",
                "downloadURL",
                "download_url",
                "download",
                "url",
                "file",
                "mp3",
            ],
        )
        started_at = archive_time_value(row, ["startTime", "start", "start_time", "from", "time", "datetime"], day)
        ended_at = archive_time_value(row, ["endTime", "end", "end_time", "to", "until"], day)
        label = first_value(row, ["timeframe", "timeFrame", "label", "name", "descr", "description"])

        if not download_url and isinstance(label, str) and "http" in label:
            match = re.search(r"https?://\S+", label)
            download_url = match.group(0).rstrip(".,") if match else None

        archives.append(
            {
                "id": str(first_value(row, ["id", "archiveId", "archive_id"]) or ""),
                "day": day,
                "label": str(label or ""),
                "startedAt": started_at,
                "endedAt": ended_at,
                "downloadUrl": str(download_url or ""),
                "raw": row,
            }
        )
    return [archive for archive in archives if archive.get("downloadUrl")]


def archive_rows_from_payload(payload: Any) -> List[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in [
        "archives",
        "archive",
        "Archives",
        "Archive",
        "data",
        "results",
        "feeds",
    ]:
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = archive_rows_from_payload(value)
            if nested:
                return nested

    return [payload] if any(key.lower().endswith("url") or key in {"url", "download", "file"} for key in payload) else []


def archive_time_value(row: Dict[str, Any], keys: Sequence[str], day: str) -> Optional[str]:
    value = first_value(row, keys)
    if value is None:
        label = str(first_value(row, ["timeframe", "timeFrame", "label", "name"]) or "")
        match = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)", label)
        if match:
            return archive_time_value({"time": match.group(1)}, ["time"], day)
        return None

    text = str(value).strip()
    parsed = parse_iso(text)
    if parsed:
        return iso_z(parsed)

    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"]:
        try:
            if fmt.startswith("%Y"):
                dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            else:
                hour = datetime.strptime(text, fmt).time()
                date = datetime.strptime(day, "%Y-%m-%d").date()
                dt = datetime.combine(date, hour, tzinfo=timezone.utc)
            return iso_z(dt)
        except ValueError:
            continue

    return None


def first_value(mapping: Dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def archive_dates_for_lookback(hours: int) -> List[str]:
    now = utc_now()
    start = now - timedelta(hours=max(1, hours))
    dates = {start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")}
    return sorted(dates)


def archive_identity(archive: Dict[str, Any]) -> str:
    if archive.get("id"):
        return str(archive["id"])
    raw = "|".join(
        str(archive.get(key) or "")
        for key in ["day", "startedAt", "endedAt", "downloadUrl", "label"]
    )
    return uuid.uuid5(uuid.NAMESPACE_URL, raw).hex


def transcript_text_from_openai_response(response: Dict[str, Any]) -> str:
    if isinstance(response.get("text"), str):
        return response["text"]

    segments = response.get("segments")
    if isinstance(segments, list):
        parts = []
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            speaker = segment.get("speaker")
            text = segment.get("text")
            if text and speaker:
                parts.append(f"{speaker}: {text}")
            elif text:
                parts.append(str(text))
        if parts:
            return " ".join(parts)

    return ""


def extract_response_text(response: Dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]

    parts = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(parts)


def choose_or_create_incident(
    state: Dict[str, Any],
    transcript_text: str,
    timestamp: datetime,
    max_age_seconds: int,
) -> Dict[str, Any]:
    incidents = state.setdefault("incidents", [])
    best: Optional[Tuple[float, Dict[str, Any]]] = None
    for incident in incidents:
        updated_at = parse_iso(incident.get("updatedAt")) or timestamp
        if (timestamp - updated_at).total_seconds() > max_age_seconds:
            continue
        score = incident_similarity(incident, transcript_text)
        if best is None or score > best[0]:
            best = (score, incident)

    if best and best[0] >= 0.32:
        return best[1]

    keywords = sorted(extract_keywords(transcript_text))
    incident = {
        "id": f"inc-{timestamp.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}",
        "createdAt": iso_z(timestamp),
        "updatedAt": iso_z(timestamp),
        "title": title_from_keywords(keywords),
        "summary": summary_from_text(transcript_text),
        "status": "active",
        "keywords": keywords[:20],
        "transcriptIds": [],
        "transcriptCount": 0,
        "latestText": "",
    }
    incidents.insert(0, incident)
    del incidents[100:]
    return incident


def update_incident_with_event(state: Dict[str, Any], incident: Dict[str, Any], event: Dict[str, Any]) -> None:
    current_keywords = set(incident.get("keywords") or [])
    current_keywords.update(event.get("keywords") or [])
    transcript_ids = incident.setdefault("transcriptIds", [])
    transcript_ids.append(event["id"])
    del transcript_ids[:-12]

    incident["updatedAt"] = event["timestamp"]
    incident["keywords"] = sorted(current_keywords)[:24]
    incident["transcriptCount"] = int(incident.get("transcriptCount") or 0) + 1
    incident["latestText"] = event["text"]
    incident["summary"] = merge_summary(incident.get("summary", ""), event["text"])
    if not incident.get("title") or incident.get("title") == "Scanner Incident":
        incident["title"] = title_from_keywords(incident["keywords"])

    state["incidents"] = sorted(state.get("incidents", []), key=lambda item: item.get("updatedAt", ""), reverse=True)


def incident_similarity(incident: Dict[str, Any], transcript_text: str) -> float:
    existing = set(incident.get("keywords") or [])
    incoming = extract_keywords(transcript_text)
    if not existing or not incoming:
        return 0.0

    overlap = len(existing & incoming)
    union = len(existing | incoming)
    jaccard = overlap / union if union else 0.0
    term_bonus = 0.15 if (existing & incoming & INCIDENT_TERMS) else 0.0
    number_bonus = 0.15 if (extract_numbers(" ".join(existing)) & extract_numbers(transcript_text)) else 0.0
    return min(1.0, jaccard + term_bonus + number_bonus)


def extract_keywords(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9']+", text.lower())
    keywords = {
        word.strip("'")
        for word in words
        if len(word) >= 3 and word not in STOP_WORDS and not word.isdigit()
    }
    keywords.update(word for word in words if word in INCIDENT_TERMS)
    keywords.update(f"unit-{num}" for num in extract_numbers(text))
    return keywords


def extract_numbers(text: str) -> set[str]:
    return set(re.findall(r"\b\d{2,5}\b", text.lower()))


def title_from_keywords(keywords: Sequence[str]) -> str:
    useful = [keyword.replace("unit-", "Unit ") for keyword in keywords if keyword in INCIDENT_TERMS]
    if useful:
        return " / ".join(useful[:3]).title()
    if keywords:
        return " ".join(keyword.replace("unit-", "Unit ") for keyword in keywords[:4]).title()
    return "Scanner Incident"


def summary_from_text(text: str) -> str:
    return clean_short_text(text, max_len=260) or "Scanner traffic captured for review."


def merge_summary(existing: str, text: str) -> str:
    text = clean_short_text(text, max_len=220)
    if not existing:
        return text
    if not text or text.lower() in existing.lower():
        return existing
    merged = f"{existing} {text}"
    return clean_short_text(merged, max_len=500) or existing


def compact_recent_incidents(incidents: List[Dict[str, Any]], exclude_id: str) -> List[Dict[str, Any]]:
    rows = []
    for incident in incidents[:8]:
        if incident.get("id") == exclude_id:
            continue
        rows.append(compact_incident(incident))
    return rows


def compact_incident(incident: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": incident.get("id"),
        "title": incident.get("title"),
        "summary": incident.get("summary"),
        "updatedAt": incident.get("updatedAt"),
        "keywords": incident.get("keywords", [])[:12],
    }


def normalize_transcript_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    garbage = {"you", "thank you", "thanks for watching", "[music]", "(music)"}
    if cleaned.lower() in garbage:
        return ""
    return cleaned


def clean_short_text(value: Any, max_len: int = 120) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "..."


def audio_duration_seconds(path: Path) -> float:
    if not shutil.which("ffprobe"):
        return 0.0
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = run_command(command, timeout=30, capture=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def estimate_speech_seconds(path: Path, duration: float) -> float:
    if duration <= 0 or not shutil.which("ffmpeg"):
        return max(duration, 0.0)

    command = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(path),
        "-af",
        "silencedetect=n=-38dB:d=1.1",
        "-f",
        "null",
        "-",
    ]
    result = run_command(command, timeout=max(30, math.ceil(duration) + 30), capture=True, check=False)
    silence = 0.0
    for match in re.finditer(r"silence_duration: ([0-9.]+)", result.stderr):
        silence += float(match.group(1))
    return max(0.0, duration - silence)


def run_command(
    command: Sequence[str],
    timeout: int,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)} {detail[:300]}")
    return result


def require_command(name: str) -> None:
    if not shutil.which(name):
        raise RuntimeError(f"{name} is required. Install ffmpeg on the Pi.")


def load_incident_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"incidents": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("incidents"), list):
            return data
    except Exception:
        pass
    return {"incidents": []}


def save_incident_state(path: Path, state: Dict[str, Any]) -> None:
    save_json(path, state)


def load_archive_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"processedArchiveIds": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("processedArchiveIds"), list):
            return data
    except Exception:
        pass
    return {"processedArchiveIds": []}


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
