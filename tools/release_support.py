"""Small shared helpers for build/archive verification."""
import ast
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def app_version():
    parsed = ast.parse((ROOT / 'upscale_toolkit' / '__init__.py').read_text(encoding='utf-8'))
    for node in parsed.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__version__' for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError('Missing application __version__')


def isolated_environment(user_dir):
    environment = os.environ.copy()
    environment['LOCALAPPDATA'] = str(user_dir)
    environment['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    for name in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', 'TCL_LIBRARY', 'TK_LIBRARY'):
        environment.pop(name, None)
    return environment
