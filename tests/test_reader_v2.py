import json
import socket
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from reader_v2 import Session, Spool, Schedule, observation, validated_control
from vito_catalog import FAST, catalogue, decode


class Daemon(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b'vctrld>')
        while command := self.rfile.readline().strip():
            if command == b'debug on':
                self.wfile.write(b'vctrld>')
                continue
            body = self.server.reply
            for piece in (body[:7],body[7:],b'vctrld>'):
                self.wfile.write(piece)


FRAME = b'\n'.join(b'DEBUG: >SENT: '+v for v in b'01 F7 05 00 04'.split())
SAMPLES = Path(__file__).with_name('fixtures')/'2048-read-samples.txt'


class ReaderTests(unittest.TestCase):
    def test_captured_samples(self):
        chunks=SAMPLES.read_text().splitlines()
        raw={x.rstrip(':'):bytes.fromhex(chunks[i+1]) for i,x in enumerate(chunks) if x.startswith('get')}
        self.assertEqual(decode('0500-4',raw['getEinschaltVerdichter'])['counter_value'],40785)
        self.assertEqual(decode('0580-4',raw['getBetriebsstdVerdichter'])['counter_value'],103171086)
        self.assertEqual(decode('00F8-8',raw['getDevType'])['text_value'],'2048')
        self.assertEqual(decode('0414-1',raw['getStatusUmschaltventilHWW'])['text_value'],'Heizen')
        for name in raw:
            if name.startswith('getEnergie'):
                self.assertEqual(decode('16D0-2',raw[name]),{'confidence':'unknown','quality':'sentinel'})
        self.assertEqual(decode('0116-2',b'\xff\xff')['quality'],'unmapped')

    def test_read_frame_and_partial(self):
        regs=catalogue({'getEinschaltVerdichter':'Starts'})
        reg=regs['0500-4']
        with socketserver.TCPServer(('127.0.0.1',0),Daemon) as srv:
            thread=threading.Thread(target=srv.serve_forever,daemon=True)
            thread.start()
            session=Session(*srv.server_address)
            try:
                srv.reply=FRAME+b'\nDEBUG: <RECV: received 51 9F 00 00\n40785.000000\n'
                sample,value=observation(reg,session)
                self.assertEqual(sample['counter_value'],40785)
                self.assertEqual(value,'40785.000000')
                srv.reply=FRAME+b'\nDEBUG: <RECV: received 51 9F\nERR: short\n'
                sample,value=observation(reg,session)
                self.assertNotIn('counter_value',sample)
                self.assertEqual(sample['raw_hex'],'519F')
                srv.reply=FRAME+b'\nDEBUG: <RECV: received 51 9F 00 00\nERR: decode unavailable\n'
                sample,value=observation(reg,session)
                self.assertEqual((sample['counter_value'],value),(40785,None))
                srv.reply=FRAME+b'\nDEBUG: <RECV: received 51 9F\n0\n'
                sample,value=observation(reg,session)
                self.assertEqual((sample['quality'],sample['raw_hex'],value),('partial','519F',None))
            finally:
                session.close()
                srv.shutdown()
                thread.join()

    def test_timeout(self):
        class Timeout:
            def read(self,*args):
                raise socket.timeout()
            def close(self):
                self.closed=True
        session=Timeout()
        sample,value=observation(catalogue({})['0414-1'],session)
        self.assertTrue(session.closed)
        self.assertEqual(sample['quality'],'timeout')
        self.assertNotIn('raw_hex',sample)

    def test_schedule(self):
        regs=catalogue({})
        sch=Schedule(regs,100)
        self.assertEqual(set(sch.intervals),set(regs))
        for k in FAST:
            self.assertEqual(sch.next(100),k)
            sch.complete(k,100,101,True)
        self.assertNotIn(sch.next(101), FAST)
        self.assertIn(sch.next(131),FAST)
        sch.complete('0500-4',132,133,False)
        self.assertGreater(sch.due['0500-4'],162)

    def test_durable_delivery(self):
        class Client:
            def publish(self,topic,body,qos,retain):
                self.last=json.loads(body)
                return SimpleNamespace(rc=0)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'test.db'
            c=Client()
            s=Spool(path,2)
            def msg(i):
                return dict(register='0500-4',observed_at=f'2026-01-01T00:00:0{i}.123456Z',counter_value=i)
            for i in range(3):
                s.put(msg(i))
            s.flush(c,100)
            self.assertEqual(s.stats()['backlog'],2)
            s.db.close()
            s=Spool(path,2)
            s.flush(c,0)
            self.assertEqual(c.last,msg(2))
            s.acknowledge(msg(2)['register'],msg(2)['observed_at'])
            self.assertEqual(s.stats()['backlog'],1)
            self.assertEqual(s.stats()['dropped'],1)
            s.db.close()

    def test_control_validation(self):
        params={'setRaum2':dict(type='numeric',min=0,max=30)}
        def request(value,retained=False,dup=False):
            return SimpleNamespace(topic='vito/set/setRaum2',retain=retained,dup=dup,
                                   payload=json.dumps({'value':value}).encode())
        self.assertEqual(validated_control(request(21),params),('setRaum2',21.0))
        for message in [request(21,True),request(21,False,True),request(float('nan')),request(32)]:
            with self.assertRaises(ValueError):
                validated_control(message,params)
