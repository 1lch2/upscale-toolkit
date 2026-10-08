"""Shared local/Actions build pipeline. Does not publish a GitHub Release."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from release_support import ROOT, app_version


def run(*arguments, environment=None):
    subprocess.run([sys.executable, '-B', *map(str, arguments)], cwd=ROOT,
                   env=environment, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', choices=['auto', 'cpu', 'cu130'], default='auto')
    parser.add_argument('--include-models', action='store_true')
    parser.add_argument('--release', action='store_true')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--test-model-dir', type=Path)
    parser.add_argument('--tag')
    args = parser.parse_args()
    if sys.platform != 'win32':
        raise RuntimeError('Windows builds must run on Windows')
    version = app_version()
    if args.tag and args.tag != f'v{version}':
        raise ValueError(f'Tag {args.tag} does not match application version v{version}')
    import torch
    runtime = 'cpu' if torch.version.cuda is None else 'cu130' if torch.version.cuda == '13.0' else None
    if runtime is None or (args.runtime != 'auto' and args.runtime != runtime):
        raise ValueError(f'Installed Torch runtime {torch.__version__} does not match --runtime {args.runtime}')
    environment = os.environ.copy()
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    environment['PYINSTALLER_CONFIG_DIR'] = str(ROOT / '.cache' / 'pyinstaller' / runtime)
    metadata = ROOT / 'build' / runtime / 'metadata'
    metadata.mkdir(parents=True, exist_ok=True)
    model_dir = ROOT / 'model'
    if not model_dir.is_dir() and (ROOT.parent / 'model').is_dir():
        model_dir = ROOT.parent / 'model'
    if args.include_models:
        for filename in ('4x-UltraSharpV2.pth', 'ScuNET.pth'):
            if not (model_dir / filename).is_file():
                raise FileNotFoundError(f'Missing model requested for bundling: {model_dir / filename}')
        if (model_dir / 'TEST_FIXTURES.json').exists():
            raise ValueError('CI fixtures must never be included in releases')
    test_models = (args.test_model_dir or model_dir).resolve()
    if args.verify:
        for filename in ('4x-UltraSharpV2.pth', 'ScuNET.pth'):
            if not (test_models / filename).is_file():
                raise FileNotFoundError(f'Verification needs real weights or CI fixtures: {test_models / filename}')
    run(ROOT / 'tools' / 'collect_licenses.py', '--output', metadata / 'licenses', environment=environment)
    manifest = {'version': version, 'runtime': runtime, 'includes_models': args.include_models,
                'python': sys.version.split()[0], 'verification_models': ('untrained-fixtures' if (test_models / 'TEST_FIXTURES.json').exists() else 'user-provided') if args.verify else None,
                'verification_device': 'cpu' if args.verify else None}
    (metadata / 'build-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    environment['UPSCALE_BUILD_METADATA'] = str(metadata)
    environment['UPSCALE_INCLUDE_MODELS'] = '1' if args.include_models else '0'
    environment['UPSCALE_MODEL_DIR'] = str(model_dir)
    if args.verify:
        run(ROOT / 'tools' / 'e2e.py', '--device', 'cpu', '--model-dir', test_models,
            '--name', f'source-{runtime}', environment=environment)
    destination = ROOT / 'dist' / runtime
    run('-m', 'PyInstaller', '--clean', '--noconfirm', '--distpath', destination, '--workpath', ROOT / 'build' / runtime / 'pyinstaller',
        ROOT / 'UpscaleToolkit.spec', environment=environment)
    exe = destination / 'UpscaleToolkit' / 'UpscaleToolkit.exe'
    if args.verify:
        run(ROOT / 'tools' / 'e2e.py', '--exe', exe, '--device', 'cpu', '--model-dir', test_models,
            '--name', f'packaged-{runtime}', environment=environment)
        run(ROOT / 'tools' / 'gui_acceptance.py', '--exe', exe, '--model-dir', test_models, '--no-capture', '--device', 'cpu',
            '--name', f'gui-{runtime}', environment=environment)
    if args.release:
        run(ROOT / 'tools' / 'package_release.py', '--app-dir', exe.parent, '--output-dir', destination, environment=environment)
        if args.verify:
            run(ROOT / 'tools' / 'verify_portable.py', '--release-report', destination / 'release.json',
                '--model-dir', test_models, environment=environment)
    print(f'Built {exe}', flush=True)


if __name__ == '__main__':
    main()
