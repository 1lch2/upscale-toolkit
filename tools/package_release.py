"""Package the directory created by the shared build entry."""
import argparse
import hashlib
import json
import time
import zipfile
from pathlib import Path

from release_support import ROOT, app_version


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    app = args.app_dir.resolve()
    output = (args.output_dir or app.parent).resolve()
    manifest = json.loads((app / 'build-manifest.json').read_text(encoding='utf-8'))
    if manifest['version'] != app_version():
        raise ValueError('Built application version differs from current source; rebuild before packaging')
    weights = {p.name for p in (app / 'model').glob('*.pth')}
    expected = {'4x-UltraSharpV2.pth', 'ScuNET.pth'} if manifest['includes_models'] else set()
    if weights != expected:
        raise ValueError(f'Unexpected release weights: {weights}; expected {expected}')
    if (app / 'model' / 'TEST_FIXTURES.json').exists():
        raise ValueError('Test fixtures cannot be released')
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f'UpscaleToolkit-{manifest["version"]}-windows-x64-{manifest["runtime"]}.zip'
    started = time.perf_counter()
    files = sorted(p for p in app.rglob('*') if p.is_file())
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as zipped:
        for path in files:
            zipped.write(path, Path('UpscaleToolkit') / path.relative_to(app))
    with archive.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    report = manifest | {'archive': archive.name, 'archive_bytes': archive.stat().st_size,
                         'folder_bytes': sum(p.stat().st_size for p in files), 'files': len(files),
                         'sha256': sha, 'packaging_seconds': round(time.perf_counter() - started, 2)}
    (output / 'release.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output / (archive.name + '.sha256')).write_text(f'{sha}  {archive.name}\n', encoding='ascii')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
