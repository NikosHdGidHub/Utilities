#!/usr/bin/env python3
"""
Универсальная сборка через PyInstaller.

Кидаешь этот файл рядом с main.py в любой папке и запускаешь:

    python build.py

Что делает:
  - находит main.py (или любой другой .py с точкой входа);
  - ищет иконку (icon.ico / icon.png / app.ico / app.png);
  - чистит build/ и dist/ от прошлой сборки;
  - собирает один exe в dist/;
  - удаляет сгенерированный .spec, чтобы не мусорить.

Опции:
  python build.py myapp.py            # конкретный входной файл
  python build.py --name MyApp        # имя выходного exe
  python build.py --console           # показать консоль (по умолчанию скрыта)
  python build.py --onefile false     # собрать папкой, а не одним файлом
  python build.py --no-clean          # не чистить build/ и dist/
  python build.py --keep-spec         # оставить .spec после сборки
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def find_entry(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            sys.exit(f"[build] Не найден входной файл: {p}")
        return p

    main = Path("main.py")
    if main.exists():
        return main

    for candidate in sorted(Path(".").glob("*.py")):
        if candidate.name == "build.py":
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "__name__" in text and "__main__" in text:
            return candidate

    sys.exit(
        "[build] main.py не найден. Укажи файл явно: "
        "python build.py myscript.py"
    )


def find_icon() -> Path | None:
    for name in ("icon.ico", "icon.png", "app.ico", "app.png"):
        p = Path(name)
        if p.exists():
            return p
    return None

def find_python() -> str:
    """
    Возвращает путь к python, в котором есть PyInstaller.

    Приоритет:
      1. venv в текущей папке (.venv, venv, env) — если в нём есть PyInstaller.
      2. Текущий интерпретатор — если PyInstaller установлен.
      3. Первый venv, где PyInstaller есть, даже если это не наш текущий.
    """
    candidates: list[Path] = []

    for venv_name in (".venv", "venv", "env"):
        venv_dir = Path(venv_name)
        if not venv_dir.is_dir():
            continue
        if sys.platform == "win32":
            candidates.append(venv_dir / "Scripts" / "python.exe")
        else:
            candidates.append(venv_dir / "bin" / "python")

    # 1. venv с PyInstaller
    for python_path in candidates:
        if python_path.exists() and _has_pyinstaller(python_path):
            print(f"[build] Использую venv: {python_path}")
            return str(python_path)

    # 2. текущий интерпретатор
    if _has_pyinstaller(Path(sys.executable)):
        return sys.executable

    # 3. любой venv, даже без PyInstaller — потом упадём с понятной ошибкой
    for python_path in candidates:
        if python_path.exists():
            print(
                f"[build] PyInstaller не найден ни в текущем Python, "
                f"ни в venv. Использую {python_path}."
            )
            return str(python_path)

    print(
        "[build] PyInstaller не найден. Собираю текущим интерпретатором — "
        "возможно, дальше будет ошибка."
    )
    return sys.executable


def _has_pyinstaller(python_exe: Path) -> bool:
    """Проверяет, установлен ли PyInstaller в этом интерпретаторе."""
    try:
        result = subprocess.run(
            [str(python_exe), "-c", "import PyInstaller"],
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Универсальная сборка PyInstaller"
    )
    parser.add_argument("entry", nargs="?",
                        help="Входной .py (по умолчанию main.py)")
    parser.add_argument("--name",
                        help="Имя выходного exe (по умолчанию — имя папки)")
    parser.add_argument("--console", action="store_true",
                        help="Оставить консольное окно")
    parser.add_argument("--onefile", default="true",
                        choices=["true", "false"],
                        help="Собрать одним файлом (true) или папкой (false)")
    parser.add_argument("--no-clean", action="store_true",
                        help="Не удалять build/ и dist/ перед сборкой")
    parser.add_argument("--keep-spec", action="store_true",
                        help="Оставить сгенерированный .spec")
    args = parser.parse_args()

    entry = find_entry(args.entry)
    name = args.name or Path.cwd().name
    icon = find_icon()

    if not args.no_clean:
        for d in ("build", "dist"):
            if Path(d).exists():
                print(f"[build] Удаляю {d}/")
                shutil.rmtree(d, ignore_errors=True)

    python_exe = find_python()

    cmd = [
        python_exe, "-m", "PyInstaller",
        str(entry),
        "--name", name,
        "--clean", "--noconfirm",
    ]

    if args.onefile == "true":
        cmd.append("--onefile")

    if not args.console:
        cmd.append("--windowed")

    if icon is not None:
        print(f"[build] Иконка: {icon}")
        cmd += ["--icon", str(icon)]
    else:
        print("[build] Иконка не найдена — пропускаю")

    print("[build] Команда:")
    print("  ", " ".join(cmd))
    print()

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("\n[build] Сборка не удалась.", file=sys.stderr)
        print(
            "\nПодсказка: если PyInstaller не установлен, "
            "активируй venv или поставь его:\n"
            "    .\\.venv\\Scripts\\Activate.ps1\n"
            "    pip install pyinstaller",
            file=sys.stderr,
        )
        return result.returncode

    if not args.keep_spec:
        spec = Path(f"{name}.spec")
        if spec.exists():
            spec.unlink()

    dist = Path("dist")
    if dist.exists():
        print(f"\n[build] Готово: {dist.resolve()}")
        for item in sorted(dist.iterdir()):
            print(f"  {item.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())