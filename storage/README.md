# Versioned telemetry ingestion

The five Node-RED nodes live on the existing Viessmann tab and reuse its MQTT broker configuration. The incoming subscription is `vito/telemetry/v2/+` at QoS 1. Each accepted observation becomes an InfluxDB line-protocol point in the existing `Vito` database, using the collector's UTC acquisition timestamp at nanosecond precision.

| Measurement | Tags | Fields |
| --- | --- | --- |
| `vito_observation_v2` | `device`, `register` (address-length, e.g. `0500-4`) | Required strings `quality`, `decoder_version`. Optional strings `name`, `tier`, `confidence`, `raw_hex`, `text_value`. Signed integer `counter_value`. Floating-point `numeric_value`, `latency_ms`. |
| `vito_reader_health_v2` | `device` | Integer `reads_ok`, `reads_failed`, `backlog`, `dropped`, `catalogue_size`, `attempted_registers`. Floating-point `last_latency_ms`, `max_fast_lateness_s`, `last_success_age_s`, `oldest_backlog_age_s`. The incoming register key is `_health`. |

A successful Influx HTTP 204 produces a non-retained QoS 1 acknowledgement on `vito/ack/v2/<device>`, containing the original `register` and `observed_at`. The collector owns the bounded persistent spool. It deletes a sample on this application acknowledgement. After a database/network outage, restarting Node-RED, or losing an acknowledgement, retrying the same immutable observation writes the same Influx point. Acquisition timestamps must therefore be unique per device and register for distinct observations. Protocol validation errors appear in Node-RED logs; examine the collector backlog and dropped count if writes stop.

## Test, deploy and roll back

Run `node storage/test_storage.js` with a working Node runtime. The tests exercise immutable retries, full precision, zero counters, unknown/text values, missing bytes on a timeout, malformed inputs, health routing and acknowledgement policy.

Install or update the branch with the following command. The deployment uses the v2 flow revision and the modified-node deployment mode.

```sh
python3 storage/deploy.py --node-red http://10.0.1.8:1881 --influx http://10.0.1.8:8086
```

Add `--remove` to remove the five production nodes. The collector can spool observations during a temporary rollback. The script accepts `NODE_RED_TOKEN` for authenticated editors. The write endpoint uses the current LAN Influx configuration. The script assumes HTTP write access to the named database.

For isolated verification use `--stage` with fixture database `Vito_Ingest_Fixture`, input `vito/staging/v2/+`, and ACK output `vito/staging-ack/v2/<device>`. Use a fixture device ID and explicit timestamp. With the fixture database absent, expect no ACK. Create the fixture database, publish the same test observation twice, and verify both acknowledgements and one stored point. Remove the stage nodes using `--stage --remove` and delete the disposable test database after verifying its ownership.
