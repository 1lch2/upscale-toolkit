"""Model-inference E2E with user weights or CI fixtures; --exe tests the frozen app."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, PngImagePlugin

project = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project))


def fixture(path, size=(65, 49), mode='RGB', parameters='fixture seed 123'):
    image = Image.new('RGB', size, '#ddae73')
    draw = ImageDraw.Draw(image)
    margin = min(8, min(size) // 4)
    draw.rectangle((margin, margin, size[0] - margin - 1, size[1] - margin - 1), fill='#3299d0')
    draw.line((0, 0, size[0] - 1, size[1] - 1), fill='white', width=2)
    if mode == 'RGBA':
        image = image.convert('RGBA')
        alpha = Image.new('L', size, 170)
        ImageDraw.Draw(alpha).rectangle((0, 0, 12, 12), fill=0)
        image.putalpha(alpha)
    elif mode == 'L':
        image = image.convert('L')
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text('parameters', parameters)
    image.save(path, pnginfo=metadata)
    return image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path)
    parser.add_argument('--name', default='source')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cuda')
    parser.add_argument('--model-dir', type=Path)
    args = parser.parse_args()
    report_root = project / 'artifacts' / args.name
    report_root.mkdir(parents=True, exist_ok=True)
    artifacts = Path(tempfile.mkdtemp(prefix='run-', dir=report_root))
    os.environ['LOCALAPPDATA'] = str(artifacts / 'user')
    source = artifacts / '输入 图片' / '透明.png'
    fixture(source, mode='RGBA')
    output = artifacts / '输出 图片'
    command = [str(args.exe.resolve())] if args.exe else [sys.executable, str(project / 'app.py')]
    if args.model_dir:
        command += ['--model-dir', str(args.model_dir.resolve())]
    child_env = os.environ.copy()
    if args.exe:
        child_env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'TCL_LIBRARY', 'TK_LIBRARY'):
            child_env.pop(key, None)
    reports = []

    def run(name, *parameters, success=True):
        report = artifacts / (name + '.json')
        process = subprocess.run(command + list(parameters) + ['--report', str(report)],
                                 cwd=artifacts, env=child_env, timeout=240, capture_output=True)
        result = json.loads(report.read_text(encoding='utf-8'))
        if success and process.returncode != 0:
            raise AssertionError(f'{name}: {result}; stderr={process.stderr[-1000:]}')
        if not success and process.returncode == 0:
            raise AssertionError(f'{name}: expected failure')
        reports.append({'scenario': name, 'exit': process.returncode, 'report': result})
        print(name, 'OK', flush=True)
        return result

    run('runtime', '--diagnose')
    common = ['--input', str(source), '--output', str(output), '--device', args.device, '--tile', '48', '--overlap', '8']
    upscale = run('upscale', *common, '--scale', '2')
    with Image.open(upscale['records'][0]['output']) as im:
        assert im.mode == 'RGBA' and im.size == (130, 98) and 'fixture seed 123' in im.info['parameters']
    run('cpu-denoise', '--input', str(source), '--output', str(output), '--mode', 'denoise', '--device', 'cpu')
    precision = ['--half'] if args.device == 'cuda' else []
    run('blend-crop', *common, '--mode', 'blend', *precision, '--width', '101', '--height', '77', '--crop')
    run('blend-zero', *common, '--mode', 'blend', '--blend', '0')
    run('blend-one', *common, '--mode', 'blend', '--blend', '1', '--format', 'jpg')
    run('repeat-collision', *common, '--scale', '2')
    run('max-edge', *common, '--max-edge', '90')
    run('contain-size', *common, '--width', '101', '--height', '60')
    run('cpu-upscale', '--input', str(source), '--output', str(output), '--device', 'cpu', '--scale', '2', '--tile', '0')
    narrow = artifacts / '输入 图片' / '窄图.png'
    fixture(narrow, size=(9, 7))
    run('small-image-tiling', '--input', str(narrow), '--output', str(output), '--device', args.device)
    run('zero-overlap', *common, '--overlap', '0')
    run('multi-pass-upscale', *common, '--scale', '5')
    run('invalid-overlap', *common, '--overlap', '48', success=False)
    batch = artifacts / '批量 输入'
    fixture(batch / 'same.png', mode='L', parameters='unique A')
    fixture(batch / '子目录' / 'same.png', mode='RGBA', parameters='unique B')
    (batch / 'broken.png').write_bytes(b'broken image')
    batch_output = batch / 'output'
    fixture(batch_output / 'excluded.png')
    summary = run('batch-continue-exclude', '--input', str(batch), '--output', str(batch_output), '--recursive',
                  '--mode', 'denoise', '--format', 'webp', '--device', args.device, success=False)
    assert summary['success'] == 2 and summary['failed'] == 1 and len(summary['records']) == 3
    run('same-directory', '--input', str(batch), '--output', str(batch), success=False)
    run('output-ancestor', '--input', str(batch / '子目录'), '--output', str(batch), '--mode', 'denoise', '--device', args.device)
    (artifacts / 'summary.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    (report_root / 'summary.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    print('CLI/model/save E2E complete.', flush=True)


if __name__ == '__main__':
    main()
