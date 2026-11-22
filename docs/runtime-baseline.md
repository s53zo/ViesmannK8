# Viessmann production baseline, 22 November 2026

The pre-overhaul collector is captured in Git at f70dc5b. On the reader, the original checkout is under /home/s53zo/ViesmannK8. A private backup, including the installed service units, is under /home/s53zo/vito-overhaul-baseline.Cv3YKi. The reader boots from NFS. The system clock reported NTP synchronization.

The installed unit waits 75 seconds at startup and launches the Python reader as root. The other service owns the USB serial adapter. Keep the existing daemon and device ownership during deployment. Prior to cutover, the latest seven compressor-start writes were 40,785 with intervals of 183–201 seconds. The configured profile is 204D but the hardware returned ID 2048. Keep raw observations and distinguish validated measurements from uncertain interpretations.

On SynK8, /volume1/docker/vito-overhaul-baseline.3zQI8m is a private snapshot of the Node-RED deployment and both existing dashboard definitions. The flow revision before installation was 1fdd89071ddedbca40ada57f27bf5dbc52291eaa80692b583153d069c9854490. Remote dashboard version 69, panel 34, had ten targets. The new dashboard uses a separate UID. Existing Node-RED consumers use one-level telemetry topics and existing controls use the set subtree.

InfluxDB 1.8 stores Vito data in the unlimited autogen retention policy. Do not assume the rest of the NAS volume is available for this service. Monitor measurement growth and spool usage with the new reader before increasing the discovery rate.
