"""Verify the actual archive without requiring previous local test artifacts."""
import argparse
import hashlib
import json
import subprocess
import time
import tempfile
import zipfile
from pathlib import Path

from release_support import ROOT, isolated_environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--release-report', type=Path, required=True)
    parser.add_argument('--model-dir', type=Path, required=True)
    args = parser.parse_args()
    release_report = args.release_report.resolve()
    release = json.loads(release_report.read_text(encoding='utf-8'))
    archive_path = release_report.parent / release['archive']
    with archive_path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != release['sha256']:
            raise ValueError('Archive checksum mismatch')
    report_root = ROOT / 'artifacts' / f'portable-{release["runtime"]}'
    report_root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='run-', dir=report_root)) / '解压 独立运行'
    folder.mkdir()
    started = time.perf_counter()
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(folder)
    app = folder / 'UpscaleToolkit'
    # This marker catches accidental pretrained/fixture inclusion in public artifacts.
    if not release['includes_models'] and list((app / 'model').glob('*.pth')):
        raise ValueError('Public archive unexpectedly contains weights')
    from PIL import Image, PngImagePlugin
    source = folder / '输入 图片.png'
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text('parameters', 'Portable acceptance fixture')
    Image.new('RGBA', (33, 25), (80, 150, 210, 180)).save(source, pnginfo=pnginfo)
    environment = isolated_environment(folder / 'user')
    report = folder / 'fusion.json'
    command = [str(app / 'UpscaleToolkit.exe'), '--input', str(source), '--output', str(folder / '输出'),
               '--mode', 'blend', '--device', 'cpu', '--width', '51', '--height', '37', '--crop',
               '--tile', '24', '--overlap', '4', '--model-dir', str(args.model_dir.resolve()), '--report', str(report)]
    subprocess.run(command, cwd=folder, env=environment, timeout=180, check=True)
    result = json.loads(report.read_text(encoding='utf-8'))
    if result['success'] != 1:
        raise AssertionError(result)
    diagnostics = folder / 'runtime.json'
    subprocess.run([str(app / 'UpscaleToolkit.exe'), '--diagnose', '--report', str(diagnostics)],
                   cwd=folder, env=environment, timeout=60, check=True)
    runtime = json.loads(diagnostics.read_text(encoding='utf-8'))
    if not runtime['frozen'] or Path(runtime['root']) != app or not Path(runtime['torch_path']).is_relative_to(app):
        raise AssertionError(runtime)
    result.update(extracted_app=str(app), verification_seconds=round(time.perf_counter() - started, 3),
                  runtime=release['runtime'], verification_device='cpu', pretrained_quality_test=False)
    (folder / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (report_root / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Portable archive verified: {archive_path.name}')


if __name__ == '__main__':
    main()
