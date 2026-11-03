import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def launch(env,port):
    return subprocess.run([sys.executable,'-B',str(ROOT/'scripts/launch.py'),'--managed','--no-browser','--port',str(port)],
                          cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=10)

def test_managed_missing_data_never_falls_back_to_default():
    env=dict(os.environ,STATS_MODE='local');env.pop('STATS_DATA_DIR',None)
    result=launch(env,8501)
    events=[json.loads(line) for line in result.stdout.splitlines()]
    assert result.returncode==1
    assert [e['type'] for e in events]==['error','exit']
    assert 'explicit local Stats library' in events[0]['message']
    assert events[-1]['clean'] is False

def test_managed_occupied_port_does_not_open_existing_service(tmp_path):
    with sqlite3.connect(tmp_path/'stats.sqlite3') as db:db.execute('CREATE TABLE sample(value)')
    env=dict(os.environ,STATS_MODE='local',STATS_DATA_DIR=str(tmp_path))
    with socket.socket() as held:
        held.bind(('127.0.0.1',0));held.listen()
        result=launch(env,held.getsockname()[1])
    events=[json.loads(line) for line in result.stdout.splitlines()]
    assert result.returncode==1
    assert [e['type'] for e in events]==['error','exit']
    assert 'already in use' in events[0]['message']
