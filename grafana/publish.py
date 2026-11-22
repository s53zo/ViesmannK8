#!/usr/bin/env python3
"""Publish the checked-in dashboard with optimistic concurrency.

Supply GRAFANA_TOKEN (dashboard write scope) and optionally GRAFANA_URL.
Alternatively set GRAFANA_USER and GRAFANA_PASSWORD for form login.
"""
import http.cookiejar
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

base=os.environ.get('GRAFANA_URL','http://10.0.1.8:3000').rstrip('/')
headers={'Content-Type':'application/json','Origin':base}
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def api(path,body=None):
    request=urllib.request.Request(base+path,headers=headers,data=None if body is None else json.dumps(body).encode())
    with opener.open(request,timeout=30) as resp:
        return json.load(resp)


def main():
    if os.environ.get('GRAFANA_TOKEN'):
        headers['Authorization']='Bearer '+os.environ['GRAFANA_TOKEN']
    else:
        api('/login',dict(user=os.environ['GRAFANA_USER'],password=os.environ['GRAFANA_PASSWORD']))
    path=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).with_name('heat-pump.json')
    dashboard=json.loads(path.read_text())
    assert dashboard['uid']=='vito-2048-telemetry-v2'
    folder=''
    try:
        existing=api('/api/dashboards/uid/'+dashboard['uid'])
    except urllib.error.HTTPError as exc:
        if exc.code!=404:raise
    else:
        if existing['dashboard']['title']!=dashboard['title']:
            raise SystemExit('Dashboard UID is already assigned to another dashboard')
        dashboard['id']=existing['dashboard']['id']
        dashboard['version']=existing['dashboard']['version']
        folder=existing['meta']['folderUid']
    result=api('/api/dashboards/db',dict(dashboard=dashboard,folderUid=folder,overwrite=False,
            message='Publish the versioned Vitocal 2048 telemetry dashboard'))
    print(result['status'],base+result['url'],'version',result['version'])


if __name__=='__main__':
    main()
