import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from common import APP_DIR

SETTINGS = APP_DIR / "settings.json"


def save_default(directory):
    with NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, dir=SETTINGS.parent) as f:
        try:
            json.dump({"directory": str(directory)}, f, ensure_ascii=False, indent=2)
            f.close()
            os.replace(f.name, SETTINGS)
        finally:
            Path(f.name).unlink(missing_ok=True)


def default_directory():
    if not SETTINGS.exists():
        save_default(Path.home())
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("directory"), str) or not data["directory"].strip() or not Path(data["directory"]).is_dir():
        raise ValueError("Проверьте каталог в settings.json")
    return data["directory"]
