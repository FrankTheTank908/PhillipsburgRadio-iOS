#!/usr/bin/env python3

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("broadcastify_api_backend.py")
spec = importlib.util.spec_from_file_location("broadcastify_api_backend", MODULE_PATH)
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


payload = {
    "Feed": [
        {
            "id": 45951,
            "descr": "Phillipsburg / Easton Public Safety",
            "status": 1,
            "listeners": "8",
            "bitrate": "32",
            "mount": "/test-mount",
            "Relays": [
                {
                    "host": "relay.broadcastify.com",
                    "port": "80",
                }
            ],
        }
    ]
}

config = backend.build_feed_config(payload, "45951", 300)

assert config["feedId"] == "45951"
assert config["title"] == "Phillipsburg / Easton Public Safety"
assert config["status"] == "online"
assert config["listeners"] == 8
assert config["bitrate"] == 32
assert config["streamUrl"] == "http://relay.broadcastify.com/test-mount"
assert config["source"] == "broadcastify-embed-player-pi-backend"

embed_html = """
<audio width="300" id="mePlayer_45951"
       src="https://listen.broadcastify.com/example-token.mp3"
       type="audio/mp3" controls="controls">
</audio>
<script src="https://cdnjs.cloudflare.com/ajax/libs/mediaelement/4.2.9/mediaelement-and-player.min.js"></script>
"""

assert backend.extract_stream_url_from_embed_html(
    embed_html,
    "https://api.broadcastify.com/embed/player/?feedId=45951",
) == "https://listen.broadcastify.com/example-token.mp3"

catalog = backend.normalize_catalog_response(
    "feeds",
    {
        "feeds": [
            {
                "feedId": 123,
                "descr": "City Police Dispatch",
                "listeners": "17",
                "bitrate": "32",
                "ctid": 99,
            }
        ]
    },
)
assert catalog["items"][0]["id"] == "123"
assert catalog["items"][0]["name"] == "City Police Dispatch"
assert catalog["items"][0]["feedId"] == "123"
assert catalog["items"][0]["countyId"] == "99"

print("backend parser tests ok")
