#!/usr/bin/env python3
"""Single-owner named-register reader with persistent application-acknowledged telemetry."""
import argparse
from datetime import datetime, timezone
import json
import logging
import math
import subprocess
from pathlib import Path
from queue import Full, Queue
import re
import socket
import sqlite3
import time

from vito_catalog import FAST, THERMAL, STATES, VERSION, catalogue, decode, enum_units

LOG = logging.getLogger('vito-reader')
DEVICE = 'vitocal-2048'
PREFIX = 'vito/telemetry/v2/'
ACK = 'vito/ack/v2/' + DEVICE
READ_TIMEOUT = 8
MAX_PAYLOAD = 8192


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')


class Session:
    """The daemon returns one prompt per command. Discard timed-out sessions."""
    def __init__(self, host='127.0.0.1', port=3002):
        self.host, self.port = host, port
        self.sock = None

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def reply(self):
        data = bytearray()
        deadline = time.monotonic() + READ_TIMEOUT
        while not data.endswith(b'vctrld>'):
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('command deadline')
            self.sock.settimeout(remaining)
            part = self.sock.recv(8192)
            if not part:
                raise ConnectionError('daemon disconnected')
            data.extend(part)
            if len(data)>65536:
                raise ValueError('oversize daemon reply')
        return data[:-7].decode('utf-8','replace')

    def read(self, name, key):
        if not self.sock:
            self.sock = socket.create_connection((self.host,self.port),READ_TIMEOUT)
            self.reply()
            self.sock.sendall(b'debug on\n')
            self.reply()
        self.sock.sendall((name+'\n').encode('ascii'))
        reply = self.reply()
        # Verify the KW2 frame actually sent by the daemon before attributing its bytes.
        sent = re.findall(r'>SENT: ([\da-fA-F]{2})',reply)
        addr, size = key.split('-')
        expected = bytes.fromhex('01F7'+addr) + bytes([int(size)])
        if expected not in bytes.fromhex(''.join(sent)):
            raise ValueError('daemon register differs from catalogue or transaction failed')
        received = re.findall(r'<RECV: received ([0-9A-Fa-f ]+)\r?$',reply,re.M)
        formatted = '\n'.join(l.strip() for l in reply.splitlines()
                              if not l.startswith(('DEBUG:', 'ERR:')) and l.strip())
        if received:
            return bytes.fromhex(received[-1]), formatted or None
        chunks = re.findall(r'<RECV: len=1 ([0-9a-fA-F]{2}) ', reply)
        if chunks and len(chunks)<int(size):
            return bytes.fromhex(''.join(chunks)), None
        raise ValueError('no completed register response')


class Spool:
    """A single thread owns the SQLite connection, including ACK deletions."""
    def __init__(self, path, capacity=40000):
        path = Path(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        self.db = sqlite3.connect(path)
        # This single writer runs on an NFS-root Pi. Reuse the rollback journal
        # and keep its lock to avoid file creation/unlink for every sample.
        self.db.execute('PRAGMA locking_mode=EXCLUSIVE')
        self.db.execute('PRAGMA journal_mode=PERSIST')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA temp_store=MEMORY')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS pending (
                id INTEGER PRIMARY KEY, reg TEXT, ts TEXT, body TEXT, UNIQUE(reg,ts));
            CREATE TABLE IF NOT EXISTS stats (id INTEGER PRIMARY KEY, dropped INTEGER);
            INSERT OR IGNORE INTO stats VALUES (1,0);
            CREATE TEMP TABLE delivery (id INTEGER PRIMARY KEY, next_try REAL NOT NULL);
            CREATE INDEX temp.delivery_deadline ON delivery(next_try,id);
            INSERT INTO delivery SELECT id,0 FROM pending;
        ''')
        self.capacity = capacity

    def _delete_acknowledged(self, acknowledgements):
        for reg, ts in acknowledgements:
            self.db.execute(
                'DELETE FROM delivery WHERE id=(SELECT id FROM pending WHERE reg=? AND ts=?)',
                (reg, ts))
            self.db.execute('DELETE FROM pending WHERE reg=? AND ts=?', (reg, ts))

    def put(self, sample, acknowledgements=()):
        body = json.dumps(sample, allow_nan=False, separators=(',', ':'))
        if len(body.encode()) > MAX_PAYLOAD:
            raise ValueError('observation exceeds storage budget')
        # Group end-to-end ACKs with the next mandatory durable acquisition write.
        # On a crash, uncommitted ACKs cause idempotent retries from disk.
        with self.db:
            self._delete_acknowledged(acknowledgements)
            row = self.db.execute('INSERT INTO pending(reg,ts,body) VALUES(?,?,?)',
                                  (sample['register'], sample['observed_at'], body))
            self.db.execute('INSERT INTO delivery VALUES(?,0)', (row.lastrowid,))
            excess = self.db.execute('SELECT count(*)-? FROM delivery', (self.capacity,)).fetchone()[0]
            if excess > 0:
                self.db.execute('DELETE FROM delivery WHERE id IN '
                                '(SELECT id FROM pending ORDER BY id LIMIT ?)', (excess,))
                self.db.execute('DELETE FROM pending WHERE id IN '
                                '(SELECT id FROM pending ORDER BY id LIMIT ?)', (excess,))
                self.db.execute('UPDATE stats SET dropped=dropped+?', (excess,))

    def acknowledge(self, reg, ts):
        with self.db:
            self._delete_acknowledged([(reg, ts)])

    def flush(self, client, now):
        rows = self.db.execute(
            'SELECT d.id,p.reg,p.body FROM delivery d JOIN pending p ON p.id=d.id '
            'WHERE d.next_try<=? ORDER BY d.next_try,d.id LIMIT 16', (now,)).fetchall()
        # Only the in-memory retry index changes after transport accepts a send.
        with self.db:
            for ident, reg, body in rows:
                if client.publish(PREFIX + reg, body, qos=1, retain=False).rc:
                    break
                self.db.execute('UPDATE delivery SET next_try=? WHERE id=?', (now+30, ident))

    def stats(self):
        count, oldest=self.db.execute('SELECT count(*),min(ts) FROM pending').fetchone()
        dropped=self.db.execute('SELECT dropped FROM stats').fetchone()[0]
        age=time.time()-datetime.fromisoformat(oldest.replace('Z','+00:00')).timestamp() if oldest else 0
        return dict(backlog=count,dropped=dropped,oldest_backlog_age_s=max(0,age))


class Schedule:
    def __init__(self, regs, now):
        self.due={}
        self.intervals={}
        self.errors={}
        self.rank={}
        self.fast_lateness=0.0
        # First revisit fast diagnostics; interleave legacy and discovery fairly thereafter.
        slow_index=0
        for key,reg in regs.items():
            if key in FAST:
                interval,offset=30,0
            elif key in THERMAL or key in STATES:
                interval,offset=120,0
            elif key in {'0508-4','0509-4','0588-4','0589-4'}:
                interval,offset=180,0
            elif reg.legacy:
                interval,offset=900,(slow_index%50)*2
                slow_index+=1
            else:
                interval,offset=3600,60+(slow_index%200)*7
                slow_index+=1
            priority=FAST.index(key) if key in FAST else 10+(THERMAL.index(key) if key in THERMAL else 20)
            self.intervals[key]=interval
            self.rank[key]=priority
            self.due[key]=now+offset

    def next(self, now):
        ready=[k for k,v in self.due.items() if v<=now]
        if not ready:
            return None
        fast=[k for k in ready if k in FAST]
        # Oldest relative deadline eventually brings every due slow read forward.
        key=min(fast or ready,key=lambda k: ((self.due[k]-now)/self.intervals[k],self.rank[k]))
        if key in FAST:
            self.fast_lateness=max(self.fast_lateness,now-self.due[key])
        return key

    def complete(self,key,start,end,success):
        self.errors[key]=0 if success else min(5,self.errors.get(key,0)+1)
        self.due[key]=max(end,start+self.intervals[key]*(2**self.errors[key]))


def validated_control(msg, params):
    if msg.retain or msg.dup or not msg.topic.startswith('vito/set/'):
        raise ValueError('retained, duplicate or invalid control topic')
    name=msg.topic[len('vito/set/'):]
    if name not in params:
        raise ValueError('unknown control')
    conf=params[name]
    value=json.loads(msg.payload)['value']
    if conf['type']=='numeric':
        if isinstance(value,bool):
            raise ValueError('invalid numeric value')
        value=float(value)
        if not math.isfinite(value) or not conf['min']<=value<=conf['max']:
            raise ValueError('out-of-range control')
    elif value not in conf['values']:
        raise ValueError('unsupported enum')
    return name,value


def observation(reg,session):
    started=time.monotonic()
    # Prefer the legacy alias so its formatted output preserves exact vcontrold semantics.
    name=next(iter(reg.legacy or reg.aliases))
    out=dict(device=DEVICE, register=reg.key, name=name, decoder_version=VERSION,
             tier='fast' if reg.key in FAST else 'thermal' if reg.key in THERMAL else
                  'diagnostic' if reg.key in STATES or reg.key in {'0508-4','0509-4','0588-4','0589-4'} else 'slow',
             confidence='unknown')
    formatted=None
    try:
        raw,formatted=session.read(name,reg.key)
        out['raw_hex']=raw.hex().upper()
        if len(raw)!=int(reg.key.split('-')[1]):
            out['quality']='partial'
            formatted=None
        else:
            out.update(decode(reg.key,raw))
            if reg.key == '0414-1' and out['quality'] == 'unmapped':
                out['text_value'] = f'Unknown (0x{raw.hex().upper()})'
    except (OSError,ValueError) as exc:
        session.close()
        out['quality']='timeout' if isinstance(exc,TimeoutError) else 'read_error'
        LOG.warning('Read %s failed: %s',reg.key,exc)
    out['observed_at']=stamp()
    out['latency_ms']=round(1000*(time.monotonic()-started))
    return out,formatted


def main():
    import paho.mqtt.client as mqtt
    import vito_mqtt as legacy
    parser=argparse.ArgumentParser()
    parser.add_argument('--state-dir',default='/var/lib/vito-telemetry')
    parser.add_argument('--broker',default=legacy.MQTT_HOST)
    parser.add_argument('--broker-port',type=int,default=legacy.MQTT_PORT)
    args=parser.parse_args()
    commands={**legacy.PLAUSIBLE_COMMANDS,**legacy.SUSPICIOUS_COMMANDS,**legacy.ADDITIONAL_COMMANDS}
    regs=catalogue(commands)
    units=enum_units()
    spool=Spool(Path(args.state_dir)/'spool.sqlite3')
    session=Session()
    client=mqtt.Client(client_id='vito-reader-v2')
    acks, controls=Queue(2048),Queue(8)
    client.max_queued_messages_set(64)
    client.will_set('vito/status/v2/availability','offline',qos=1,retain=True)

    def connected(client,userdata,flags,rc):
        if rc==0:
            client.subscribe([(ACK,1),(legacy.MQTT_SET_TOPIC,0)])
            client.publish('vito/status/v2/availability','online',qos=1,retain=True)

    def message(client,userdata,msg):
        try:
            if msg.topic==ACK:
                ack=json.loads(msg.payload)
                if (isinstance(ack.get('register'),str) and isinstance(ack.get('observed_at'),str)
                    and (ack['register'] in regs or ack['register']=='_health')):
                    acks.put_nowait((ack['register'],ack['observed_at']))
            else:
                controls.put_nowait((time.monotonic(),validated_control(msg,legacy.SETTABLE_PARAMETERS)))
        except (ValueError,TypeError,KeyError,AttributeError,Full) as exc:
            LOG.warning('Ignoring invalid or overflowing MQTT input: %s',exc)

    client.on_connect=connected
    client.on_message=message
    client.connect_async(args.broker,args.broker_port,60)
    client.loop_start()
    schedule=Schedule(regs,time.monotonic())
    ok=failed=latency=0
    seen=set()
    last_success=None
    health_due=0
    def drain_acks():
        while not acks.empty():
            yield acks.get_nowait()

    try:
        while True:
            now=time.monotonic()
            if not controls.empty():
                submitted,(name,value)=controls.get_nowait()
                if now-submitted<=15:
                    # Release the daemon client lock before the existing one-shot writer.
                    session.close()
                    result=legacy.execute_vclient_command(f'{name} {value}')
                    if result is not None and 'ERR' not in result.upper():
                        legacy.publish_command_value(client,name,legacy.SETTABLE_PARAMETERS[name]['description'],value)
                else:
                    LOG.warning('Expired queued control %s',name)
            if client.is_connected():
                spool.flush(client,now)
            if now>=health_due:
                health=dict(device=DEVICE,register='_health',observed_at=stamp(),decoder_version=VERSION,
                            quality='ok',reads_ok=ok,reads_failed=failed,last_latency_ms=latency,
                            max_fast_lateness_s=round(schedule.fast_lateness,2),
                            catalogue_size=len(regs),attempted_registers=len(seen),**spool.stats())
                if last_success is not None:
                    health['last_success_age_s']=round(now-last_success,2)
                try:
                    sync = subprocess.run(['timedatectl','show','-p','NTPSynchronized','--value'],
                                          capture_output=True,text=True,timeout=2).stdout.strip()
                    if sync in ('yes','no'):
                        health['clock_synchronized']=int(sync=='yes')
                except (OSError,subprocess.TimeoutExpired):
                    pass
                spool.put(health, drain_acks())
                health_due=now+30
                schedule.fast_lateness=0
            key=schedule.next(time.monotonic())
            if key is None:
                session.close()
                time.sleep(0.25)
                continue
            reg=regs[key]
            started=time.monotonic()
            sample,formatted=observation(reg,session)
            ended=time.monotonic()
            success=sample['quality'] not in ('partial','read_error','timeout')
            schedule.complete(key,started,ended,success)
            spool.put(sample, drain_acks())
            seen.add(key)
            latency=sample['latency_ms']
            if not success:
                failed+=1
                continue
            ok+=1
            last_success=ended
            if formatted is None:
                continue
            primary_unit=reg.aliases[sample['name']]
            for alias,description in reg.legacy.items():
                value=formatted
                if reg.aliases[alias]!=primary_unit:
                    enum=units[reg.aliases[alias]]
                    value=enum.get(sample['raw_hex'],enum.get('','UNKNOWN'))
                try:
                    if legacy.EXPECTED_OUTPUT_TYPE.get(alias,'numeric')=='numeric':
                        value=f'{float(value):.1f}'
                except ValueError:
                    pass
                legacy.publish_command_value(client,alias,description,value)
    finally:
        session.close()
        client.disconnect()
        client.loop_stop()
        spool.db.close()


if __name__=='__main__':
    main()
