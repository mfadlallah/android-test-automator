"""Bounded UIAutomator2 snapshot worker, independent of app/domain logic."""
import argparse
import importlib.util
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path


def resolve_backend(requested):
    installed=importlib.util.find_spec('uiautomator2') is not None
    if requested=='auto':
        return 'uiautomator2' if installed else 'adb'
    if requested=='uiautomator2' and not installed:
        raise RuntimeError('Install hierarchy backend: python3 -m pip install -r requirements-hierarchy.txt')
    return requested


def snapshot(serial, output):
    import uiautomator2 as u2
    device=u2.connect(serial)
    device.jsonrpc.setConfigurator({'waitForIdleTimeout':0,
                                   'waitForSelectorTimeout':0})
    xml=device.dump_hierarchy(compressed=False,pretty=False,max_depth=100)
    root=ET.fromstring(xml)
    if root.tag!='hierarchy' or not root.findall('.//node'):
        raise RuntimeError('UIAutomator2 returned an empty or invalid hierarchy')
    Path(output).write_text(xml,encoding='utf-8')


def capture(serial, output, diagnostic_path, timeout=25):
    output=Path(output)
    output.unlink(missing_ok=True)
    command=[sys.executable,'-m','src.hierarchy_backend','--serial',serial,
             '--output',str(output.resolve())]
    started=time.monotonic()
    record={'backend':'uiautomator2','command':command,'timeout_seconds':timeout,
            'started_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    def decode(value):
        return value.decode(errors='replace') if isinstance(value,bytes) else (value or '')
    try:
        result=subprocess.run(command,capture_output=True,timeout=timeout)
        record.update(exit_code=result.returncode,stdout=decode(result.stdout),
                      stderr=decode(result.stderr),timed_out=False)
        if result.returncode:
            raise RuntimeError('UIAutomator2 snapshot failed: '+record['stderr'][-800:])
        xml=output.read_text(encoding='utf-8')
        root=ET.fromstring(xml)
        if root.tag!='hierarchy' or not root.findall('.//node'):
            raise RuntimeError('UIAutomator2 snapshot has no nodes')
        return xml
    except subprocess.TimeoutExpired as exc:
        record.update(exit_code=None,stdout=decode(exc.stdout),
                      stderr=decode(exc.stderr),timed_out=True)
        raise RuntimeError('UIAutomator2 snapshot exceeded '+str(timeout)+' seconds') from exc
    finally:
        record['duration_seconds']=round(time.monotonic()-started,3)
        with Path(diagnostic_path).open('a',encoding='utf-8') as log:
            log.write(json.dumps(record,ensure_ascii=False)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--serial',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:
        snapshot(args.serial,args.output)
    except Exception as exc:
        print(type(exc).__name__+': '+str(exc),file=sys.stderr)
        raise SystemExit(1)
