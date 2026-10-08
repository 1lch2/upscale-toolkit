"""Forge SD metadata handling adapted to standalone Pillow I/O. AGPL-3.0."""
import os
import tempfile
from pathlib import Path

import piexif
import piexif.helper
from PIL import Image, ImageOps, PngImagePlugin


def read_image(path):
    with Image.open(path) as source:
        if getattr(source, 'n_frames', 1) != 1:
            raise ValueError('暂不支持动画或多帧图像，请先导出单帧')
        if source.mode not in ('RGB', 'RGBA', 'L', 'LA', 'P', '1'):
            raise ValueError(f'暂不支持 {source.mode} 图像，请先转换为 8 位 RGB')
        # Adapted images.read_info_from_image standard metadata branch.
        metadata = source.info.copy()
        parameters = metadata.get('parameters', '')
        if metadata.get('exif'):
            try:
                comment = piexif.load(metadata['exif']).get('Exif', {}).get(piexif.ExifIFD.UserComment, b'')
                if comment:
                    parameters = piexif.helper.UserComment.load(comment)
            except (ValueError, OSError, TypeError, KeyError):
                pass
        source.load()
        oriented = ImageOps.exif_transpose(source)
        has_alpha = 'A' in oriented.getbands() or 'transparency' in metadata
        rgba = oriented.convert('RGBA') if has_alpha else None
        alpha = rgba.getchannel('A') if rgba else None
        rgb = (rgba or oriented).convert('RGB')
        return rgb, alpha, str(parameters or ''), {k: v for k, v in metadata.items() if isinstance(v, str)}


def apply_alpha(image, alpha, opts, original_size):
    if alpha is None:
        return image
    target, final = opts.dimensions(original_size)
    alpha = alpha.resize(target, Image.Resampling.LANCZOS)
    if target != final:
        x, y = (target[0] - final[0]) // 2, (target[1] - final[1]) // 2
        alpha = alpha.crop((x, y, x + final[0], y + final[1]))
    image = image.convert('RGBA')
    image.putalpha(alpha)
    return image


def save_result(image, destination, parameters, metadata, opts, cancel):
    """Save fully, then publish via Windows non-overwriting atomic rename."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    mode = {'upscale': 'UltraSharp V2', 'denoise': 'ScuNET', 'blend': 'UltraSharp V2 + ScuNET'}[opts.mode]
    processing = f'UpscaleToolkit: {opts.mode}, Models: {mode}, ScuNET blend: {opts.blend if opts.mode == "blend" else "n/a"}, Size: {image.width}x{image.height}'
    info = '\n'.join(part for part in (parameters, processing) if part)
    kwargs = {}
    if opts.format == 'png':
        # Fresh per-image dictionary: no metadata contamination across a batch.
        output_metadata = metadata.copy()
        output_metadata.update(parameters=info, postprocessing=processing)
        pnginfo = PngImagePlugin.PngInfo()
        for key, value in output_metadata.items():
            pnginfo.add_text(key, value)
        kwargs['pnginfo'] = pnginfo
    else:
        kwargs['exif'] = piexif.dump({'Exif': {piexif.ExifIFD.UserComment: piexif.helper.UserComment.dump(info, encoding='unicode')}})
        kwargs['quality'] = 95
        if opts.format == 'webp':
            kwargs['lossless'] = True
        elif image.mode == 'RGBA':
            background = Image.new('RGB', image.size, opts.jpeg_background)
            background.paste(image, mask=image.getchannel('A'))
            image = background
    fd, temporary = tempfile.mkstemp(prefix='.upscale-', suffix='.' + opts.format, dir=destination.parent)
    os.close(fd)
    try:
        image.save(temporary, format={'png': 'PNG', 'jpg': 'JPEG', 'webp': 'WEBP'}[opts.format], **kwargs)
        if cancel.is_set():
            from .engine import Cancelled
            raise Cancelled('保存前已取消')
        index = 0
        while True:
            candidate = destination if index == 0 else destination.with_name(f'{destination.stem}_{index}{destination.suffix}')
            try:
                if os.name == 'nt':
                    os.rename(temporary, candidate)  # Windows refuses existing destination
                else:
                    os.link(temporary, candidate)
                    os.unlink(temporary)
                return candidate
            except FileExistsError:
                index += 1
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

