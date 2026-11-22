# Operating the Viessmann reader

The controller host runs a single polling service, vito_mqtt.service. The vcontrold.service process owns the serial port. The existing Node-RED Viessmann tab handles both legacy input and the new observation branch. Passwords, Grafana sessions and private Node-RED backups belong outside this repository.

## Deploy an accepted reader release

Deploy storage and verify its acknowledgement path first. From a clean checkout of the accepted Git revision, export the committed source into a new directory under /opt/vito-telemetry/releases on the reader. Use the Git SHA as the directory name. Do not include Git credentials, a .git directory or runtime data in the release. The host supplies Python 3 and python3-paho-mqtt. As root on the reader, run:

```sh
sh "$release/ops/reader-deploy.sh" activate "$release"
systemctl status vito_mqtt --no-pager
journalctl -u vito_mqtt --since "5 minutes ago" --no-pager
```

Activation replaces the reader command via a systemd drop-in and restarts the single service. With the original unit in place, the following rollback restores the saved baseline entrypoint:

```sh
sh "$release/ops/reader-deploy.sh" rollback
```

Allow the baseline unit's original 75-second startup delay. Confirm legacy MQTT timestamps advance afterwards. Rollback retains the v2 database history and spool. Node-RED and Grafana can be rolled back independently if the fault is there. Never delete the live database or the reader's spool to recover from a temporary downstream outage.

## Diagnose missing points

1. Check vito_mqtt and vcontrold on the reader. Compare journal timestamps with UTC on the database host. A recent MQTT connection alone does not prove a successful controller read.
2. Inspect the reader health series and individual register qualities. A confirmed zero, undecoded replies and failed reads have different meanings. If legacy values appear frozen, check the MQTT message timestamp before interpreting a retained reading.
3. Compare a v2 MQTT observation's register and UTC acquisition time with its Influx point. Check Node-RED's HTTP write result and acknowledgement path. During an Influx or MQTT outage the pending count and oldest unconfirmed age should grow, then fall after recovery. Check disk and overflow counters if backlog persists.
4. Inspect Grafana's selected data source, range and register filter. An old dashboard's alias or database is not an independent measurement. Use the register catalogue and physical diagnostics when assigning an interpretation.

## Capacity and timing

The configured schedule covers 187 keys: three at 30 seconds, twelve at two minutes, four at three minutes, 43 at fifteen minutes and 125 at one hour. With one health point every 30 seconds, the nominal budget is 29,208 points per day, before timing jitter and error backoff. Vito's autogen policy currently retains these indefinitely. The existing Vito data directory measured about 33 MiB before rollout; that includes legacy data. Measure actual disk growth across a completed shard interval before projecting long-term compression or changing retention.

On the netboot reader, SQLite keeps an exclusive single-writer lock and a persistent rollback journal. Capacity is 40,000 pending samples with a per-sample payload ceiling of 8 KiB. At the nominal rate this covers around 33 hours of downstream outage; it depends on the actual rate and available space. Once full, the oldest pending records are evicted and the dropped count increases. A NAS outage can also affect the reader's NFS root itself; the spool protects against broker/database service interruptions while that filesystem is available.

## Serial-session recovery

A debug client that disappears during an optical read can leave an old vcontrold worker writing to a closed socket. Symptoms observed during commissioning were consecutive timeouts and repeated SIGPIPE entries in /etc/vcontrold/vcontrol.log. The final reader handles SIGTERM at a transaction boundary, sends quit, drains the response and yields its connection after bounded batches. Use ordinary systemd stop/restart so this handshake can run. On a genuinely stuck daemon, stop the reader, restart vcontrold and verify a named read before restoring the reader. This interrupts telemetry; it must not send a heating control command.
