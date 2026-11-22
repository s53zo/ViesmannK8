"""Exercise crash recovery across process boundaries using a disposable spool."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reader_v2 import PREFIX, Spool, observation
from vito_catalog import catalogue


class CounterFixture:
    def read(self, name, register):
        assert (name, register) == ('getEinschaltVerdichter', '0500-4')
        return bytes.fromhex('519F0000'), '40785.000000'


class Broker:
    def __init__(self, online=True):
        self.online = online
        self.messages = []

    def publish(self, topic, payload, qos, retain):
        assert topic == PREFIX + '0500-4' and qos == 1 and not retain
        if self.online:
            self.messages.append(payload)
        return SimpleNamespace(rc=0 if self.online else 4)


def collect_and_crash(path, transcript):
    spool = Spool(path, capacity=3)
    reg = catalogue({'getEinschaltVerdichter': 'Compressor starts'})['0500-4']
    original = []
    broker = Broker(online=False)
    for i in range(5):
        sample, _ = observation(reg, CounterFixture())
        sample['observed_at'] = f'2026-11-22T01:02:0{i}.123456Z'
        original.append(sample)
        spool.put(sample)
        spool.flush(broker, now=i)
    assert not broker.messages
    broker.online = True
    spool.flush(broker, now=10)
    assert [json.loads(body) for body in broker.messages] == original[-3:]
    transcript.write_text(json.dumps(broker.messages))
    # Broker accepted QoS 1; Influx storage ACK has not arrived.
    # Simulate abrupt termination without calling close or cleanup handlers.
    os._exit(73)


class OutageTests(unittest.TestCase):
    def test_crash_after_publish_before_database_ack(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        with self.subTest(scenario='reader restart'):
            tmp = temporary.name
            path, transcript = Path(tmp)/'spool.sqlite3', Path(tmp)/'wire.json'
            child = subprocess.run([sys.executable, __file__, '--crash', str(path), str(transcript)],
                                   capture_output=True, text=True, timeout=120)
            self.assertEqual(child.returncode, 73, child.stderr)
            broker = Broker()
            spool = Spool(path, capacity=3)
            self.addCleanup(spool.db.close)
            self.assertEqual(spool.stats()['dropped'], 2)
            self.assertEqual(spool.stats()['backlog'], 3)
            spool.flush(broker, now=0)
            original = json.loads(transcript.read_text())
            self.assertEqual(broker.messages, original)
            accepted = [json.loads(body) for body in original]
            # One point has been committed. A duplicate ACK for it cannot delete another point.
            for _ in range(2):
                spool.acknowledge(accepted[0]['register'], accepted[0]['observed_at'])
            self.assertEqual(spool.stats()['backlog'], 2)
            broker.messages.clear()
            spool.flush(broker, now=1)
            self.assertEqual(broker.messages, [])
            spool.flush(broker, now=31)
            self.assertEqual(broker.messages, original[1:])
            for point in accepted[1:]:
                spool.acknowledge(point['register'], point['observed_at'])
            self.assertEqual(spool.stats()['backlog'], 0)
            self.assertEqual(spool.stats()['dropped'], 2)
            self.assertEqual(spool.db.execute('PRAGMA integrity_check').fetchone(), ('ok',))


if __name__ == '__main__':
    if sys.argv[1:2] == ['--crash']:
        collect_and_crash(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        unittest.main()
