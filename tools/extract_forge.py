"""Initial source extraction, not used at application runtime."""
import ast
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
project = Path(__file__).resolve().parents[1]
destination = project / 'upscale_toolkit'
destination.mkdir(exist_ok=True)
specs = {
    'forge_grid.py': ('modules/images.py', ['Grid', 'split_grid', 'combine_grid'],
                      'import math\nfrom collections import namedtuple\nimport numpy as np\nfrom PIL import Image\n'),
    'forge_tensor.py': ('modules/upscaler_utils.py', ['pil_image_to_torch_bgr', 'torch_bgr_to_pil_image'],
                        'import numpy as np\nimport torch\nfrom PIL import Image\n'),
}
manifest = {}
for filename, (relative, symbols, imports) in specs.items():
    source = root / relative
    raw = source.read_bytes()
    code = raw.decode('utf-8-sig').replace('\r\n', '\n')
    nodes = {n.name: n for n in ast.parse(code).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    header = f'"""Extracted from Forge {relative}. AGPL-3.0; see SOURCE_MAP.md."""\n'
    chunks = [ast.get_source_segment(code, nodes[name]) for name in symbols]
    (destination / filename).write_text(header + imports + '\n\n' + '\n\n\n'.join(chunks) + '\n', encoding='utf-8')
    manifest[relative] = {'sha256': hashlib.sha256(raw).hexdigest(), 'symbols': symbols}
for relative in ['modules/upscaler.py', 'modules/modelloader.py', 'backend/utils.py',
                 'scripts/postprocessing_upscale.py', 'modules/postprocessing.py']:
    manifest[relative] = {'sha256': hashlib.sha256((root / relative).read_bytes()).hexdigest()}
(project / 'source-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
shutil = __import__('shutil')
shutil.copy2(root / 'LICENSE', project / 'LICENSE')
print('Extracted grid/tensor routines and recorded source hashes.')
