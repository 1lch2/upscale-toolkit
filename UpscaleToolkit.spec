# Build with build.ps1, which prepares dependency/license metadata.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

root = Path(SPECPATH)
metadata = Path(os.environ['UPSCALE_BUILD_METADATA'])
model_readme = root / 'model' / 'README.md'
if not model_readme.is_file():
    model_readme = root.parent / 'model' / 'README.md'
datas = [(str(metadata / 'licenses'), 'licenses'),
         (str(metadata / 'runtime-versions.json'), '.'),
         (str(metadata / 'build-manifest.json'), '.'),
         (str(model_readme), 'model')]
include_models = os.environ.get('UPSCALE_INCLUDE_MODELS') == '1'
if include_models:
    for filename in ('4x-UltraSharpV2.pth', 'ScuNET.pth'):
        datas.append((str(Path(os.environ['UPSCALE_MODEL_DIR']) / filename), 'model'))

# Explicit source list avoids .git, test fixtures, caches and private model files.
source_files = ['app.py', 'build.ps1', 'UpscaleToolkit.spec', 'requirements-lock.txt',
                'requirements-torch.txt', 'source-manifest.json', 'SOURCE_MAP.md',
                'README.md', 'LICENSE', 'CONTRIBUTING.md']
for name in source_files:
    datas.append((str(root / name), 'source'))
for directory in ('upscale_toolkit', 'tools', '.github'):
    for file in (root / directory).rglob('*'):
        if file.is_file() and file.suffix in ('.py', '.ps1', '.yml', '.yaml'):
            datas.append((str(file), str(Path('source') / file.relative_to(root).parent)))
datas.extend([(str(root / 'README.md'), '.'), (str(root / 'LICENSE'), '.')])
datas.append((str(root / 'licenses' / 'README.md'), 'source/licenses'))
datas += copy_metadata('spandrel')
analysis = Analysis([str(root / 'app.py')], pathex=[str(root)], binaries=[], datas=datas,
                    hiddenimports=collect_submodules('spandrel'),
                    excludes=['matplotlib', 'scipy', 'pandas', 'IPython', 'pytest', 'tensorboard',
                              'cv2', 'gradio', 'transformers', 'torchaudio', 'spandrel_extra_arches'],
                    noarchive=False)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name='UpscaleToolkit',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, contents_directory='.')
collection = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name='UpscaleToolkit')
