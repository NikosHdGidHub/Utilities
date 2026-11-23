"""Validate trusted local layers and compile independent, in-memory plans."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from common import Command, DeploymentError, check_placeholders, inside, is_link, relative_path

STAGES = ("Prepare", "Scaffold", "Dependencies", "Cleanup", "Files", "Finalize", "Git", "GitHub")


def strings(value, field):
    if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
        raise ValueError(f"{field}: требуется список строк")
    return value


def commands(items):
    if not isinstance(items, list):
        raise ValueError("Этап должен содержать список команд")
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("label"), str) or not item["label"].strip():
            raise ValueError("У команды отсутствует label")
        if type(item.get("required", True)) is not bool:
            raise ValueError("required должен быть true или false")
        for field in ("args", "args_windows"):
            if field == "args_windows" and field not in item:
                continue
            args = item.get(field)
            if (not isinstance(args, list) or not args or not args[0]
                    or not all(isinstance(a, str) and "\0" not in a for a in args) or not args[0].strip()):
                raise ValueError(f"Некорректное поле {field}")
            for arg in args:
                check_placeholders(arg)
            if args[0].startswith("./"):
                relative_path(args[0][2:])
        args = item.get("args_windows", item["args"]) if os.name == "nt" else item["args"]
        yield Command(item["label"], tuple(args), item.get("required", True))


@dataclass
class Layer:
    data: dict
    stages: dict
    files: dict
    remove: list
    mkdir: list

    @classmethod
    def read(cls, folder):
        data = json.loads(inside(folder, Path("template.json")).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or type(data.get("version", 1)) is not int or data.get("version", 1) != 1:
            raise ValueError("Неизвестная версия формата")
        data.setdefault("id", folder.name)
        for key in ("id", "name", "description", "extends"):
            if key == "extends" and key not in data:
                continue
            if not isinstance(data.get(key), str) or not data[key].strip():
                raise ValueError(f"Заполните {key}")
        strings(data.get("features", []), "features")
        if type(data.get("component", False)) is not bool:
            raise ValueError("component должен быть true или false")
        stages = data.get("stages", {})
        if not isinstance(stages, dict) or set(stages) - set(STAGES):
            raise ValueError("Некорректный этап")
        stages = {key: list(commands(value)) for key, value in stages.items()}
        for key, old in (("Scaffold", "commands"), ("Finalize", "post_commands")):
            stages.setdefault(key, []).extend(commands(data.get(old, [])))
        source = inside(folder, relative_path(data.get("files", "files")))
        files = {}
        if source.exists() or "files" in data:
            if not source.is_dir():
                raise ValueError(f"Отсутствует каталог {source}")
            for item in sorted(source.rglob("*")):
                rel = item.relative_to(source)
                inside(source, rel)
                if item.is_file():
                    raw = item.read_bytes()
                    try:
                        value = raw.decode() if b"\0" not in raw else raw
                    except UnicodeDecodeError:
                        value = raw
                    if isinstance(value, str):
                        check_placeholders(value)
                    files[rel] = value
        paths = [[relative_path(p) for p in strings(data.get(k, []), k)] for k in ("remove", "mkdir")]
        return cls(data, stages, files, *paths)


@dataclass
class Preset:
    id: str
    name: str
    description: str
    stages: dict
    files: dict
    remove: tuple
    mkdir: tuple
    cheatsheet: str

    @classmethod
    def load(cls, directory):
        presets, errors = load_presets(directory.parent)
        ident = Layer.read(directory).data["id"]
        for preset in presets:
            if preset.id == ident:
                return preset
        raise ValueError("\n".join(errors))


def plan(key, layers):
    ordered, seen, visiting = [], set(), set()

    def visit(ident):
        if ident in visiting:
            raise ValueError(f"Цикл шаблонов: {ident}")
        if ident in seen:
            return
        if ident not in layers:
            raise ValueError(f"Не найден шаблон: {ident}")
        layer = layers[ident]
        visiting.add(ident)
        if "extends" in layer.data:
            visit(layer.data["extends"])
        for feature in layer.data.get("features", []):
            visit(feature)
        visiting.remove(ident)
        seen.add(ident)
        ordered.append(layer)

    visit(key)
    stages = {stage: [] for stage in STAGES}
    files, remove, mkdir = {}, {}, {}
    for layer in ordered:
        for stage, ops in layer.stages.items():
            stages[stage].extend(ops)
        files.update(layer.files)
        remove.update(dict.fromkeys(layer.remove))
        mkdir.update(dict.fromkeys(layer.mkdir))
    data = layers[key].data
    sheet = files.get(Path("CHEATSHEET.md"), "")
    if not data.get("component") and (not isinstance(sheet, str) or not sheet.strip()):
        raise ValueError("Заполните CHEATSHEET.md")
    for path in (*files, *mkdir):
        if any(parent in files for parent in path.parents) or path in files and path in mkdir:
            raise ValueError(f"Конфликт файла и каталога: {path}")
    return Preset(key, data["name"], data["description"], stages, files, tuple(remove), tuple(mkdir), sheet)


def load_presets(*roots):
    layers, errors, result = {}, [], []

    def scan(directory):
        if is_link(directory):
            raise ValueError(f"Ссылка на каталог шаблонов: {directory}")
        if (directory / "template.json").exists():
            layer = Layer.read(directory)
            key = layer.data["id"]
            if key in layers:
                raise ValueError(f"Повтор ID: {key}")
            layers[key] = layer
            return
        children = sorted(p for p in directory.iterdir() if p.is_dir() and not p.name.startswith("."))
        if not children or (directory / "files").exists():
            raise ValueError("Отсутствует template.json")
        for child in children:
            scan_checked(child)

    def scan_checked(directory):
        try:
            scan(directory)
        except (OSError, ValueError, DeploymentError) as exc:
            errors.append(f"{directory}: {exc}")

    for root in roots:
        if root.is_dir():
            try:
                for child in sorted(root.iterdir()):
                    if child.is_dir() and not child.name.startswith("."):
                        scan_checked(child)
            except OSError as exc:
                errors.append(str(exc))
    for key, layer in layers.items():
        try:
            preset = plan(key, layers)
            if not layer.data.get("component"):
                result.append(preset)
        except ValueError as exc:
            errors.append(f"{key}: {exc}")
    return result, errors
