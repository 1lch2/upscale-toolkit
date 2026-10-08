"""Desktop entry point; optional CLI supports reproducible packaged acceptance."""
import argparse
import json
import logging
import sys
from pathlib import Path

from upscale_toolkit.options import Options, app_root
from upscale_toolkit.storage import setup_logging


def main():
    parser = argparse.ArgumentParser(description='UltraSharp V2 / ScuNET 图像处理')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--mode', choices=['upscale', 'denoise', 'blend'], default='upscale')
    parser.add_argument('--device', choices=['auto', 'cpu', 'cuda'], default='auto')
    parser.add_argument('--scale', type=float, default=4)
    parser.add_argument('--blend', type=float, default=.25)
    parser.add_argument('--width', type=int)
    parser.add_argument('--height', type=int)
    parser.add_argument('--max-edge', type=int, default=0)
    parser.add_argument('--crop', action='store_true')
    parser.add_argument('--resize-denoise', action='store_true')
    parser.add_argument('--recursive', action='store_true')
    parser.add_argument('--half', action='store_true')
    parser.add_argument('--tile', type=int, default=256)
    parser.add_argument('--overlap', type=int, default=16)
    parser.add_argument('--format', choices=['png', 'jpg', 'webp'], default='png')
    parser.add_argument('--diagnose', action='store_true')
    parser.add_argument('--model-dir', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--gui-no-capture', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--gui-smoke', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    setup_logging()
    try:
        if args.gui_smoke:
            from upscale_toolkit.verification import gui_smoke
            gui_smoke(args.gui_smoke, model_dir=args.model_dir, capture_enabled=not args.gui_no_capture, device=args.device)
            return 0
        if args.diagnose:
            import torch
            import tkinter
            from upscale_toolkit.options import MODELS
            window = tkinter.Tk()
            window.update()
            window.destroy()
            result = {'root': str(app_root()), 'python': sys.version, 'torch': torch.__version__,
                      'executable': sys.executable, 'frozen': bool(getattr(sys, 'frozen', False)),
                      'torch_path': torch.__file__, 'python_prefix': sys.prefix,
                      'cuda': torch.cuda.is_available(),
                      'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                      'tk': 'window opened', 'models': {k: (app_root() / 'model' / v).is_file() for k, v in MODELS.items()}}
        elif args.input:
            if not args.output:
                raise ValueError('--input 需要 --output')
            if bool(args.width) != bool(args.height):
                raise ValueError('--width 和 --height 必须同时指定')
            from upscale_toolkit.engine import Engine
            from upscale_toolkit.jobs import run_jobs, scan_inputs
            opts = Options(mode=args.mode, device=args.device, scale=args.scale, blend=args.blend,
                           sizing='size' if args.width else 'scale', width=args.width or 1920,
                           height=args.height or 1080, fit='crop' if args.crop else 'contain',
                           resize_denoise=args.resize_denoise, max_edge=args.max_edge,
                           half=args.half, tile=args.tile, overlap=args.overlap, format=args.format)
            opts.validate()
            root, files = scan_inputs(args.input, args.output, args.recursive)
            if not files:
                raise ValueError('没有可处理的图片')
            engine = Engine(args.model_dir.resolve() if args.model_dir else None)
            result = run_jobs(engine, root, files, args.output, opts)
            engine.release()
        else:
            from upscale_toolkit.ui import make_window
            root, app = make_window()
            root.mainloop()
            return 0
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        elif sys.stdout:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('failed') else 0
    except Exception as error:
        logging.exception('Application failed')
        failure_report = args.report or args.gui_smoke
        if failure_report:
            failure_report.parent.mkdir(parents=True, exist_ok=True)
            if args.report or not failure_report.exists():
                failure_report.write_text(json.dumps({'error': f'{type(error).__name__}: {error}', 'passed': False}, ensure_ascii=False, indent=2), encoding='utf-8')
        elif args.input or args.diagnose or args.gui_smoke:
            if sys.stderr:
                print(str(error), file=sys.stderr)
        else:
            import tkinter.messagebox
            tkinter.messagebox.showerror('启动失败', str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
