"""Export XML definitions alongside the daemon's resolved, read-only command list."""
import csv
import sys
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]


def export(output):
    actual = {}
    for line in (ROOT / "active_reads.tsv").read_text().splitlines():
        if line and not line.startswith("#"):
            name, address, length, unit = line.split()
            actual[name] = (address, length, unit)
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("command", "address", "length_bytes", "legacy_unit", "xml_profiles",
                     "resolution", "effective_register", "xml_description"))
    for element in ElementTree.parse(ROOT / "vito.xml").findall(".//command"):
        if element.get("protocmd") != "getaddr":
            continue
        name = element.attrib["name"]
        address = (element.findtext("addr") or "").strip().upper()
        length = (element.findtext("len") or "").strip()
        unit = (element.findtext("unit") or "").strip()
        active = actual.get(name)
        if active is None:
            resolution = "unavailable by name"
        elif active == (address, length, unit):
            resolution = "effective definition"
        else:
            resolution = "shadowed definition"
        profiles = " ".join(d.attrib["ID"] for d in element.findall("device"))
        description = " ".join((element.findtext("description") or "").split())
        writer.writerow((name, address, length, unit, profiles, resolution,
                         "-".join(active[:2]) if active else "", description))


if __name__ == "__main__":
    export(sys.stdout)
