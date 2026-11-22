"""Install the v2 branch in the existing Viessmann tab, using the Node-RED v2 revision check."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent


def nodes(flow, stage, influx_url, database):
    tabs = [n for n in flow if n.get("type") == "tab" and n.get("label") == "Viesmann VITO"]
    if len(tabs) != 1:
        raise ValueError("Expected one Viesmann VITO tab")
    tab = tabs[0]["id"]
    inputs = [n for n in flow if n.get("z") == tab and n.get("type") == "mqtt in" and n.get("topic") == "vito/+"]
    if len(inputs) != 1:
        raise ValueError("Expected one existing Viessmann MQTT input")
    broker = inputs[0]["broker"]
    prefix = "vito_v2_stage_" if stage else "vito_v2_"
    topic = "vito/staging/v2/+" if stage else "vito/telemetry/v2/+"
    y = 740 if stage else 660

    def node(key, kind, name, x, to=None, **kwargs):
        return {"id": prefix + key, "type": kind, "z": tab, "name": name, "x": x, "y": y,
                "wires": [[prefix + to]] if to else [], **kwargs}

    ack = (ROOT / "acknowledge.js").read_text()
    if stage:
        ack = ack.replace("vito/ack/v2/", "vito/staging-ack/v2/")
    return [
        node("mqtt_in", "mqtt in", "Versioned observations" + (" (test)" if stage else ""), 160, "encode",
             topic=topic, qos="1", datatype="json", broker=broker, nl=False, rap=True, rh=0, inputs=0),
        node("encode", "function", "Preserve acquisition time and raw data", 480, "write",
             func=(ROOT / "observation.js").read_text(), outputs=1, timeout=0, noerr=0,
             initialize="", finalize="", libs=[]),
        node("write", "http request", "Write observation to " + database, 800, "confirm",
             method="POST", ret="txt", paytoqs="ignore", url=influx_url.rstrip("/") + "/write?" +
             urlencode({"db": database, "precision": "ns"}), tls="", persist=True, proxy="", authType="", senderr=False),
        node("confirm", "function", "Acknowledge committed writes", 1050, "mqtt_out", func=ack, outputs=1,
             timeout=0, noerr=0, initialize="", finalize="", libs=[]),
        node("mqtt_out", "mqtt out", "Storage acknowledgements", 1300, topic="", qos="1", retain="false",
             broker=broker, expiry="", contentType="", userProps="", correl="", respTopic=""),
    ]


def deploy(args):
    endpoint = args.node_red.rstrip("/") + "/flows"
    headers = {"Node-RED-API-Version": "v2"}
    if os.getenv("NODE_RED_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["NODE_RED_TOKEN"]
    with urlopen(Request(endpoint, headers=headers), timeout=20) as res:
        current = json.load(res)
    database = "Vito_Ingest_Fixture" if args.stage else "Vito"
    branch = nodes(current["flows"], args.stage, args.influx, database)
    ids = {n["id"] for n in branch}
    previous = [n for n in current["flows"] if n["id"] in ids]
    expected_types = {n['id']: (n['type'], n['z']) for n in branch}
    if any((n['type'], n.get('z')) != expected_types[n['id']] for n in previous):
        raise ValueError("A target ID is in use by an unrelated node")
    if (not args.remove and previous == branch) or (args.remove and not previous):
        return "Already in requested state"
    current["flows"] = [n for n in current["flows"] if n["id"] not in ids]
    if not args.remove:
        current["flows"].extend(branch)
    headers.update({"Content-Type": "application/json", "Node-RED-Deployment-Type": "nodes"})
    with urlopen(Request(endpoint, data=json.dumps(current).encode(), headers=headers), timeout=45) as res:
        return json.load(res)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-red", required=True)
    parser.add_argument("--influx", required=True)
    parser.add_argument("--stage", action="store_true", help="Use the isolated fixture topic and database")
    parser.add_argument("--remove", action="store_true", help="Remove only this branch")
    args = parser.parse_args()
    if any(urlparse(url).scheme not in ("http", "https") for url in (args.node_red, args.influx)):
        parser.error("Expected HTTP(S) endpoints")
    print(deploy(args))
