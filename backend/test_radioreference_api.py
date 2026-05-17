#!/usr/bin/env python3

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("radioreference_api.py")
spec = importlib.util.spec_from_file_location("radioreference_api", MODULE_PATH)
rr = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = rr
spec.loader.exec_module(rr)


catalog = rr.method_catalog()
method_names = {method["name"] for method in catalog["methods"]}
assert "getCountryList" in method_names
assert "getUserFeedBroadcasts" in method_names
assert "getZipcodeInfo" in method_names

client = rr.RadioReferenceClient(
    username="demo-user",
    password="demo-password",
    app_key="demo-key",
)
envelope = rr.build_soap_envelope(
    rr.METHOD_SPECS["getZipcodeInfo"],
    {"zipcode": "90210", "authInfo": client.auth_info()},
)
assert b"getZipcodeInfo" in envelope
assert b"90210" in envelope
assert b"demo-key" in envelope

response_xml = b"""<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
  <SOAP-ENV:Body>
    <ns1:getUserFeedBroadcastsResponse xmlns:ns1="http://api.radioreference.com/soap2">
      <return>
        <item>
          <feedId>45951</feedId>
          <descr>Phillipsburg / Easton Public Safety</descr>
          <hostname>audio.broadcastify.com</hostname>
          <port>80</port>
          <mount>/example</mount>
          <password>secret-feed-password</password>
        </item>
      </return>
    </ns1:getUserFeedBroadcastsResponse>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>
"""
parsed = rr.parse_soap_response(response_xml)
redacted = rr.redact_secret_fields(parsed)

assert parsed[0]["feedId"] == "45951"
assert redacted[0]["password"] == "[redacted]"

print("radioreference soap tests ok")
