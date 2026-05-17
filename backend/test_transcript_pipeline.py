#!/usr/bin/env python3

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


os.environ["BROADCASTIFY_API_KEY"] = "test-key"

MODULE_PATH = Path(__file__).with_name("transcript_pipeline.py")
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("transcript_pipeline", MODULE_PATH)
pipeline = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pipeline
spec.loader.exec_module(pipeline)


state = {"incidents": []}
timestamp = datetime(2026, 5, 17, 20, 30, tzinfo=timezone.utc)

incident_a = pipeline.choose_or_create_incident(
    state,
    "Engine 94 responding to a motor vehicle accident near South Main Street with injuries.",
    timestamp,
    2700,
)
pipeline.update_incident_with_event(
    state,
    incident_a,
    {
        "id": "event-1",
        "timestamp": pipeline.iso_z(timestamp),
        "text": "Engine 94 responding to a motor vehicle accident near South Main Street with injuries.",
        "keywords": sorted(pipeline.extract_keywords("Engine 94 responding to a motor vehicle accident near South Main Street with injuries.")),
    },
)

incident_b = pipeline.choose_or_create_incident(
    state,
    "Additional EMS requested for the accident on South Main Street, unit 94 on scene.",
    timestamp,
    2700,
)

incident_c = pipeline.choose_or_create_incident(
    state,
    "Fire alarm activation at a different commercial property across town.",
    timestamp,
    2700,
)

assert incident_a["id"] == incident_b["id"]
assert incident_c["id"] != incident_a["id"]
assert "accident" in pipeline.extract_keywords("motor vehicle accident")
assert pipeline.normalize_transcript_text("  Test   transcript\n") == "Test transcript"

state_path = Path("build/test-transcript-pipeline-state.json")
pipeline.save_incident_state(state_path, state)
loaded = pipeline.load_incident_state(state_path)
assert loaded["incidents"][0]["id"] == state["incidents"][0]["id"]

print("transcript pipeline tests ok")
