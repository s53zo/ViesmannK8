#!/bin/sh
# Run on the collector as root with an extracted, committed release.
set -eu
unit=vito_mqtt.service
dropdir=/etc/systemd/system/$unit.d
override=$dropdir/50-telemetry-v2.conf
case "${1:-}" in
rollback)
    if [ -e "$override" ]; then
        rm "$override"
        systemctl daemon-reload
        systemctl restart "$unit"
    fi
    exit 0 ;;
activate) ;;
*) echo "usage: $0 activate RELEASE_DIRECTORY | rollback" >&2; exit 2 ;;
esac
release=$(realpath "${2:?release directory required}")
case "$release" in
    /opt/vito-telemetry/releases/*) ;;
    *) echo "expected a release under /opt/vito-telemetry/releases/" >&2; exit 2 ;;
esac
test -r "$release/reader_v2.py"
test -r "$release/vito.xml"
test -r "$release/vcontrold.xml"
systemctl is-active --quiet vcontrold.service
/usr/bin/python3 -c 'import paho.mqtt.client, sqlite3'
install -d -m 0755 "$dropdir"
next=$(mktemp "$dropdir/.telemetry-next.XXXXXX")
prev=$(mktemp "$dropdir/.telemetry-prev.XXXXXX")
had_override=false
if [ -f "$override" ]; then
    cp -p "$override" "$prev"
    had_override=true
fi
trap 'rm -f "$next" "$prev"' EXIT
cat > "$next" <<UNIT
[Unit]
After=vcontrold.service
[Service]
WorkingDirectory=$release
StateDirectory=vito-telemetry
UMask=0077
ExecStartPre=
ExecStart=
ExecStart=/usr/bin/python3 $release/reader_v2.py
UNIT
chmod 0644 "$next"
mv "$next" "$override"
if ! (systemctl daemon-reload && systemctl restart "$unit" && systemctl is-active --quiet "$unit"); then
    if "$had_override"; then cp -p "$prev" "$override"; else rm -f "$override"; fi
    systemctl daemon-reload
    systemctl restart "$unit"
    exit 1
fi
