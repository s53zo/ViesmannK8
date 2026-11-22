# Register coverage and interpretation

See [the coverage inventory](register-coverage.csv) for every getaddr definition in the installed XML. Reproduce it with `python3 ops/export_catalogue.py`. The daemon's resolved command names, addresses, byte lengths and legacy units are in [active_reads.tsv](../active_reads.tsv). Multiple XML rows can describe the same command and address. A shadowed entry cannot be requested by that name at the alternate address. Device-scoped XML annotations are source metadata, not positive identification of the unit.

We read through the working 204D/KW2 configuration on 2048 hardware. Identity is based on the first two bytes at 00F8. An effective row establishes a way to ask for bytes, not the meaning of those bytes. Defer unresolvable definitions while retaining the reason in the inventory. Do not change the device profile solely to increase coverage.

| Register | Working interpretation | Evidence and limitations |
|---|---|---|
| 0500-4 | Compressor switch-ons | Little-endian integer. The WO1B mapping and named read agree. Count changes between acquisition timestamps. |
| 0580-4 | Cumulative compressor runtime in seconds | Little-endian integer. Dividing by 3600 matches the daemon's reported operating hours. Preserve the integer before presentation. |
| 0414-1 | Heating / DHW diverter position | Text is decoded from the installed enum. 01 has been observed alongside Heizen. Installation-specific interpretation of other positions still needs comparison with the controller display. |
| 0508-4 / 0509-4 and 0588-4 / 0589-4 | Auxiliary heater stage starts and runtime | Existing commands returned plausible counts and hours. Their changes may help disambiguate whole-house pulses. |
| 0103-2 / 0104-2 and 0105-2 / 0106-2 | Source and secondary circuit temperatures | Provisional signed tenths of a degree. The source fluid and direction should be checked against the installation. Avoid assigning groundwater, underfloor or room labels from the command name alone. |
| 16D0-2 through 16D3-2 | Weekly energy candidates | All four returned FF FF on this unit. Preserve the bytes with a quality flag. A later different value also needs validated scaling before it can enter an efficiency calculation. |
| 0482-1, 081A-2 and 1680-2 | Unresolved status, sensor and performance inputs | Local names, equipment scope or unit conversions are uncertain. Preserve raw bytes for investigation. |

Reference material: [OpenV controller identification](https://github.com/openv/openv/wiki/Ger%C3%A4te) and [WO1B register research](https://github.com/openv/openv/issues/420#issuecomment-1345502824). Interpretations can be revised without rewriting the observed bytes.
