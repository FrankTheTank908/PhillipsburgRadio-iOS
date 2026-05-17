#!/usr/bin/env python3

import importlib.util
import os
from pathlib import Path


os.environ["BROADCASTIFY_API_KEY"] = "test-key"
os.environ["BROADCASTIFY_FEED_ID"] = "45951"
os.environ["BACKEND_PORT"] = "5214"
os.environ["OUTPUT_JSON_PATH"] = str(Path("build/test-current-feed.json").resolve())
os.environ["TRANSCRIPTS_PATH"] = str(Path("build/test-transcripts.jsonl").resolve())

MODULE_PATH = Path(__file__).with_name("phillipsburg_radio_server.py")
spec = importlib.util.spec_from_file_location("phillipsburg_radio_server", MODULE_PATH)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

health = server.STATE.health()
assert health["service"] == "phillipsburg-radio-backend"
assert health["feedId"] == "45951"
assert health["port"] == 5214

event = server.STATE.add_transcript({"text": "Unit test transcript", "channel": "Test"})
assert event["text"] == "Unit test transcript"
assert server.STATE.read_transcripts(limit=1)[0]["text"] == "Unit test transcript"

print("backend server tests ok")
