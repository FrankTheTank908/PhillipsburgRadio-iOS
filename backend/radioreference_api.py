#!/usr/bin/env python3
"""
RadioReference SOAP Web Service helper for the Phillipsburg Radio Pi backend.

The RadioReference database service is metadata/account access. It is separate
from Broadcastify live audio, so this module never exposes credentials or feed
passwords back to the iPhone app.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SOAP_ENV_NS = "http://schemas.xmlsoap.org/soap/envelope/"
SOAP_ENC_NS = "http://schemas.xmlsoap.org/soap/encoding/"
XSD_NS = "http://www.w3.org/2001/XMLSchema"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
RR_NS = "http://api.radioreference.com/soap2"

DEFAULT_ENDPOINT = "https://api.radioreference.com/soap2/"
DEFAULT_WSDL_URL = "https://api.radioreference.com/soap2/?wsdl&v=latest"
DEFAULT_VERSION = "latest"
DEFAULT_STYLE = "rpc"
DEFAULT_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class MethodSpec:
    name: str
    params: List[Dict[str, str]]
    returns: str

    @property
    def requires_auth(self) -> bool:
        return any(param["name"] == "authInfo" for param in self.params)


METHOD_SPECS: Dict[str, MethodSpec] = {
    "getTrsTalkgroups": MethodSpec(
        "getTrsTalkgroups",
        [
            {"name": "sid", "type": "xsd:int"},
            {"name": "tgCid", "type": "xsd:int"},
            {"name": "tgTag", "type": "xsd:int"},
            {"name": "tgDec", "type": "xsd:int"},
            {"name": "authInfo", "type": "tns:authInfo"},
        ],
        "tns:Talkgroups",
    ),
    "getTrsTalkgroupCats": MethodSpec(
        "getTrsTalkgroupCats",
        [{"name": "sid", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:TalkgroupCats",
    ),
    "getTrsDetails": MethodSpec(
        "getTrsDetails",
        [{"name": "sid", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:Trs",
    ),
    "getTrsBySysid": MethodSpec(
        "getTrsBySysid",
        [{"name": "sysid", "type": "xsd:string"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:TrsList",
    ),
    "getTrsSites": MethodSpec(
        "getTrsSites",
        [{"name": "sid", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:TrsSites",
    ),
    "getStatesByList": MethodSpec(
        "getStatesByList",
        [{"name": "request", "type": "tns:stidList"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:States",
    ),
    "getCountiesByList": MethodSpec(
        "getCountiesByList",
        [{"name": "request", "type": "tns:ctidList"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:Counties",
    ),
    "getTag": MethodSpec(
        "getTag",
        [{"name": "id", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:tags",
    ),
    "getMode": MethodSpec(
        "getMode",
        [{"name": "mode", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:modes",
    ),
    "getTrsType": MethodSpec(
        "getTrsType",
        [{"name": "id", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:TrsType",
    ),
    "getTrsFlavor": MethodSpec(
        "getTrsFlavor",
        [{"name": "id", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:TrsFlavor",
    ),
    "getTrsVoice": MethodSpec(
        "getTrsVoice",
        [{"name": "id", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:TrsVoice",
    ),
    "getCountryList": MethodSpec("getCountryList", [], "tns:Countries"),
    "getCountryInfo": MethodSpec(
        "getCountryInfo",
        [{"name": "coid", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:CountryInfo",
    ),
    "getStateInfo": MethodSpec(
        "getStateInfo",
        [{"name": "stid", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:StateInfo",
    ),
    "getCountyInfo": MethodSpec(
        "getCountyInfo",
        [{"name": "ctid", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:CountyInfo",
    ),
    "getAgencyInfo": MethodSpec(
        "getAgencyInfo",
        [{"name": "aid", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:AgencyInfo",
    ),
    "getSubcatFreqs": MethodSpec(
        "getSubcatFreqs",
        [{"name": "scid", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:Freqs",
    ),
    "searchCountyFreq": MethodSpec(
        "searchCountyFreq",
        [
            {"name": "ctid", "type": "xsd:int"},
            {"name": "freq", "type": "xsd:decimal"},
            {"name": "tone", "type": "xsd:string"},
            {"name": "authInfo", "type": "tns:authInfo"},
        ],
        "tns:searchFreqResults",
    ),
    "searchStateFreq": MethodSpec(
        "searchStateFreq",
        [
            {"name": "stid", "type": "xsd:int"},
            {"name": "freq", "type": "xsd:decimal"},
            {"name": "tone", "type": "xsd:string"},
            {"name": "authInfo", "type": "tns:authInfo"},
        ],
        "tns:searchFreqResults",
    ),
    "searchMetroFreq": MethodSpec(
        "searchMetroFreq",
        [
            {"name": "mid", "type": "xsd:int"},
            {"name": "freq", "type": "xsd:decimal"},
            {"name": "tone", "type": "xsd:string"},
            {"name": "authInfo", "type": "tns:authInfo"},
        ],
        "tns:searchFreqResults",
    ),
    "getCountyFreqsByTag": MethodSpec(
        "getCountyFreqsByTag",
        [{"name": "ctid", "type": "xsd:int"}, {"name": "tag", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:Freqs",
    ),
    "getAgencyFreqsByTag": MethodSpec(
        "getAgencyFreqsByTag",
        [{"name": "aid", "type": "xsd:int"}, {"name": "tag", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:Freqs",
    ),
    "getMetroArea": MethodSpec(
        "getMetroArea",
        [{"name": "mid", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:Metros",
    ),
    "getMetroAreaInfo": MethodSpec(
        "getMetroAreaInfo",
        [{"name": "mid", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:Counties",
    ),
    "getZipcodeInfo": MethodSpec(
        "getZipcodeInfo",
        [{"name": "zipcode", "type": "xsd:int"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:ZipInfo",
    ),
    "fccGetCallsign": MethodSpec(
        "fccGetCallsign",
        [{"name": "callsign", "type": "xsd:string"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:fccCallsignDetails",
    ),
    "fccGetRadioServiceCode": MethodSpec(
        "fccGetRadioServiceCode",
        [{"name": "code", "type": "xsd:string"}, {"name": "authInfo", "type": "tns:authInfo"}],
        "tns:fccRadioServiceCodes",
    ),
    "fccGetProxCallsigns": MethodSpec(
        "fccGetProxCallsigns",
        [
            {"name": "lat", "type": "xsd:decimal"},
            {"name": "lon", "type": "xsd:decimal"},
            {"name": "range", "type": "xsd:decimal"},
            {"name": "unit", "type": "xsd:string"},
            {"name": "authInfo", "type": "tns:authInfo"},
        ],
        "tns:proxCallsignResults",
    ),
    "getUserData": MethodSpec("getUserData", [{"name": "authInfo", "type": "tns:authInfo"}], "tns:UserInfo"),
    "getUserFeedBroadcasts": MethodSpec(
        "getUserFeedBroadcasts",
        [{"name": "authInfo", "type": "tns:authInfo"}],
        "tns:userFeedBroadcasts",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Call RadioReference SOAP metadata methods.")
    parser.add_argument("method", nargs="?", default="methods", help="Method name, or 'methods' for the catalog.")
    parser.add_argument("--param", action="append", default=[], help="name=value parameter. Can be repeated.")
    args = parser.parse_args()

    if args.method == "methods":
        print(json.dumps(method_catalog(), indent=2))
        return 0

    params = parse_param_args(args.param)
    client = RadioReferenceClient.from_env()
    result = client.call_method(args.method, params)
    print(json.dumps(redact_secret_fields(result), indent=2))
    return 0


def parse_param_args(values: Iterable[str]) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid --param value: {value}")
        key, raw = value.split("=", 1)
        params[key.strip()] = raw.strip()
    return params


class RadioReferenceClient:
    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        username: str = "",
        password: str = "",
        app_key: str = "",
        version: str = DEFAULT_VERSION,
        style: str = DEFAULT_STYLE,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.endpoint = endpoint
        self.username = username
        self.password = password
        self.app_key = app_key
        self.version = version
        self.style = style
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "RadioReferenceClient":
        app_key = (
            os.environ.get("RADIOREFERENCE_API_KEY", "").strip()
            or os.environ.get("RADIO_REFERENCE_API_KEY", "").strip()
            or os.environ.get("BROADCASTIFY_API_KEY", "").strip()
        )
        return cls(
            endpoint=os.environ.get("RADIOREFERENCE_ENDPOINT", DEFAULT_ENDPOINT).strip() or DEFAULT_ENDPOINT,
            username=os.environ.get("RADIOREFERENCE_USERNAME", "").strip(),
            password=os.environ.get("RADIOREFERENCE_PASSWORD", "").strip(),
            app_key=app_key,
            version=os.environ.get("RADIOREFERENCE_VERSION", DEFAULT_VERSION).strip() or DEFAULT_VERSION,
            style=os.environ.get("RADIOREFERENCE_STYLE", DEFAULT_STYLE).strip() or DEFAULT_STYLE,
            timeout_seconds=int(os.environ.get("RADIOREFERENCE_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
        )

    @property
    def has_auth(self) -> bool:
        return bool(self.username and self.password and self.app_key)

    def auth_info(self) -> Dict[str, str]:
        if not self.has_auth:
            raise RuntimeError(
                "RadioReference username, password, and app key are required for this method. "
                "Set RADIOREFERENCE_USERNAME, RADIOREFERENCE_PASSWORD, and RADIOREFERENCE_API_KEY in GitHub secrets."
            )
        return {
            "username": self.username,
            "password": self.password,
            "appKey": self.app_key,
            "version": self.version,
            "style": self.style,
        }

    def call_method(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        spec = METHOD_SPECS.get(method)
        if not spec:
            raise ValueError(f"Unsupported RadioReference method: {method}")

        payload_params = dict(params or {})
        if spec.requires_auth:
            payload_params["authInfo"] = self.auth_info()

        envelope = build_soap_envelope(spec, payload_params)
        response_xml = self.post_soap(method, envelope)
        return parse_soap_response(response_xml)

    def post_soap(self, method: str, envelope: bytes) -> bytes:
        request = Request(
            self.endpoint,
            data=envelope,
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f"{RR_NS}#{method}",
                "User-Agent": "PhillipsburgRadioBackend/1.0",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read()
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"RadioReference SOAP returned HTTP {response.status}: {body[:240]!r}")
                return body
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"RadioReference SOAP returned HTTP {error.code}: {detail[:240]}") from error
        except URLError as error:
            raise RuntimeError(f"Could not call RadioReference SOAP: {error.reason}") from error


def build_soap_envelope(spec: MethodSpec, params: Dict[str, Any]) -> bytes:
    ET.register_namespace("soapenv", SOAP_ENV_NS)
    ET.register_namespace("soapenc", SOAP_ENC_NS)
    ET.register_namespace("xsd", XSD_NS)
    ET.register_namespace("xsi", XSI_NS)
    ET.register_namespace("rr", RR_NS)

    envelope = ET.Element(f"{{{SOAP_ENV_NS}}}Envelope")
    body = ET.SubElement(envelope, f"{{{SOAP_ENV_NS}}}Body")
    method_element = ET.SubElement(body, f"{{{RR_NS}}}{spec.name}")

    for param in spec.params:
        name = param["name"]
        if name not in params:
            raise ValueError(f"Missing required parameter for {spec.name}: {name}")
        append_value(method_element, name, params[name], param["type"])

    return ET.tostring(envelope, encoding="utf-8", xml_declaration=True)


def append_value(parent: ET.Element, name: str, value: Any, param_type: str = "") -> None:
    element = ET.SubElement(parent, name)

    if isinstance(value, dict):
        for child_key, child_value in value.items():
            append_value(element, child_key, child_value)
        return

    if isinstance(value, list):
        for child_value in value:
            append_value(element, "item", child_value)
        return

    element.text = coerce_value(value, param_type)


def coerce_value(value: Any, param_type: str) -> str:
    if value is None:
        return ""
    if param_type == "xsd:int":
        return str(int(value))
    if param_type == "xsd:decimal":
        return str(value).strip()
    return str(value)


def parse_soap_response(xml_bytes: bytes) -> Any:
    root = ET.fromstring(xml_bytes)
    fault = root.find(f".//{{{SOAP_ENV_NS}}}Fault")
    if fault is not None:
        raise RuntimeError(f"RadioReference SOAP fault: {element_to_data(fault)}")

    body = root.find(f".//{{{SOAP_ENV_NS}}}Body")
    if body is None or len(body) == 0:
        return None

    response = list(body)[0]
    for child in list(response):
        if local_name(child.tag) == "return":
            return element_to_data(child)

    return element_to_data(response)


def element_to_data(element: ET.Element) -> Any:
    children = list(element)
    if not children:
        return text_or_none(element.text)

    names = [local_name(child.tag) for child in children]
    if len(set(names)) == 1 and names[0] in {"item", "country", "state", "county", "freq", "talkgroup"}:
        return [element_to_data(child) for child in children]

    result: Dict[str, Any] = {}
    for child in children:
        key = local_name(child.tag)
        value = element_to_data(child)
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(value)
        else:
            result[key] = value
    return result


def text_or_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def method_catalog() -> Dict[str, Any]:
    methods = []
    for spec in METHOD_SPECS.values():
        methods.append(
            {
                "name": spec.name,
                "requiresAuth": spec.requires_auth,
                "params": [param for param in spec.params if param["name"] != "authInfo"],
                "returns": spec.returns,
            }
        )

    return {
        "docs": {
            "wsdl": DEFAULT_WSDL_URL,
            "wiki": "https://wiki.radioreference.com/index.php/RadioReference.com_Web_Service",
        },
        "methods": methods,
    }


def redact_secret_fields(value: Any) -> Any:
    secret_keys = {"password", "pass", "passwd", "token", "appkey", "apikey", "api_key"}
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, child in value.items():
            if key.lower() in secret_keys:
                redacted[key] = "[redacted]"
            else:
                redacted[key] = redact_secret_fields(child)
        return redacted

    if isinstance(value, list):
        return [redact_secret_fields(child) for child in value]

    return value


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
