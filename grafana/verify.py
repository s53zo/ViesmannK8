#!/usr/bin/env python3
"""Exercise the exported dashboard through the same datasource queries as Grafana.

Pass --fixtures to check gap, reset and unknown-value behaviour using a new
temporary Influx database. No production measurement is written or deleted.
"""
import argparse
import json
import math
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
VITO = 'deasq3bzjrx8ge'
HOUSE = 'fe9liwluvfev4d'


def request(url, data=None, content_type='application/json'):
    req = Request(url, data=data, headers={'Content-Type': content_type})
    try:
        with urlopen(req, timeout=45) as response:
            body = response.read()
    except HTTPError as exc:
        raise RuntimeError(f'{url}: {exc.code} {exc.read().decode()[:2000]}') from exc
    return json.loads(body) if body else None


def query_panel(grafana, panel, start, end, db=None, selected_device=None):
    queries = []
    for target in panel['targets']:
        t = target.copy()
        q = t.get('query')
        if q:
            # In Grafana these substitutions are made by the dashboard front end.
            for name in ('register', 'quality', 'confidence'):
                q = q.replace('${'+name+':regex}', '.*')
            q = q.replace('${__from}', str(start)).replace('${__to}', str(end))
            q = q.replace('$__interval','30s')
            if db and t['datasource']['uid'] == VITO:
                for measurement in ('vito_observation_v2', 'vito_reader_health_v2'):
                    q=q.replace(f'FROM "{measurement}"',f'FROM "{db}"."autogen"."{measurement}"')
            if selected_device:
                q=q.replace("'vitocal-2048'", "'"+selected_device+"'")
            t.update(query=q, intervalMs=30000, maxDataPoints=2000)
        queries.append(t)
    data=request(grafana+'/api/ds/query', json.dumps(dict(queries=queries, **{'from':str(start),'to':str(end)})).encode())
    for ref, result in data['results'].items():
        if result.get('error') or result.get('status',200) != 200:
            raise AssertionError(f'{panel["title"]}/{ref}: {result}')
    return data['results']


def field_values(results, ref):
    values=[]
    for frame in results.get(ref,{}).get('frames',[]):
        cols=frame.get('data',{}).get('values',[])
        if cols:
            values.extend(cols[-1])
    return values


def influx_query(influx, statement):
    result=request(influx+'/query',urlencode(dict(q=statement)).encode(),'application/x-www-form-urlencoded')
    if result['results'][0].get('error'):
        raise ValueError(result)


def fixtures(influx, grafana, panels):
    db='vito_dashboard_fixture_'+uuid.uuid4().hex
    assert db.startswith('vito_dashboard_fixture_')
    end=(int(time.time())//30)*30
    start=end-240
    influx_query(influx,'CREATE DATABASE "'+db+'"')
    try:
        lines=[]
        for device in ('valid','no-start','reset','gap','edges'):
            for i in range(9):
                if device=='gap' and i in (2,3,4,5):continue
                if device=='edges' and i<4:continue
                ts=start+i*30
                starts=100 + (0 if device=='no-start' else i//4)
                if device=='reset' and i>=4:starts=i//4
                for k,val in [('0500-4',starts),('0580-4',10000+i*15)]:
                    lines.append(f'vito_observation_v2,device={device},register={k} counter_value={val}i,quality="ok",confidence="verified" {ts}')
        for i,(key,offset,value) in enumerate([('0103-2',1,12),('0104-2',4,10),('0103-2',31,13),('0104-2',51,8)]):
            lines.append(f'vito_observation_v2,device=valid,register={key} numeric_value={value}.0,quality="provisional",confidence="provisional" {start+offset}')
        lines.append(f'vito_observation_v2,device=valid,register=16D0-2 raw_hex="FFFF",quality="sentinel",confidence="unknown" {start+1}')
        lines.append(f'vito_observation_v2,device=valid,register=0414-1 text_value="Heizen",quality="ok",confidence="verified" {start+1}')
        request(influx+'/write?'+urlencode(dict(db=db,precision='s')),'\n'.join(lines).encode(),'text/plain')
        for scenario in ('valid','no-start','reset','gap','edges','empty'):
            rows=query_panel(grafana, panels['Minutes per start · selected window'],start*1000,end*1000,db,scenario)
            vals=field_values(rows,'Result')
            finite=[v for v in vals if isinstance(v,(float,int)) and math.isfinite(v)]
            assert finite == ([1] if scenario=='valid' else []), (scenario,vals)
        rows=query_panel(grafana,panels['Source ΔT · entering minus leaving'],start*1000,end*1000,db,'valid')
        assert [v for v in field_values(rows,'Difference') if v is not None]==[2], rows
        rows=query_panel(grafana,panels['Energy channels awaiting validation'],start*1000,end*1000,db,'valid')
        assert 'FFFF' in json.dumps(rows)
        rows=query_panel(grafana,panels['Operating state'],start*1000,end*1000,db,'valid')
        assert 'Heizen' in json.dumps(rows)
        print('Fixture cases passed: normal, zero starts, reset, stale edges, missing samples, empty, matched thermal pair, unknown bytes, valve text.')
    finally:
        # This name is freshly generated solely for this run.
        influx_query(influx,'DROP DATABASE "'+db+'"')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--grafana',default='http://10.0.1.8:3000')
    ap.add_argument('--influx',default='http://10.0.1.8:8086')
    ap.add_argument('--fixtures',action='store_true')
    ap.add_argument('--published',action='store_true')
    args=ap.parse_args()
    d=json.loads((HERE/'heat-pump.json').read_text())
    if args.published:
        live=request(args.grafana+'/api/dashboards/uid/'+d['uid'])['dashboard']
        assert live['panels']==d['panels'], 'Published panels differ'
        for uid in ('YItU9nUGz2','YItU9nUGz'):
            assert request(args.grafana+'/api/dashboards/uid/'+uid)['dashboard']['uid']==uid
    ps={p['title']:p for p in d['panels'] if p['type']!='row'}
    end=int(time.time()*1000)
    for title,panel in ps.items():
        results=query_panel(args.grafana,panel,end-10800000,end)
        populated=sum(any(frame.get('data',{}).get('values') and len(frame['data']['values'][0]) for frame in r.get('frames',[])) for r in results.values())
        print(f'{title}: {populated}/{len(results)} query results with data')
    if args.fixtures:
        fixtures(args.influx,args.grafana,ps)


if __name__=='__main__':
    main()
