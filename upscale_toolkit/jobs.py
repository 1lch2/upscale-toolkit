import logging
import threading
import time
from pathlib import Path

from .image_io import read_image, apply_alpha, save_result

logger = logging.getLogger(__name__)
SUPPORTED = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}


def scan_inputs(source, output, recursive=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.exists():
        raise FileNotFoundError(f'输入不存在：{source}')
    if source.is_file():
        if source.suffix.lower() not in SUPPORTED:
            raise ValueError('支持 PNG、JPEG、WebP、BMP 图片')
        return source.parent, [source]
    if source == output:
        raise ValueError('输入目录与输出目录不能相同')
    exclude_output = output.is_relative_to(source)
    import os
    files = []
    for parent, directories, filenames in os.walk(source, followlinks=False):
        directories[:] = sorted(d for d in directories
                                if not (Path(parent) / d).is_symlink()
                                and (not exclude_output or not (Path(parent) / d).resolve().is_relative_to(output))) if recursive else []
        for name in sorted(filenames):
            path = Path(parent) / name
            if path.suffix.lower() in SUPPORTED and (not exclude_output or not path.resolve().is_relative_to(output)):
                files.append(path)
    return source, files


def run_jobs(engine, root, files, output, opts, emit=lambda *a: None, cancel=None):
    from .engine import Cancelled, check_cancel
    cancel = cancel or threading.Event()
    opts.validate()
    output = Path(output).resolve()
    started = time.perf_counter()
    records = []
    emit('manifest', [str(p) for p in files])
    for index, source in enumerate(files):
        if cancel.is_set():
            break
        emit('file', {'index': index, 'total': len(files), 'path': str(source)})
        try:
            image, alpha, parameters, metadata = read_image(source)
            check_cancel(cancel)
            result = engine.process(image, opts, lambda text, done, total: emit('progress', {'text': text, 'done': done, 'total': total}), cancel)
            result = apply_alpha(result, alpha, opts, image.size)
            check_cancel(cancel)
            relative = source.relative_to(root)
            label = {'upscale': 'upscaled', 'denoise': 'denoised', 'blend': 'blend'}[opts.mode]
            destination = output / relative.parent / f'{source.stem}_{label}.{opts.format}'
            saved = save_result(result, destination, parameters, metadata, opts, cancel)
            record = {'input': str(source), 'status': 'success', 'output': str(saved), 'size': list(result.size)}
            logger.info('Saved %s', saved)
        except Cancelled:
            record = {'input': str(source), 'status': 'cancelled'}
            records.append(record)
            emit('result', record)
            break
        except Exception as error:
            logger.exception('Task failed: %s', source)
            record = {'input': str(source), 'status': 'failed', 'error': f'{type(error).__name__}: {error}'}
            engine.release()
        records.append(record)
        emit('result', record)
    processed = len(records)
    records.extend({'input': str(p), 'status': 'pending'} for p in files[processed:])
    summary = {'records': records, 'success': sum(r['status'] == 'success' for r in records),
               'failed': sum(r['status'] == 'failed' for r in records), 'cancelled': cancel.is_set(),
               'pending': sum(r['status'] == 'pending' for r in records),
               'seconds': round(time.perf_counter() - started, 3)}
    emit('finished', summary)
    return summary
