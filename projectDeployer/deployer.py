"""Execute a compiled preset in an exclusively created directory."""
import os
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from common import (BUNDLED_TEMPLATES, Command, DeploymentError, inside, is_link,
                    prepare_command, project_variables, render, resolve_destination,
                    resolve_program, run_command, user_templates)
from presets import STAGES, Preset, load_presets
import git_ops


class PartialProject(DeploymentError):
    def __init__(self, message, path, identity):
        super().__init__(f"{message}\nЧастично созданный проект: {path}")
        self.path = path
        self.identity = identity

    def discard(self):
        verify_root(self.path, self.identity)
        shutil.rmtree(self.path)


def verify_root(path, identity):
    info = path.lstat()
    if is_link(path) or (info.st_dev, info.st_ino) != identity:
        raise DeploymentError("Каталог проекта был заменён")


def write_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Replace the entry atomically, including if a generator made a hard link.
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        try:
            stream.write(content)
            stream.close()
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)


def deploy(preset, project_name, folder_name, parent, log, *, decide=None, publication=None, warn=None):
    project_name = project_name.strip()
    if not project_name or not project_name.isprintable():
        raise DeploymentError("Введите название проекта без управляющих символов.")
    dest = resolve_destination(parent, folder_name)
    if os.path.lexists(dest):
        raise DeploymentError(f"Папка уже существует: {dest}")
    variables = project_variables(project_name, folder_name)

    def attempt(label, action, required=True):
        while True:
            try:
                return action()
            except (DeploymentError, ValueError, OSError) as exc:
                message = f"{label}: {exc}"
                log(message)
                choice = decide(message, required) if decide else ("stop" if required else "skip")
                if choice == "retry":
                    continue
                if choice == "skip" and not required:
                    log("Предупреждение: " + message)
                    if warn:
                        warn(message)
                    return
                raise DeploymentError(message) from exc

    attempt("Проверка Git", lambda: resolve_program("git"))
    for stage, ops in preset.stages.items():
        if stage == "GitHub":
            continue
        for op in ops:
            if op.required and not op.args[0].startswith("./"):
                attempt(op.label, lambda: prepare_command(op, variables))
    try:
        dest.mkdir()
    except OSError as exc:
        raise DeploymentError(f"Не удалось создать папку {dest}: {exc}") from exc
    info = dest.lstat()
    identity = info.st_dev, info.st_ino

    def command(op):
        verify_root(dest, identity)
        run_command(prepare_command(op, variables, dest), dest, log)

    stage = "Prepare"
    try:
        log(f"Проект: {dest}")
        for stage in STAGES:
            if stage == "GitHub" and not publication:
                continue
            verify_root(dest, identity)
            log(f"Этап {stage}")
            if stage == "Cleanup":
                for rel in preset.remove:
                    path = inside(dest, rel)
                    log(f"Удаление: {rel}")
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink(missing_ok=True)
            if stage == "Files":
                for rel in preset.mkdir:
                    log(f"Каталог: {rel}")
                    inside(dest, rel).mkdir(parents=True, exist_ok=True)
                for rel, value in preset.files.items():
                    log(f"Запись: {rel}")
                    data = render(value, variables).encode() if isinstance(value, str) else value
                    write_file(inside(dest, rel), data)
            for op in preset.stages[stage]:
                attempt(op.label, lambda: command(op), op.required)
            if stage == "Git":
                for op in git_ops.steps():
                    attempt(op.label, lambda: command(op))
            if stage == "GitHub":
                attempt("Публикация GitHub", lambda: publication.publish(dest, log), False)
    except (DeploymentError, ValueError, OSError) as exc:
        if stage == "GitHub":
            log(f"Проект сохранён. Ошибка публикации: {exc}")
            if warn:
                warn(str(exc))
        else:
            raise PartialProject(str(exc), dest, identity) from exc
    return dest
