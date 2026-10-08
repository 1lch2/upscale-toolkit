import json
import logging
import os
from pathlib import Path


def user_dir():
    path = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'UpscaleToolkit'
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging():
    logging.basicConfig(filename=user_dir() / 'app.log', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8')


def load_settings():
    try:
        return json.loads((user_dir() / 'settings.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_settings(data):
    (user_dir() / 'settings.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
