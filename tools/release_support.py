"""Small shared helpers for build/archive verification."""
import ast
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def app_version():
    source = ROOT / 'upscale_toolkit' / '_version.py'
    if not source.is_file():
        source = ROOT / 'upscale_toolkit' / '__init__.py'
    parsed = ast.parse(source.read_text(encoding='utf-8'))
    for node in parsed.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__version__' for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError('Missing application __version__')


def write_tag_version(tag):
    version = tag.removeprefix('v')
    number = r'(?:0|[1-9][0-9]*)'
    prerelease = r'(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)'
    pattern = rf'{number}\.{number}\.{number}(?:-{prerelease}(?:\.{prerelease})*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?'
    if re.fullmatch(pattern, version) is None:
        raise ValueError('Release tag must be a semantic version, e.g. v1.2.3 or v1.2.3-rc.1')
    source = ROOT / 'upscale_toolkit' / '_version.py'
    source.write_text(f'# Generated from Git tag {tag}; do not edit.\n__version__ = {version!r}\n', encoding='utf-8')
    return version


def isolated_environment(user_dir):
    environment = os.environ.copy()
    environment['LOCALAPPDATA'] = str(user_dir)
    environment['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    for name in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', 'TCL_LIBRARY', 'TK_LIBRARY'):
        environment.pop(name, None)
    return environment


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate the application version from a Git tag')
    parser.add_argument('--tag', required=True)
    print(write_tag_version(parser.parse_args().tag))
