"""Forge upscale execution adapted to explicit task state. AGPL-3.0.

Source functions and changes are documented in SOURCE_MAP.md.
"""
import copy
import gc
import logging
import threading

import torch
from PIL import Image
from spandrel import ImageModelDescriptor, ModelLoader

from .forge_grid import Grid, split_grid, combine_grid
from .forge_tensor import pil_image_to_torch_bgr, torch_bgr_to_pil_image
from .options import MODELS, Options, app_root


class Cancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel.is_set():
        raise Cancelled('任务已取消')


class Engine:
    def __init__(self, model_dir=None):
        self.model_dir = model_dir or app_root() / 'model'
        self.cache = {}
        self.active = None
        self.active_key = None
        torch.set_num_threads(min(8, torch.get_num_threads()))

    def release(self):
        self.active = None
        self.active_key = None
        gc.collect()
        if torch.cuda.is_initialized():
            try:
                torch.cuda.empty_cache()
            except Exception:
                logging.exception('CUDA cache cleanup failed; subsequent task will report its device error')

    def load(self, name, opts, progress, cancel):
        check_cancel(cancel)
        device = opts.device
        if device == 'auto':
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
        if device == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA 不可用；请检查 NVIDIA 驱动，或选择 CPU')
        if opts.half and device == 'cpu':
            raise ValueError('半精度需要 CUDA；当前为 CPU')
        key = (name, device, opts.half)
        if self.active_key == key:
            return self.active
        self.release()
        progress(f'加载 {MODELS[name]} · {device.upper()}', 0, 1)
        if name not in self.cache:
            path = self.model_dir / MODELS[name]
            if not path.is_file():
                raise FileNotFoundError(f'缺少模型：{path}')
            # Forge backend.utils: safe CPU load and unwrap state_dict.
            state = torch.load(path, map_location='cpu', weights_only=True)
            if 'state_dict' in state:
                state = state['state_dict']
            descriptor = ModelLoader().load_from_state_dict(state)
            if not isinstance(descriptor, ImageModelDescriptor) or descriptor.input_channels != 3 or descriptor.output_channels != 3:
                raise ValueError(f'{path.name} 不是支持的 RGB 图像模型')
            expected = 4 if name == 'ultrasharp' else 1
            if descriptor.scale != expected:
                raise ValueError(f'{path.name} 原生倍率应为 {expected}，实际为 {descriptor.scale}')
            self.cache[name] = descriptor.eval().float()
        original = self.cache[name]
        dtype = torch.float32
        if opts.half:
            if original.supports_half:
                dtype = torch.float16
            elif original.supports_bfloat16:
                dtype = torch.bfloat16
            else:
                raise ValueError(f'{original.architecture.name} 不支持半精度')
        # Keep pristine CPU FP32 weights to avoid rounding cached weights.
        self.active = original if device == 'cpu' else copy.deepcopy(original).to(device=device, dtype=dtype)
        self.active_key = key
        check_cancel(cancel)
        return self.active

    @staticmethod
    @torch.inference_mode()
    def patch(model, image):
        # Forge upscale_pil_patch, without global devices/autocast state.
        param = next(model.model.parameters())
        tensor = pil_image_to_torch_bgr(image).unsqueeze(0).to(device=param.device, dtype=param.dtype)
        if tensor.dtype != torch.float32 and model.architecture.name in ('ATD', 'DAT', 'DRCT'):
            previous = torch.get_default_dtype()
            try:
                torch.set_default_dtype(tensor.dtype)
                with torch.device(tensor.device):
                    output = model(tensor)
            finally:
                torch.set_default_dtype(previous)
        else:
            output = model(tensor)
        return torch_bgr_to_pil_image(output)

    def tiled(self, model, image, opts, progress, cancel, label):
        # Forge upscale_with_model_cpu; CUDA inference + CPU compositing.
        check_cancel(cancel)
        if opts.tile == 0:
            progress(f'{label} · 整图推理', 0, 1)
            result = self.patch(model, image)
            check_cancel(cancel)
            progress(label, 1, 1)
            return result
        grid = split_grid(image, opts.tile, opts.tile, opts.overlap)
        newtiles = []
        count = 0
        factor = model.scale
        for y, h, row in grid.tiles:
            newrow = []
            for x, w, tile in row:
                check_cancel(cancel)
                progress(f'{label} · 分块 {count + 1}/{grid.tile_count}', count, grid.tile_count)
                output = self.patch(model, tile)
                check_cancel(cancel)
                if output.size != (tile.width * factor, tile.height * factor):
                    raise RuntimeError('模型输出倍率与描述不一致')
                newrow.append([x * factor, w * factor, output])
                count += 1
                progress(label, count, grid.tile_count)
            newtiles.append([y * factor, h * factor, newrow])
        check_cancel(cancel)
        return combine_grid(Grid(newtiles, grid.tile_w * factor, grid.tile_h * factor,
                                 grid.image_w * factor, grid.image_h * factor, grid.overlap * factor))

    def branch(self, name, image, opts, progress, cancel):
        model = self.load(name, opts, progress, cancel)
        target, final = opts.dimensions(image.size)
        result = image
        # Forge Upscaler.upscale: 4 passes maximum, stop at size/no growth, Lanczos.
        for step in range(4):
            before = result.size
            result = self.tiled(model, result, opts, progress, cancel, f'{model.architecture.name} · 第 {step + 1} 轮')
            if (result.width >= target[0] and result.height >= target[1]) or result.size == before:
                break
        if result.size != target:
            result = result.resize(target, Image.Resampling.LANCZOS)
        if target != final:
            x, y = (result.width - final[0]) // 2, (result.height - final[1]) // 2
            result = result.crop((x, y, x + final[0], y + final[1]))
        return result

    def process(self, image, opts: Options, progress=lambda *a: None, cancel=None):
        opts.validate()
        cancel = cancel or threading.Event()
        if opts.mode == 'denoise' or (opts.mode == 'blend' and opts.blend == 1):
            return self.branch('scunet', image, opts, progress, cancel)
        main = self.branch('ultrasharp', image, opts, progress, cancel)
        if opts.mode == 'blend' and opts.blend > 0:
            # Same original image: ScriptPostprocessingUpscale.process semantics.
            second = self.branch('scunet', image, opts, progress, cancel)
            check_cancel(cancel)
            main = Image.blend(main, second.convert(main.mode), opts.blend)
        check_cancel(cancel)
        return main
