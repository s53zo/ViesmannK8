# Production commissioning, 22 November 2026

The reader at 10.0.1.82 runs b2ab2ec under the existing vito_mqtt service. The same USB daemon and database Vito serve the new release. The final reader was restarted at 06:11:38 UTC. A fresh v2 count arrived at 06:11:40.690929 UTC, and the daemon remained running across the restart.

## Acceptance evidence

- Twelve offline regression tests passed on the actual reader, including an abrupt process exit with unacknowledged records, overflow, retry, lost acknowledgements and clean serial shutdown.
- The live acceptance check matched a fresh legacy count, the v2 MQTT observation, the direct Influx point and the Grafana data-source result. At 06:15:21.214645 UTC the counter contained 52 9F 00 00, or 40,786 starts. Original acquisition time and bytes matched.
- The last three fast-register intervals in that acceptance check had medians of 32.0, 32.1 and 32.0 seconds (starts, runtime and valve). All 57 legacy topics had fresh samples from the final release. The reference legacy compressor series had intervals of 183–201 seconds before implementation.
- The physical ID began with 20 48. Four-byte runtime retained integer seconds, and weekly energy FF FF was preserved with sentinel quality. Valve 00 was stored as Unknown (0x00). No heat-pump controls were operated as part of acceptance.
- The isolated write test withheld the storage ACK on Influx failure, then replayed an identical sample twice and obtained a single nanosecond-timestamped point. The existing Node-RED tab contains the five v2 nodes beside its legacy path. The new dashboard has 17 data panels in five sections. All 50 data-source queries matched independent Influx queries, and a browser check found no panel rendering errors.
- An intermediate restart identified a daemon child logging SIGPIPE and blocking other reads. The affected workers were cleared with a controlled daemon restart; the final release drains the connection on shutdown. Old logs remain on the host. Ordinary reader restart was verified on the fixed release.

## Interpretation still awaiting physical confirmation

Use the actual controller display during a space-heating and a domestic-hot-water cycle to validate valve and pipe labels. An unclassified valve position remains visible. Household watts cover the entire site and cannot isolate compressor power. Performance factors and energy conversions stay provisional while the raw history accumulates.

## Completed discovery sweep

At 06:35:02 UTC on the final release, health reported 515 successful reads, zero failed reads, zero dropped samples and one pending observation younger than two seconds. A separate Influx query compared registers containing raw bytes since restart with the effective catalogue. All 187 keys matched. The last quality for each key comprised 7 ok, 13 provisional, 163 unmapped and 4 sentinel. This validates collection coverage; physical interpretation of uncertain registers remains open. The valve returned 00 throughout this acceptance interval.
