"""Collect the active build environment, without mutating tracked license files."""
import argparse
import hashlib
import importlib.metadata as md
import json
import shutil
import sys
import tarfile
import urllib.request
import tkinter
from pathlib import Path

from packaging.requirements import Requirement
from release_support import ROOT


SPANDREL_COMMIT = '724cca389f28c38e1050689d4862a452fd644484'  # v0.4.2
SPANDREL_SHA256 = '1c3f9c86bc80f3e4e9546416f4f0be702b07e5d6b120a3641e342e7b4a05eb5b'


def download(url, expected_hash=None):
    cache = ROOT / '.cache' / 'license-downloads'
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (hashlib.sha256(url.encode()).hexdigest() + '.bin')
    if not path.is_file():
        with urllib.request.urlopen(url, timeout=60) as response:
            content = response.read()
        if expected_hash and hashlib.sha256(content).hexdigest() != expected_hash:
            raise ValueError(f'License source checksum mismatch: {url}')
        path.write_bytes(content)
    if expected_hash and hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError(f'Cached license source checksum mismatch: {path}')
    return path


def collect_spandrel(output):
    # The wheel omits upstream license files, including the bundled architectures.
    if md.version('spandrel') != '0.4.2':
        raise ValueError('Update the pinned Spandrel license source when upgrading Spandrel')
    url = f'https://codeload.github.com/chaiNNer-org/spandrel/tar.gz/{SPANDREL_COMMIT}'
    archive = download(url, SPANDREL_SHA256)
    paths = []
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            relative = Path(*Path(member.name).parts[1:])
            if not member.isfile() or relative.is_absolute() or '..' in relative.parts:
                continue
            if relative != Path('LICENSE') and not relative.is_relative_to('libs/spandrel'):
                continue
            if not relative.name.lower().startswith(('license', 'licence', 'copying', 'notice')):
                continue
            destination = output / 'dependencies' / 'spandrel' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source.extractfile(member) as stream:
                destination.write_bytes(stream.read())
            paths.append(relative.as_posix())
    if not paths:
        raise RuntimeError('No Spandrel licenses found in pinned source archive')
    return {'url': url, 'sha256': SPANDREL_SHA256, 'files': paths}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'build' / 'metadata' / 'licenses')
    args = parser.parse_args()
    output = args.output.resolve()
    if output == (ROOT / 'licenses').resolve() or output.is_relative_to(ROOT / 'licenses'):
        raise ValueError('Generated licenses must not overwrite the source license tree')
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'LICENSE', output / 'Forge-AGPL-3.0.txt')
    shutil.copy2(ROOT / 'licenses' / 'README.md', output / 'README.md')
    versions = {}
    pending = ['spandrel', 'pillow', 'piexif', 'pyinstaller']
    while pending:
        distribution = md.distribution(pending.pop())
        name = distribution.metadata['Name'].lower().replace('_', '-')
        if name in versions:
            continue
        versions[name] = distribution.version
        for requirement in distribution.requires or []:
            parsed = Requirement(requirement)
            if parsed.marker is None or parsed.marker.evaluate({'extra': ''}):
                pending.append(parsed.name)
        for relative in distribution.files or []:
            if any(word in str(relative).lower() for word in ('license', 'licence', 'copying', 'notice')):
                source = Path(distribution.locate_file(relative))
                if source.is_file():
                    safe = Path(*[part for part in relative.parts if part not in ('.', '..')])
                    destination = output / 'dependencies' / name / safe
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    sources = {'spandrel': collect_spandrel(output)}
    tcl_version = str(tkinter.Tcl().call('info', 'patchlevel'))
    tcl_minor = '.'.join(tcl_version.split('.')[:2])
    for relative in ['LICENSE.txt', f'tcl/tcl{tcl_minor}/license.terms', f'tcl/tk{tkinter.TkVersion}/license.terms']:
        source = Path(sys.base_prefix) / relative
        destination = output / ('Python-LICENSE.txt' if relative == 'LICENSE.txt' else source.parent.name + '-license.terms')
        if not source.is_file() and relative.startswith('tcl/tcl'):
            url = f'https://raw.githubusercontent.com/tcltk/tcl/core-{tcl_version.replace(".", "-")}/license.terms'
            source = download(url)
            sources['tcl'] = {'version': tcl_version, 'url': url}
        if not source.is_file():
            raise FileNotFoundError(f'Python installation is missing a required license: {source}')
        shutil.copy2(source, destination)
    (output / 'sources.json').write_text(json.dumps(sources, indent=2), encoding='utf-8')
    (output.parent / 'runtime-versions.json').write_text(json.dumps(versions, indent=2), encoding='utf-8')
    print(f'Collected {len(versions)} distributions into {output}')


if __name__ == '__main__':
    main()
