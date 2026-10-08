"""Real Tk event-loop acceptance, available only through --gui-smoke."""
import json
import ctypes
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageGrab, PngImagePlugin

from .ui import make_window


def gui_smoke(report_path, model_dir=None, capture_enabled=True, device='auto'):
    report_path = Path(report_path).resolve()
    folder = report_path.parent
    folder.mkdir(parents=True, exist_ok=True)
    image = Image.new('RGB', (193, 145), '#64a8dd')
    ImageDraw.Draw(image).ellipse((20, 20, 120, 120), fill='#f6ce62')
    source = folder / '界面 输入.png'
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text('parameters', 'GUI fixture seed 456')
    image.save(source, pnginfo=metadata)
    output = folder / '界面 输出'
    root, app = make_window(model_dir=model_dir)
    app.device.set({'auto': '自动', 'cpu': 'CPU', 'cuda': 'CUDA'}[device])
    root.update()
    report_path.with_suffix('.ready.json').write_text(json.dumps({'window': 'ready', 'geometry': root.geometry()}), encoding='utf-8')
    errors = []
    result = {'heartbeats': 0, 'scenarios': []}
    start_time = time.perf_counter()
    stage = 'initial'
    block_completed = threading.Event()
    original_emit = app.emit

    def emit(kind, data):
        original_emit(kind, data)
        if kind == 'progress' and data['done'] >= 1:
            block_completed.set()

    app.emit = emit

    def fail(error):
        errors.append(f'{type(error).__name__}: {error}')
        app.cancel.set()
        root.destroy()

    def exception_hook(kind, value, traceback):
        fail(value)

    root.report_callback_exception = exception_hook

    def capture(name):
        root.update()
        root.update_idletasks()
        app.render_preview()
        root.update_idletasks()
        assert app.start_button.winfo_rooty() + app.start_button.winfo_height() <= root.winfo_rooty() + root.winfo_height(), f'start button outside {name}: {root.geometry()}, start={app.start_button.winfo_rooty()}, h={app.start_button.winfo_height()}, rooty={root.winfo_rooty()}'
        assert app.cancel_button.winfo_rootx() + app.cancel_button.winfo_width() <= root.winfo_rootx() + root.winfo_width(), 'cancel button outside window'
        if capture_enabled:
            handle = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2)
            ImageGrab.grab(window=handle).save(folder / (name + '.png'))

    def tick():
        nonlocal stage
        result['heartbeats'] += 1
        try:
            if time.perf_counter() - start_time > 180:
                raise TimeoutError(f'GUI acceptance timed out in {stage}')
            if stage == 'initial':
                app.single_path.set(str(source))
                app.output_path.set(str(output))
                app.refresh_input()
                assert app.engine is None, 'image selection must not load model'
                capture('window-default')
                root.geometry(f'{root.minsize()[0]}x{root.minsize()[1]}')
                root.update_idletasks()
                capture('window-small')
                app.scale.set('2')
                app.tile.set('48')
                app.overlap.set('8')
                app.start_button.invoke()
                assert app.running
                stage = 'cancelling'
            elif stage == 'cancelling':
                if app.running and block_completed.is_set() and not app.cancel.is_set():
                    app.cancel_button.invoke()
                if not app.running:
                    assert app.summary and app.summary['cancelled'], app.summary
                    assert app.summary['success'] == 0
                    assert not list(output.glob('*.png')), 'cancelled image was saved'
                    result['scenarios'].append({'name': 'tile-cancel', 'summary': app.summary})
                    app.mode.set('放大与去噪融合')
                    app.sizing.set('按宽高')
                    app.lock_ratio.set(False)
                    app.width.set('97')
                    app.height.set('71')
                    app.fit.set('填满并居中裁剪')
                    app.tile.set('96')
                    app.start_button.invoke()
                    stage = 'blend'
            elif stage == 'blend' and not app.running:
                assert app.summary and app.summary['success'] == 1, app.summary
                record = app.summary['records'][0]
                with Image.open(record['output']) as saved:
                    assert saved.size == (97, 71)
                assert app.preview_choice.get() == '结果'
                capture('window-result')
                result['scenarios'].append({'name': 'restart-blend-crop', 'summary': app.summary})
                batch = folder / '界面 批量'
                batch.mkdir(exist_ok=True)
                image.resize((33, 25)).save(batch / '正常.png')
                (batch / '损坏.png').write_bytes(b'broken')
                app.notebook.select(1)
                app.batch_path.set(str(batch))
                app.output_path.set(str(batch / 'output'))
                app.mode.set('去噪')
                app.start_button.invoke()
                stage = 'batch'
            elif stage == 'batch' and not app.running:
                assert app.summary and app.summary['success'] == 1 and app.summary['failed'] == 1, app.summary
                for row in app.tree.get_children():
                    if app.tree.set(row, 'status') == '已完成':
                        app.tree.selection_set(row)
                root.update_idletasks()
                capture('window-batch')
                result['scenarios'].append({'name': 'directory-failure-continue', 'summary': app.summary})
                result['seconds'] = round(time.perf_counter() - start_time, 3)
                root.destroy()
                return
            root.after(40, tick)
        except Exception as error:
            fail(error)

    root.after(250, tick)
    root.mainloop()
    result['errors'] = errors
    result['passed'] = not errors and stage == 'batch' and len(result['scenarios']) == 3
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if not result['passed']:
        raise RuntimeError(f'GUI verification failed: {errors}')
