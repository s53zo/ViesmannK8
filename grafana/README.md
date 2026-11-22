# Heat-pump dashboard

The dashboard UID is `vito-2048-telemetry-v2`. Open [Viessmann heat pump telemetry](http://10.0.1.8:3000/d/vito-2048-telemetry-v2/) on the LAN. Data begins with the v2 reader cutover.

Dashboard JSON is the source of truth. Use the ordinary Grafana JSON import, or publish it with `python3 grafana/publish.py` using a dashboard editor's `GRAFANA_TOKEN` from the environment. Set `GRAFANA_URL` for a different host. For installation on another Grafana instance, remap `deasq3bzjrx8ge` to its InfluxQL data source for database `Vito` and `fe9liwluvfev4d` to its InfluxQL data source for house power. `-- Mixed --` and `__expr__` identify Grafana's built-in query engines. Keep the acquisition device identifier in the queries aligned with the reader.

## Panel and query dictionary

| Panel | Data and interpretation |
|---|---|
| Controller totals | Controller starts (0500, four bytes) and runtime in hours (0580, four bytes, divided by 3,600). |
| Starts by hour and day | Sum of nonnegative differences from adjacent reads. The first sample in the selected window establishes a baseline. Resets are skipped. UTC buckets at the edges may be partial. |
| Whole-house power and observed starts | Site power comes from the grafana database. The second axis shows observed changes in the start counter. Several starts can occur between two successful polls. |
| Minutes per start | Computes elapsed runtime minutes divided by starts over the range. Requires both endpoints within 90 seconds for both registers, at least one start, no counter decrease and no successful-read gap over 90 seconds. A running partial cycle can contribute runtime. Choose a range wholly after collection began. |
| Operating state | DHW/heating valve 0414, provisional source and secondary outputs 0402/0404 and auxiliary stages 0408/0409. Empty 30-second buckets expose gaps and polling jitter. |
| Auxiliary heater totals | Stage 1 and 2 starts (0508/0509) and hours (0588/0589). |
| Source fluid | 0103/0104. Inlet/outlet orientation requires physical confirmation. |
| Secondary water and DHW | Heating supply/return 0105/0106, M2 circuit target 1801, domestic hot water tank top 010D and hot water target 6000. |
| Source and secondary ΔT | Subtracts the latest valid numeric reads found in each common 15-second bucket. Reads straddling bucket boundaries can be omitted. |
| Energy channels awaiting validation | Raw bytes and decoding disposition for the four weekly registers and JAZ register. An engineering value requires a confirmed encoding, units and reporting period. |
| Reads and failures | Reader-reported successful, failed and discarded counts. Inspect process restarts before interpreting a decline. |
| Latency and freshness | Last serial latency, worst fast-read lateness, age of successful reading and oldest pending observation. |
| Catalogue coverage and spool | Keys attempted versus catalogue size, and pending samples. |
| Compressor polling cadence | Elapsed seconds between consecutive successfully decoded start-counter samples. |
| Read errors and register observations | Most recent 30 error/partial attempts or 250 matching acquisitions in the selected range. Register, confidence and quality selectors apply to the observations table. Missing typed fields are expected on unknown or failed attempts. |

## Verification

Run `python3 grafana/verify.py --published` to check the deployed JSON, the existing dashboards and all panel queries. The default query range is three hours. With `--fixtures` the verifier creates a uniquely named temporary InfluxDB database, evaluates the actual Grafana queries against controlled values, and drops only its own test database. Cases cover resets, zero increments, stale endpoints, an internal outage, an empty window, state text, unknown bytes and thermal-pair timing.
