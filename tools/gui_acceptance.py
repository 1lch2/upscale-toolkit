import argparse
import json
import os
import subprocess
import sys
import time
import tempfile
from pathlib import Path

project = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--exe', type=Path)
parser.add_argument('--name', default='gui-packaged')
parser.add_argument('--model-dir', type=Path)
parser.add_argument('--no-capture', action='store_true')
parser.add_argument('--device', choices=['auto', 'cpu', 'cuda'], default='auto')
args = parser.parse_args()
report_root = project / 'artifacts' / args.name
report_root.mkdir(parents=True, exist_ok=True)
folder = Path(tempfile.mkdtemp(prefix='run-', dir=report_root))
report = folder / 'report.json'
ready = report.with_suffix('.ready.json')
if ready.exists():
    ready.unlink()
environment = os.environ.copy()
environment['LOCALAPPDATA'] = str(folder / 'user')
if args.exe:
    environment['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    for name in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', 'TCL_LIBRARY', 'TK_LIBRARY'):
        environment.pop(name, None)
command = [str(args.exe.resolve())] if args.exe else [sys.executable, str(project / 'app.py')]
if args.model_dir:
    command += ['--model-dir', str(args.model_dir.resolve())]
if args.no_capture:
    command += ['--gui-no-capture']
command += ['--device', args.device]
started = time.perf_counter()
process = subprocess.Popen(command + ['--gui-smoke', str(report)], cwd=folder, env=environment)
window_seconds = None
while process.poll() is None:
    if window_seconds is None and ready.exists():
        window_seconds = round(time.perf_counter() - started, 3)
    if time.perf_counter() - started > 200:
        process.terminate()
        raise TimeoutError('GUI acceptance timed out')
    time.sleep(.05)
result = json.loads(report.read_text(encoding='utf-8'))
result['process_to_window_seconds'] = window_seconds
report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
(report_root / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
assert process.returncode == 0 and result.get('passed'), result
print(json.dumps({'passed': result['passed'], 'process_to_window_seconds': window_seconds,
                  'heartbeats': result['heartbeats'], 'seconds': result['seconds']}))
