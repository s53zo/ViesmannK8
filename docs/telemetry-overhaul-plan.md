# Viessmann telemetry overhaul

Planning baseline: 22 November 2026. Repository: s53zo/ViesmannK8. This plan covers the reader, MQTT contract, Node-RED ingestion, InfluxDB storage and a new Grafana dashboard. Implementation begins after the owner requests it.

## What we are building against

- On 10.0.1.82, vcontrold owns the USB serial adapter. The live ID bytes at 0x00F8 are 20 48 02 09 00 00 03 46. The active configuration selects 204D/KW2 and the XML includes definitions for several families. A model-plate match and comparisons with controller diagnostics are still needed. Preserve the working serial transport while validating individual mappings.
- The Python service polls 57 distinct commands in roughly three minutes and publishes retained JSON on 10.0.1.8:1883. Existing controls use vito/set/... . On the device, vito_mqtt.py and both systemd unit files differ from Git main at ff19ede. Keep the live changes recoverable.
- The existing flow on Node-RED port 1881 consumes vito/+, rounds numeric values and generally writes changes to InfluxDB 1.8 database Vito. The compressor-start counter is sampled each cycle. Vito's current default autogen policy has unlimited duration. Preserve existing topics, measurements, controls, dashboards and their consumers during migration.
- Five temperature targets on the old Viessman dashboard query a different database; the data is in Vito. A room input is labeled as floor water and two pump states as heating modes. Four weekly energy commands returned FF FF, which the existing hours conversion turned into 18.2. These are regression fixtures for the overhaul.

## Delivery sequence and Git checkpoints

Use a feature branch and commit each independently tested change. Include the rationale, verification and known gaps in Git trailers. Push at each working milestone. Record the Git SHA and deployed config revision at each rollout. Keep credentials, full live Node-RED exports, editor sessions and private backups outside Git.

| Step | Deliverable and intended commit boundary | Evidence required before proceeding |
|---|---|---|
| 1. Capture the baseline | Reconcile the three live diffs against main. Commit intentional production behavior, including the counter. Record service arguments, protocol, recorder revision, data-source UID and rollback steps. Make a private restorable snapshot of live settings and affected flow nodes. | Explain each diff. Confirm a fresh counter sample, verify the live services and identify which existing consumers use the legacy topics. |
| 2. Catalogue and fixture the reads | Build a versioned register catalogue from the named XML read definitions. Track address, byte length, alias, scope/device family, raw byte order, unit, scale, enumeration, sentinel rules, evidence, confidence and polling tier. Commit representative sanitized captures separately from decoder changes. | Reproduce identity, 0x0500 starts, 0x0580 runtime, the four FF FF reads and the diverter text. Account for duplicate names that resolve to different addresses and aliases that read the same bytes. |
| 3. Replace the polling loop | Implement one serialized reader through the existing daemon. Trial a persistent client or small batches, selected after timing on this host. Use monotonic deadlines, bounded retries/backoff and UTC acquisition timestamps. Read identical address/length combinations once per due interval. Serialize existing validated control requests through the same device-access queue; never replay control commands. | Simulated partial replies, timeout, disconnect and slow register recover without starving fast reads. Test the existing control contract against fixtures. Measure polls per minute, lateness, read latency and error rate against baseline. |
| 4. Extend the current MQTT and storage flow | Add a versioned observation branch on the existing broker and Node-RED flow. Write into the existing Vito database using new measurements. Commit the contract, sanitized node definitions and replay tests. Keep the old publisher payloads available from the same reads. | An isolated replay stores unchanged values, text, unknown bytes, failure status and precise runtime. Duplicate delivery creates one observation. An outage test shows what was buffered, replayed or lost. |
| 5. Ship the new dashboard | Commit a portable dashboard JSON with a new UID, explicit Vito data-source mapping and a separate mapping for house power. Create it alongside the existing dashboards. Include a panel/query dictionary. | Compare every panel with a direct query for the same device, time range and timezone. Exercise empty, stale, sparse, reset and unknown-value cases. Confirm both old dashboard UIDs still resolve. |
| 6. Stage and roll out | Test end to end with a simulated reader and isolated topics first. Deploy the compatible ingestion branch before switching reader processes. Use the new reader as the sole live poller; have it publish legacy and new telemetry during comparison. Tag the accepted release. | Compare corresponding raw values, sample times, legacy topic freshness and DB records. Observe at least one heating and one DHW cycle when available. Label physical mappings provisional until observed. Verify recovery after a reader restart and an MQTT outage. |

## Polling and treatment of unknowns

Start with these trial cadences. Tune them against measured device response times and serial-bus occupancy.

- **Fast, initially 20–30 seconds:** cumulative compressor starts, runtime with second-level precision and heating/DHW valve state. Trial compressor and heater-stage states once their addresses are identified. Report effective sample spacing; poll time bounds the precision of any event time.
- **Thermal, initially 1–3 minutes:** source-side and heating-side supply/return pairs, DHW tank and target, circuit supply target. Schedule each temperature pair together and timestamp each response.
- **Slow, initially 15–60 minutes:** configuration, energy statistics, load classes and model-specific candidates. Run a slow discovery queue through the catalogue's known read addresses, including uncertain and duplicate-name candidates. Address and length identify these reads. Use spare polling capacity and retry unsupported or repeatedly failing reads less often. Keep a coverage list with last attempt, result and reason for any deferred entry. Do not sweep undocumented memory or invoke set commands.
- Store a real reply even when its interpretation is unknown. Preserve bytes for FF FF, zero, unknown enums and unrecognized device IDs. Mark a sentinel invalid only for a documented or validated register; zero and all-ones can be legitimate elsewhere. A timeout has an attempt record and no invented bytes or numeric value. Preserve old observations when a decoder is revised so raw history can be reinterpreted later.

## Observation contract and InfluxDB design

Proposed topic: vito/telemetry/v2/<register-key>. Its extra path levels keep samples outside the existing vito/+ subscription. Use one sample identity per acquisition, stable through retries. Keep observation messages separate from commands. Preserve retained behavior for existing topics; use non-retained QoS 1 for new observation events and a separate availability topic.

| New measurement in Vito | Proposed contents |
|---|---|
| vito_observation_v2 | One point per device, register key and acquisition time. Bounded tags identify device and register, including length where necessary. Store raw hex, decoder version, quality, and typed fields for decoded numeric, integer counter or text when available. Keep field types stable. Preserve the raw point for both verified and provisional decoders. |
| vito_reader_health_v2 | Successful and failed reads, last successful cycle, actual cadence, serial latency, MQTT backlog, dropped or expired samples and clock health. Bound error categories and keep free-form error text out of tags. |

Use timezone-aware UTC observation time as the Influx point timestamp; carry it unchanged through MQTT and Node-RED. Distinguish observation from receipt time. The collector should use a bounded, persistent telemetry spool; trim by an explicit disk budget and surface overflow. Test the Node-RED-to-Influx failure path separately: broker acknowledgement alone does not confirm database persistence. Define durable retry/dead-letter behavior and confirm an interrupted write is recoverable. Influx retries must reproduce the same measurement, tag set and timestamp. Estimate points/day and disk consumption from staging before increasing discovery throughput. Keep unknown history for later review; changing retention or pruning data is a separate owner decision.

## New Grafana dashboard

| Row | New panels and interpretation |
|---|---|
| Compressor cycling | Cumulative starts and runtime, starts per hour/day, runtime per start for the chosen window, and whole-house power with observed counter changes. Treat a jump of three as three starts somewhere between polls. Suppress ratios for zero starts, resets or inadequate coverage. |
| Operating mode and auxiliary heat | Heating/DHW diverter as a state timeline, validated pump and compressor states, auxiliary heater stages plus stage starts/runtime. Keep unknown periods visible. |
| Temperatures and hydraulics | Paired source inlet/outlet, paired secondary supply/return, each pair's temperature difference, M2 supply target and DHW actual/target. Derive differences only from sufficiently close successful reads. Confirm sensor orientation against the controller. |
| Energy and efficiency | Show only energy channels with verified unit, scale and interval. Enable calculated efficiency after matching electrical and thermal energy windows. Until then show validation status and raw diagnostics. |
| Register explorer and reader health | Filter by register, confidence and quality; show raw bytes, provisional decode, source age, last error, effective polling interval and catalogue coverage. Expose flat readings separately from missing samples. |

Use separate axes and units for watts, counts, hours and temperatures. State panels use state transitions or last samples. Document boundary approximations for time-window calculations. Display house consumption as whole-house watts; a dedicated circuit meter would be needed to isolate heat-pump electrical demand directly.

## Cutover and rollback

Stage the new dashboard and ingestion branch independently. At the reader switch, stop the legacy polling process, start the candidate and verify live legacy and v2 telemetry. If legacy topics stall, commands regress, serial errors rise persistently or timestamps/values are corrupted, stop the new reader and restart the captured baseline. The old flows and dashboards remain available; isolate the new branch if needed and retain its collected data. Test the sequence before production. Future register promotions, renames and exclusions get their own reviewed commits.
