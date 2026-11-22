#!/usr/bin/env python3
"""Read-only acceptance check. Requires mosquitto_sub and HTTP access to Grafana/InfluxDB."""

import argparse
import concurrent.futures
from datetime import datetime, timezone
import json
import re
import statistics
import subprocess
import sys
import time
from urllib.parse import urlencode
from urllib.request import urlopen


DEVICE = "vitocal-2048"
MEASUREMENT = '"vito_observation_v2"'
DEVICE_FILTER = f'"device" = \'{DEVICE}\''
DASHBOARD = "vito-2048-telemetry-v2"
SOURCE = "deasq3bzjrx8ge"


def require(condition, explanation):
    if not condition:
        raise ValueError(explanation)


def utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fetch(url):
    with urlopen(url, timeout=15) as response:
        return json.load(response)


def query(endpoint, statement):
    url = endpoint + "/query?" + urlencode({"db": "Vito", "q": statement})
    result = fetch(url)["results"][0]
    if "error" in result:
        raise ValueError(result["error"])
    return [dict(zip(s["columns"], row))
            for s in result.get("series", []) for row in s["values"]]


def subscribe(host, topic, wait):
    cmd = ["mosquitto_sub", "-h", host, "-t", topic, "-q", "1",
           "-C", "1", "-R", "-W", str(wait)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=wait+5)
    require(out.returncode == 0 and out.stdout.strip(),
            f"Live MQTT subscription {topic} failed: {out.stderr.strip()}")
    return json.loads(out.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="10.0.1.8")
    parser.add_argument("--wait", type=int, default=90, help="seconds to wait for live MQTT")
    parser.add_argument("--max-gap", type=float, default=60, help="maximum fast sample gap in seconds")
    args = parser.parse_args()
    require(args.wait > 0 and args.max_gap > 0, "Timeouts must be positive")
    db = f"http://{args.host}:8086"
    grafana = f"http://{args.host}:3000"
    proxy = f"{grafana}/api/datasources/proxy/uid/{SOURCE}"
    for uid in (DASHBOARD, "YItU9nUGz", "YItU9nUGz2"):
        d = fetch(f"{grafana}/api/dashboards/uid/{uid}")["dashboard"]
        require(d["uid"] == uid and d.get("panels"), f"Missing Grafana dashboard {uid}")

    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        legacy = pool.submit(subscribe, args.host, "vito/getEinschaltVerdichter", args.wait)
        v2 = pool.submit(subscribe, args.host, "vito/telemetry/v2/0500-4", args.wait)
        msg = v2.result()
        old = legacy.result()
    require(old.get("command") == "getEinschaltVerdichter", "Unexpected legacy payload")
    require(msg.get("device") == DEVICE and msg.get("register") == "0500-4", "Wrong producer or register")
    ts = msg["observed_at"]
    require(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z", ts), "Non-UTC timestamp")
    age = (datetime.now(timezone.utc) - utc(ts)).total_seconds()
    require(-5 <= age <= args.max_gap, f"Stale/future acquisition: age {age:.1f} s")
    counter = msg["counter_value"]
    raw = bytes.fromhex(msg["raw_hex"])
    require(len(raw) == 4 and int.from_bytes(raw, "little") == counter, "Raw/decoded starts mismatch")
    require(abs(float(old["value"])-counter) <= 1, "Legacy and v2 live starts differ by more than one")

    select = (f'SELECT * FROM {MEASUREMENT} WHERE {DEVICE_FILTER} AND '
              f'"register" = \'0500-4\' AND time = \'{ts}\'')
    deadline = time.monotonic()+args.wait
    while not (rows := query(db, select)) and time.monotonic() < deadline:
        time.sleep(2)
    require(len(rows) == 1, f"Expected one Influx point at MQTT acquisition time {ts}")
    for key in ("raw_hex", "counter_value", "quality", "decoder_version"):
        require(rows[0].get(key) == msg.get(key), f"MQTT/Influx mismatch in {key}")
    require(rows == query(proxy, select), "Grafana datasource returned different results")
    print(f"MQTT -> Influx -> Grafana: {ts} {msg['raw_hex']} = {counter} starts")
    window = f"WHERE {DEVICE_FILTER} AND time > now()-15m"
    for register in ("0500-4", "0580-4", "0414-1"):
        samples = query(db, f'SELECT "quality" FROM {MEASUREMENT} {window} '
                            f'AND "register"=\'{register}\' ORDER BY time DESC LIMIT 4')
        require(len(samples) >= 2, f"Need at least two recent samples for {register}")
        times = [utc(row["time"]) for row in samples]
        gaps = [(a-b).total_seconds() for a,b in zip(times, times[1:])]
        require((datetime.now(timezone.utc)-times[0]).total_seconds() <= args.max_gap, f"{register} stale")
        require(all(row["quality"] in ("ok","provisional") for row in samples),
                f"{register}: recent read error or uncertain decode: {samples}")
        require(max(gaps) <= args.max_gap, f"{register} gaps exceed target: {gaps}")
        print(f"{register}: median {statistics.median(gaps):.1f}s, maximum {max(gaps):.1f}s")
    sentinels = query(db, f'SELECT * FROM {MEASUREMENT} WHERE {DEVICE_FILTER} '
                          f'AND time > now()-24h AND "quality"=\'sentinel\' ORDER BY time DESC LIMIT 1')
    require(sentinels and sentinels[0].get("raw_hex"), "No raw sentinel sample in the last day")
    require(all(sentinels[0].get(k) is None for k in ("counter_value", "numeric_value")),
            "A sentinel was promoted to a numeric value")
    require(sentinels[0].get("register") in {f"16D{i}-2" for i in range(4)}
            and sentinels[0]["raw_hex"] == "FFFF", "Unexpected weekly energy sentinel")
    print(f"Sentinel preserved: {sentinels[0]['register']} {sentinels[0]['raw_hex']}")
    identity = query(db, f'SELECT "raw_hex","text_value" FROM {MEASUREMENT} WHERE {DEVICE_FILTER} '
                         f'AND "register"=\'00F8-8\' AND time > now()-24h ORDER BY time DESC LIMIT 1')
    require(identity and identity[0]["raw_hex"].startswith("2048")
            and identity[0]["text_value"] == "2048", "Missing recent 2048 hardware ID read")
    runtime = query(db, f'SELECT "raw_hex","counter_value" FROM {MEASUREMENT} {window} '
                        f'AND "register"=\'0580-4\' ORDER BY time DESC LIMIT 1')[0]
    seconds = int.from_bytes(bytes.fromhex(runtime["raw_hex"]), "little")
    require(runtime["counter_value"] == seconds, "Compressor runtime must retain integer seconds")
    print(f"Hardware {identity[0]['text_value']}, compressor runtime {seconds} s")
    health = query(db, f'SELECT * FROM "vito_reader_health_v2" WHERE {DEVICE_FILTER} '
                       f'AND time > now()-2m ORDER BY time DESC LIMIT 1')
    require(health and health[0].get("reads_ok", 0) > 0, "No fresh successful reader health report")
    print("Reader health:", json.dumps(health[0], sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as failure:
        sys.exit(f"Acceptance check failed: {failure}")
