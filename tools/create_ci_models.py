"""Generate untrained, small real architectures for CPU pipeline E2E only."""
import argparse
import json
from pathlib import Path

import torch
from spandrel import ModelLoader
from spandrel.architectures.DAT import DAT
from spandrel.architectures.SCUNet import SCUNet


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('build/ci-models'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(123)
    models = {'4x-UltraSharpV2.pth': DAT(embed_dim=32, depth=[1], num_heads=[2], upscale=4, expansion_factor=2),
              'ScuNET.pth': SCUNet(dim=8, config=[0] * 7)}
    descriptions = {}
    for filename, model in models.items():
        path = args.output / filename
        torch.save(model.state_dict(), path)
        descriptor = ModelLoader().load_from_file(str(path))
        descriptions[filename] = {'architecture': descriptor.architecture.name, 'scale': descriptor.scale,
                                  'untrained_test_fixture': True}
    (args.output / 'TEST_FIXTURES.json').write_text(json.dumps(descriptions, indent=2), encoding='utf-8')
    print(f'Generated test-only weights: {args.output.resolve()}')


if __name__ == '__main__':
    main()
