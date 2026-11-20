"""Load file-based presets and create projects from their commands and files."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


BUNDLED_TEMPLATES = Path(__file__).resolve().parent / "templates"
PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")
BATCH_ARGUMENT = re.compile(r"[a-zA-Z0-9_./:=@+,-]+")
VARIABLES = {"project_name", "project_name_json", "folder_name", "package_name"}
WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in "123456789¹²³"
}


class DeploymentError(Exception):
    """A validation or deployment failure that can be shown in the GUI."""


@dataclass(frozen=True)
class Command:
    label: str
    args: tuple[str, ...]


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    commands: tuple[Command, ...]
    post_commands: tuple[Command, ...]
    files: Path
    cheatsheet: str

    @classmethod
    def load(cls, directory: Path) -> Preset:
        data = json.loads((directory / "template.json").read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("template.json должен содержать объект")
        for key in ("name", "description"):
            if not isinstance(data.get(key), str) or not data[key].strip():
                raise ValueError(f"заполните текстовое поле {key}")

        files = directory / "files"
        cheatsheet = (files / "CHEATSHEET.md").read_text(encoding="utf-8")
        if not cheatsheet.strip():
            raise ValueError("заполните files/CHEATSHEET.md")
        check_placeholders(cheatsheet)
        return cls(
            data["name"], data["description"],
            parse_commands(data.get("commands", []), "commands"),
            parse_commands(data.get("post_commands", []), "post_commands"),
            files, cheatsheet,
        )


def parse_commands(raw: object, field: str) -> tuple[Command, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{field} должен содержать список команд")
    commands = []
    for command in raw:
        if not isinstance(command, dict):
            raise ValueError("каждая команда должна содержать label и args")
        label, args = command.get("label"), command.get("args")
        if not isinstance(label, str) or not label.strip():
            raise ValueError("заполните текстовое поле label")
        if not isinstance(args, list) or not args or any(
            not isinstance(arg, str) or "\0" in arg for arg in args
        ) or not args[0].strip():
            raise ValueError("args должен содержать исполняемый файл и его аргументы")
        for arg in args:
            check_placeholders(arg)
        commands.append(Command(label, tuple(args)))
    return tuple(commands)


def user_templates() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ProjectDeployer" / "templates"


def load_presets(*roots: Path) -> tuple[list[Preset], list[str]]:
    presets, errors = [], []
    for root in roots:
        try:
            directories = sorted(root.iterdir())
        except FileNotFoundError:
            continue
        except OSError as exc:
            errors.append(f"{root}: {exc}")
            continue
        for directory in directories:
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            try:
                presets.append(Preset.load(directory))
            except (OSError, ValueError) as exc:
                errors.append(f"{directory.name}: {exc}")
    return presets, errors


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


def prepare_command(command: Command, variables: dict[str, str]) -> Command:
    program, *args = (render(arg, variables) for arg in command.args)
    executable = resolve_program(program)
    # Windows can route batch launchers (including npm.cmd) through cmd.exe.
    if sys.platform == "win32" and Path(executable).suffix.lower() in {".bat", ".cmd"}:
        if any(BATCH_ARGUMENT.fullmatch(arg) is None for arg in args):
            raise DeploymentError(f"Шаг «{command.label}» содержит недопустимые аргументы для .cmd/.bat.")
    return Command(command.label, (executable, *args))


def run_command(command: Command, cwd: Path, log: Callable[[str], None]) -> None:
    log(f"› {command.label}")
    with subprocess.Popen(
        command.args,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ) as process:
        assert process.stdout is not None
        for line in process.stdout:
            log(line.rstrip())
        status = process.wait()
    if status:
        raise DeploymentError(f"Шаг «{command.label}» завершился с кодом {status}.")


def copy_preset_files(source: Path, destination: Path, variables: dict[str, str]) -> None:
    # Create files exclusively, including nested files, so collisions are surfaced.
    for item in sorted(source.rglob("*")):
        target = destination / item.relative_to(source)
        if item.is_symlink() or target.is_symlink():
            raise DeploymentError(f"Копирование через символическую ссылку: {item.relative_to(source)}")
        if item.is_dir():
            target.mkdir(exist_ok=True)
            continue
        data = item.read_bytes()
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            pass
        else:
            data = render(content, variables).encode("utf-8")
        with target.open("xb") as file:
            file.write(data)


def deploy(
    preset: Preset, project_name: str, folder_name: str, parent: str,
    log: Callable[[str], None],
) -> Path:
    project_name = project_name.strip()
    if not project_name or not project_name.isprintable():
        raise DeploymentError("Введите название проекта без управляющих символов.")
    destination = resolve_destination(parent, folder_name)
    variables = project_variables(project_name, folder_name)
    if os.path.lexists(destination):
        raise DeploymentError(f"Папка уже существует: {destination}")
    commands = [prepare_command(command, variables) for command in preset.commands]
    post_commands = [prepare_command(command, variables) for command in preset.post_commands]

    try:
        destination.mkdir()
    except FileExistsError as exc:
        raise DeploymentError(f"Папка уже существует: {destination}") from exc
    except OSError as exc:
        raise DeploymentError(f"Не удалось создать папку: {exc}") from exc

    try:
        log(f"Проект: {destination}")
        for command in commands:
            run_command(command, destination, log)
        log("› Запись файлов шаблона и шпаргалки")
        copy_preset_files(preset.files, destination, variables)
        for command in post_commands:
            run_command(command, destination, log)
    except (DeploymentError, OSError, ValueError) as exc:
        raise DeploymentError(f"{exc}\nЧастично созданный проект: {destination}") from exc
    return destination
