"""Shared path validation, interpolation and subprocess primitives."""

from __future__ import annotations

import html
import json
import locale
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


APP_DIR = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
BUNDLED_TEMPLATES = APP_DIR / "templates"
PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")
BATCH_ARGUMENT = re.compile(r"[a-zA-Z0-9_./:=@+,-]+")
VARIABLES = {"project_name", "project_name_json", "project_name_html", "folder_name", "package_name"}
WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in "123456789¹²³"
}


class DeploymentError(Exception):
    """A validation or deployment failure that can be shown in the GUI."""


@dataclass(frozen=True)
class Command:
    label: str
    args: tuple[str, ...]
    required: bool = True


def user_templates() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ProjectDeployer" / "templates"


def check_placeholders(text: str) -> None:
    unknown = set(PLACEHOLDER.findall(text)) - VARIABLES
    if unknown:
        raise ValueError(f"неизвестные переменные: {', '.join(sorted(unknown))}")


def render(text: str, variables: dict[str, str]) -> str:
    check_placeholders(text)
    return PLACEHOLDER.sub(lambda match: variables[match[1]], text)


def project_variables(project_name: str, folder_name: str) -> dict[str, str]:
    # npm package names use a portable ASCII identifier.
    ascii_name = unicodedata.normalize("NFKD", project_name).encode("ascii", "ignore").decode()
    package_name = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:214].rstrip("-")
    return {
        "project_name": project_name,
        "project_name_json": json.dumps(project_name, ensure_ascii=False),
        "project_name_html": html.escape(project_name).replace("%", "&#37;"),
        "folder_name": folder_name,
        "package_name": package_name or "project",
    }


def resolve_destination(parent: str, folder_name: str) -> Path:
    if (
        not folder_name or folder_name in {".", ".."}
        or folder_name != folder_name.strip() or folder_name.endswith(".")
        or any(char in '<>:"/\\|?*' or ord(char) < 32 for char in folder_name)
        or folder_name.split(".")[0].rstrip().upper() in WINDOWS_DEVICES
    ):
        raise DeploymentError("Укажите допустимое имя одной папки, например my-project.")
    if not parent.strip():
        raise DeploymentError("Выберите каталог для создания проекта.")
    try:
        base = Path(parent.strip()).expanduser().resolve(strict=True)
    except (OSError, ValueError, RuntimeError) as exc:
        raise DeploymentError("Выберите существующий каталог для создания проекта.") from exc
    if not base.is_dir():
        raise DeploymentError("Выберите существующий каталог для создания проекта.")
    return base / folder_name


def resolve_program(name: str) -> str:
    if name == "python":
        override = os.environ.get("PROJECT_DEPLOYER_PYTHON")
        if override:
            name = override
        elif not getattr(sys, "frozen", False):
            return sys.executable
    executable = shutil.which(name)
    if executable is None:
        raise DeploymentError(f"Команда «{name}» недоступна. Установите инструмент и проверьте PATH.")
    return executable


def prepare_command(command: Command, variables: dict[str, str], cwd: Path | None = None) -> Command:
    program, *args = (render(arg, variables) for arg in command.args)
    if program.startswith("./") and cwd is not None:
        program = str(cwd / relative_path(program[2:]))
    executable = resolve_program(program)
    # Windows can route batch launchers (including npm.cmd) through cmd.exe.
    if sys.platform == "win32" and Path(executable).suffix.lower() in {".bat", ".cmd"}:
        if any(c in executable for c in '"&|<>^%!') or any(BATCH_ARGUMENT.fullmatch(arg) is None for arg in args):
            raise DeploymentError(f"Шаг «{command.label}» содержит недопустимые аргументы для .cmd/.bat.")
    return Command(command.label, (executable, *args))


def run_command(command: Command, cwd: Path, log: Callable[[str], None]) -> None:
    log(f"› {command.label} · {subprocess.list2cmdline(command.args)}")
    with subprocess.Popen(
        command.args,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ) as process:
        assert process.stdout is not None
        for line in process.stdout:
            try:
                decoded = line.decode("utf-8")
            except UnicodeDecodeError:
                decoded = line.decode(locale.getpreferredencoding(False), errors="replace")
            log(decoded.rstrip())
        status = process.wait()
    if status:
        raise DeploymentError(f"Шаг «{command.label}» завершился с кодом {status}.")



def relative_path(value: str) -> Path:
    from pathlib import PureWindowsPath
    if not isinstance(value, str) or PureWindowsPath(value).drive:
        raise ValueError(f"Некорректный относительный путь: {value!r}")
    parts = value.replace("\\", "/").split("/")
    for part in parts:
        if (not part or part != part.strip() or part.endswith(".")
                or any(c in '<>:"|?*' or ord(c) < 32 for c in part)
                or part.split(".")[0].rstrip().upper() in WINDOWS_DEVICES):
            raise ValueError(f"Недопустимый путь: {value!r}")
    return Path(*parts)


def is_link(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 1024)


def inside(root: Path, relative: Path) -> Path:
    current = root
    for part in ("", *relative_path(relative.as_posix()).parts):
        current = current / part
        if is_link(current):
            raise DeploymentError(f"Переход через ссылку запрещён: {current}")
    return current
