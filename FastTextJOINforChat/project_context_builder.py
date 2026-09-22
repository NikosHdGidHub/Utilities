#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Project Context Builder

Выбирает каталог и создаёт один TXT-файл для передачи проектного
контекста в ChatGPT/другую LLM.

В итоговом файле:
1. Полное дерево каталога со всеми файлами.
2. Затем содержимое найденных текстовых/кодовых файлов.
3. Каждый файл имеет явно обозначенные BEGIN/END-блоки.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox


# Папки, которые обычно не нужны в контексте проекта.
# Их можно убрать, если нужно включать абсолютно всё содержимое.
DEFAULT_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".idea",
    ".vscode",
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    "coverage",
}


# Явно текстовые расширения.
TEXT_EXTENSIONS = {
    # Python
    ".py", ".pyw", ".pyi",
    # JavaScript / TypeScript
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    # Web
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".vue", ".svelte",
    # Java / Kotlin / JVM
    ".java", ".kt", ".kts", ".groovy",
    # C / C++
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh",
    # C#
    ".cs",
    # Go / Rust
    ".go", ".rs",
    # PHP / Ruby / Perl
    ".php", ".phtml", ".rb", ".rake", ".pl", ".pm",
    # Swift / Objective-C
    ".swift", ".m", ".mm",
    # Shell
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    # SQL
    ".sql",
    # Data / config
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".conf", ".properties", ".xml",
    # Markdown / text
    ".md", ".markdown", ".txt", ".rst", ".adoc",
    # Docker / misc
    ".dockerfile",
    # Build / config without common extension
    ".gitignore", ".gitattributes", ".editorconfig",
    ".npmrc", ".nvmrc", ".prettierrc", ".eslintrc",
}


# Имена файлов, которые считаем текстовыми даже без обычного расширения.
TEXT_FILENAMES = {
    "Dockerfile",
    "Makefile",
    "CMakeLists.txt",
    "Procfile",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
    "README",
    "README.md",
    "LICENSE",
    "LICENSE.txt",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
}


# Максимальный размер одного файла, который автоматически попадёт
# в итоговый TXT. Большие файлы лучше не отправлять модели целиком.
MAX_FILE_SIZE_MB = 2
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


def is_probably_text_file(path: Path) -> bool:
    """Определяет, можно ли разумно включить файл как текст/код."""
    if path.name in TEXT_FILENAMES:
        return True

    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True

    # Для файлов без расширения проверяем небольшой фрагмент.
    if not path.suffix:
        try:
            sample = path.read_bytes()[:8192]
        except OSError:
            return False

        if b"\x00" in sample:
            return False

        # UTF-8 или простой ASCII — вероятно текст.
        try:
            sample.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False

    return False


def is_ignored_dir(path: Path) -> bool:
    return path.name in DEFAULT_IGNORED_DIRS


def collect_all_paths(root: Path) -> list[Path]:
    """
    Возвращает все доступные файлы и каталоги.
    Игнорируем только служебные/генерируемые папки из списка выше.
    """
    result: list[Path] = []

    def walk(current: Path) -> None:
        try:
            entries = sorted(
                current.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower())
            )
        except OSError:
            return

        for item in entries:
            if item.is_dir():
                if not is_ignored_dir(item):
                    result.append(item)
                    walk(item)
            else:
                result.append(item)

    walk(root)
    return result


def build_tree_text(root: Path, paths: list[Path]) -> str:
    """
    Строит читаемое ASCII-дерево.

    Для дерева используем относительные пути, чтобы итоговый TXT
    не зависел от конкретного абсолютного пути пользователя.
    """
    lines = [f"ROOT: {root.resolve()}", ""]

    # Словарь относительных путей для стабильного построения дерева.
    children: dict[Path, list[Path]] = {}

    for path in paths:
        rel = path.relative_to(root)
        parent = rel.parent
        children.setdefault(parent, []).append(rel)

    def render(parent: Path, prefix: str = "") -> None:
        items = sorted(
            children.get(parent, []),
            key=lambda p: (len(p.parts), p.name.lower())
        )

        # Нам удобнее отрисовать только непосредственных детей.
        direct: list[Path] = []
        for rel in children.get(parent, []):
            if len(rel.parts) == len(parent.parts) + 1:
                direct.append(rel)

        direct.sort(key=lambda p: (not p.name, p.name.lower()))

        for index, rel in enumerate(direct):
            is_last = index == len(direct) - 1
            connector = "└── " if is_last else "├── "
            full = root / rel
            lines.append(prefix + connector + rel.name)

            if full.is_dir():
                extension = "    " if is_last else "│   "
                render(rel, prefix + extension)

    lines.append(root.name + "/")
    render(Path("."), "")

    return "\n".join(lines)


def read_text_file(path: Path) -> tuple[str | None, str | None]:
    """
    Возвращает (текст, ошибка).
    Пытаемся UTF-8, затем UTF-8 с BOM, cp1251 и latin-1.
    """
    try:
        if path.stat().st_size > MAX_FILE_SIZE_BYTES:
            return None, f"Файл слишком большой (> {MAX_FILE_SIZE_MB} MB)"

        raw = path.read_bytes()

        # Бинарные файлы не должны попадать в сборку.
        if b"\x00" in raw[:8192]:
            return None, "Похож на бинарный файл"

        for encoding in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
            try:
                return raw.decode(encoding), None
            except UnicodeDecodeError:
                continue

        return None, "Не удалось декодировать как текст"

    except OSError as exc:
        return None, f"Ошибка чтения: {exc}"


def make_file_header(relative_path: Path) -> str:
    rel = relative_path.as_posix()
    return (
        "\n"
        + "=" * 100
        + "\n"
        + f"FILE: {rel}\n"
        + "=" * 100
        + "\n"
        + f"--- BEGIN FILE: {rel} ---\n"
    )


def make_file_footer(relative_path: Path) -> str:
    rel = relative_path.as_posix()
    return (
        f"\n--- END FILE: {rel} ---\n"
        + "=" * 100
        + "\n"
    )


def format_size(num_bytes: int | float) -> str:
    """Человекочитаемый размер: 1536 -> '1.5 KB'."""
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def build_output(root: Path) -> tuple[str, dict]:
    all_paths = collect_all_paths(root)

    files = [p for p in all_paths if p.is_file()]
    text_files = [
        p for p in files
        if is_probably_text_file(p)
    ]

    tree = build_tree_text(root, all_paths)

    chunks: list[str] = []

    chunks.append("# PROJECT CONTEXT\n")
    chunks.append("Generated by Project Context Builder.\n")
    chunks.append(f"Project root: {root.resolve()}\n")
    chunks.append(
        "The TREE section contains the complete visible directory structure.\n"
    )
    chunks.append(
        "The FILE CONTENTS section contains readable text/code files.\n"
    )
    chunks.append("\n" + "#" * 100 + "\n")
    chunks.append("# FULL DIRECTORY TREE\n")
    chunks.append("#" * 100 + "\n\n")
    chunks.append(tree)

    chunks.append("\n\n" + "#" * 100 + "\n")
    chunks.append("# FILE CONTENTS\n")
    chunks.append("#" * 100 + "\n")

    included = 0
    skipped: list[tuple[str, str]] = []

    for path in sorted(text_files, key=lambda p: p.relative_to(root).as_posix().lower()):
        rel = path.relative_to(root)

        text, error = read_text_file(path)
        if error is not None:
            skipped.append((rel.as_posix(), error))
            continue

        assert text is not None

        chunks.append(make_file_header(rel))
        chunks.append(text.rstrip())
        chunks.append(make_file_footer(rel))
        included += 1

    chunks.append("\n" + "#" * 100 + "\n")
    chunks.append("# COLLECTION SUMMARY\n")
    chunks.append("#" * 100 + "\n")
    chunks.append(f"Total filesystem entries in tree: {len(all_paths)}\n")
    chunks.append(f"Total files: {len(files)}\n")
    chunks.append(f"Recognized text/code files: {len(text_files)}\n")
    chunks.append(f"Included file contents: {included}\n")

    if skipped:
        chunks.append("\nSkipped files:\n")
        for filename, reason in skipped:
            chunks.append(f"- {filename} -> {reason}\n")

    output = "\n".join(chunks)

    stats = {
        "all_entries": len(all_paths),
        "files": len(files),
        "text_files": len(text_files),
        "included": included,
        "skipped": skipped,
        "chars": len(output),
    }

    return output, stats


def choose_directory() -> str:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    selected = filedialog.askdirectory(
        title="Выберите корневой каталог проекта"
    )

    root.destroy()
    return selected


def choose_output_file(initial_dir: Path) -> str:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    selected = filedialog.asksaveasfilename(
        title="Сохранить контекст проекта",
        initialdir=str(initial_dir),
        initialfile=f"{initial_dir.name}_context.txt",
        defaultextension=".txt",
        filetypes=[
            ("Text files", "*.txt"),
            ("All files", "*.*"),
        ],
    )

    root.destroy()
    return selected


def open_folder(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        pass


def main() -> None:
    selected = choose_directory()

    if not selected:
        print("Каталог не выбран.")
        return

    root = Path(selected).resolve()

    try:
        output, stats = build_output(root)
    except Exception as exc:
        messagebox.showerror(
            "Ошибка",
            f"Не удалось собрать проект:\n\n{exc}"
        )
        return

    output_path_str = choose_output_file(root)
    if not output_path_str:
        print("Сохранение отменено.")
        return

    output_path = Path(output_path_str)

    try:
        output_path.write_text(output, encoding="utf-8")
    except OSError as exc:
        messagebox.showerror(
            "Ошибка сохранения",
            f"Не удалось сохранить файл:\n\n{exc}"
        )
        return

    size_kb = output_path.stat().st_size / 1024

    message = (
        "Готово!\n\n"
        f"Файл: {output_path}\n"
        f"Размер: {size_kb:.1f} KB\n\n"
        f"Всего файлов: {stats['files']}\n"
        f"Текстовых/кодовых файлов: {stats['text_files']}\n"
        f"Включено содержимое: {stats['included']}\n"
    )

    if stats["skipped"]:
        message += f"\nПропущено при чтении: {len(stats['skipped'])}"

    messagebox.showinfo("Project Context Builder", message)


if __name__ == "__main__":
    main()
