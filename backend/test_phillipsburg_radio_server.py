#!/usr/bin/env python3

import importlib.util
import os
from pathlib import Path


os.environ["BROADCASTIFY_API_KEY"] = "test-key"
os.environ["BROADCASTIFY_FEED_ID"] = "45951"
os.environ["BACKEND_PORT"] = "5214"
os.environ["OUTPUT_JSON_PATH"] = str(Path("build/test-current-feed.json").resolve())
os.environ["TRANSCRIPTS_PATH"] = str(Path("build/test-transcripts.jsonl").resolve())
os.environ["INCIDENTS_PATH"] = str(Path("build/test-incidents.jsonl").resolve())
os.environ["INCIDENT_STATE_PATH"] = str(Path("build/test-incident-state.json").resolve())
os.environ["PIPELINE_STATUS_PATH"] = str(Path("build/test-pipeline-status.json").resolve())
os.environ["ALLOW_DEBUG_ADMIN_WITHOUT_TOKEN"] = "1"

MODULE_PATH = Path(__file__).with_name("phillipsburg_radio_server.py")
spec = importlib.util.spec_from_file_location("phillipsburg_radio_server", MODULE_PATH)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

health = server.STATE.health()
assert health["service"] == "phillipsburg-radio-backend"
assert health["feedId"] == "45951"
assert health["port"] == 5214
assert health["debugAdminNoAuth"] is True

event = server.STATE.add_transcript({"text": "Unit test transcript", "channel": "Test"})
assert event["text"] == "Unit test transcript"
assert server.STATE.read_transcripts(limit=1)[0]["text"] == "Unit test transcript"

Path(os.environ["INCIDENT_STATE_PATH"]).write_text(
    '{"incidents":[{"id":"inc-test","title":"Test Incident","summary":"Unit test summary"}]}',
    encoding="utf-8",
)
Path(os.environ["PIPELINE_STATUS_PATH"]).write_text(
    '{"ok":true,"state":"transcribed","message":"ok"}',
    encoding="utf-8",
)
assert server.STATE.read_incident_summaries(limit=1)[0]["id"] == "inc-test"
assert server.STATE.pipeline_status()["state"] == "transcribed"

message = server.STATE.add_incident({"text": "Road closure at the bridge", "author": "Unit Test"})
assert message["author"] == "Unit Test"
assert server.STATE.read_incidents(limit=1)[0]["text"] == "Road closure at the bridge"

metadata = server.STATE.metadata()
assert "/radio-reference/methods" in metadata["routes"]
assert metadata["radioReference"]["wsdl"].endswith("v=latest")

print("backend server tests ok")
