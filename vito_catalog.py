"""Controller read catalogue. Effective names come from vcontrold detail, not XML order."""
from dataclasses import dataclass, field
from pathlib import Path
import xml.etree.ElementTree as ET


BASE = Path(__file__).resolve().parent
VERSION = '2048-v1'
STARTS = {'0500-4', '0508-4', '0509-4'}
RUNTIME = {'0580-4', '0588-4', '0589-4'}
VALVE = '0414-1'
TEMP = {f'{n}-2' for n in ('0101','0103','0104','0105','0106','010D','1801','6000','3000')}
STATES = {'0402-1', '0404-1', '0408-1', '0409-1'}
ENERGY = {f'16D{x}-2' for x in '0123'}
FAST = ['0500-4', '0580-4', VALVE]
THERMAL = ['0103-2','0104-2','0105-2','0106-2','010D-2','6000-2','1801-2','0101-2']


@dataclass
class Register:
    key: str
    aliases: dict = field(default_factory=dict)
    legacy: dict = field(default_factory=dict)


def catalogue(legacy, path=BASE/'active_reads.tsv'):
    regs = {}
    for line in path.read_text().splitlines():
        if line.startswith('#') or not line:
            continue
        name, address, length, unit = line.split()
        key = f'{address}-{length}'
        reg = regs.setdefault(key, Register(key))
        reg.aliases[name] = unit
        if name in legacy:
            reg.legacy[name] = legacy[name]
    missing = legacy.keys() - {name for r in regs.values() for name in r.legacy}
    if missing:
        raise ValueError(f'Missing active legacy reads: {missing}')
    return regs


def enum_units():
    units = {}
    for u in ET.parse(BASE/'vcontrold.xml').findall('.//unit'):
        units[u.findtext('abbrev')] = {
            e.get('bytes','').replace(' ', ''): e.get('text') for e in u.findall('enum')
        }
    return units


def decode(key, raw):
    if key in STARTS or key in RUNTIME:
        return dict(confidence='verified', quality='ok', counter_value=int.from_bytes(raw,'little'))
    if key == VALVE:
        label = {0:'UNDEV',1:'Heizen',2:'Mittelstellung',3:'Warmwasser'}.get(raw[0])
        if label and label != 'UNDEV':
            return dict(confidence='verified',quality='ok',text_value=label)
    if key in TEMP:
        return dict(confidence='provisional',quality='provisional',
                    numeric_value=int.from_bytes(raw,'little',signed=True)/10)
    if key in STATES and raw[0] in (0,1):
        return dict(confidence='provisional',quality='provisional',numeric_value=raw[0])
    if key in ENERGY and raw == b'\xff\xff':
        return dict(confidence='unknown',quality='sentinel')
    if key == '00F8-8':
        return dict(confidence='verified',quality='ok',text_value=raw[:2].hex().upper())
    return dict(confidence='unknown',quality='unmapped')
