"""Portable path-only configuration and the original laboratory rules reader."""
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE/'local-config.json'


def config():
    if not CONFIG_PATH.is_file():
        return {}
    return json.loads(CONFIG_PATH.read_text(encoding='utf-8-sig'))


def path_setting(environment, key, default):
    value = os.getenv(environment) or config().get(key) or default
    return Path(value).expanduser().resolve()


def load_rules(path=None):
    if path is None:
        lab_root = os.getenv('NEXUS_LAB_ROOT')
        default = str(Path(lab_root)/'lab_rules.json') if lab_root else str(HERE/'lab_rules.json')
        path = path_setting('NEXUS_RULES_PATH','rulesPath',default)
    raw = Path(path).read_bytes()
    rules = json.loads(raw.decode('utf-8-sig'))
    rules['_hash'] = hashlib.sha256(raw).hexdigest()[:16]
    return rules


def data_mode(quote_root):
    marker = Path(quote_root).parent/'DEMO.json'
    return 'synthetic' if marker.is_file() else 'historical'
