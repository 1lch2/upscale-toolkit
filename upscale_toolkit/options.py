from dataclasses import dataclass
from pathlib import Path
import math
import sys

MODELS = {'ultrasharp': '4x-UltraSharpV2.pth', 'scunet': 'ScuNET.pth'}


def app_root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Options:
    mode: str = 'upscale'
    blend: float = 0.25
    sizing: str = 'scale'
    scale: float = 4.0
    max_edge: int = 0
    width: int = 1920
    height: int = 1080
    fit: str = 'contain'
    resize_denoise: bool = False
    device: str = 'auto'
    half: bool = False
    tile: int = 256
    overlap: int = 16
    format: str = 'png'
    jpeg_background: str = '#ffffff'

    def validate(self):
        if self.mode not in ('upscale', 'denoise', 'blend'):
            raise ValueError('未知处理模式')
        if not math.isfinite(self.blend) or not 0 <= self.blend <= 1:
            raise ValueError('融合比例必须为 0 到 1')
        if self.sizing not in ('scale', 'size') or self.fit not in ('contain', 'crop'):
            raise ValueError('未知尺寸方式')
        if not math.isfinite(self.scale) or self.scale <= 0 or min(self.width, self.height) < 1 or self.max_edge < 0:
            raise ValueError('倍率和宽高必须大于 0，最大边不能为负数')
        if self.tile < 0 or self.overlap < 0 or (self.tile and self.overlap >= self.tile):
            raise ValueError('分块须为 0（整图）或正整数；重叠须满足 0 ≤ 重叠 < 分块')
        if self.device not in ('auto', 'cpu', 'cuda') or self.format not in ('png', 'jpg', 'webp'):
            raise ValueError('未知设备或输出格式')
        if self.device == 'cpu' and self.half:
            raise ValueError('CPU 只支持 FP32，请关闭半精度')

    def dimensions(self, original):
        """Inference target and final crop size, adapted Forge Lanczos/crop flow."""
        w, h = original
        if self.mode == 'denoise' and not self.resize_denoise:
            return (w, h), (w, h)
        if self.sizing == 'scale':
            ratio = self.scale
            if self.max_edge:
                ratio = min(ratio, self.max_edge / max(w, h))
            size = max(1, round(w * ratio)), max(1, round(h * ratio))
            return size, size
        ratio = (max if self.fit == 'crop' else min)(self.width / w, self.height / h)
        resize = max(1, round(w * ratio)), max(1, round(h * ratio))
        return resize, (self.width, self.height) if self.fit == 'crop' else resize

