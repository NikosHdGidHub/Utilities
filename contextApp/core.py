from __future__ import annotations

from pathlib import Path

# Папки, которые обычно не нужны в контексте проекта.
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

CODE_EXTENSIONS = {
    ".py", ".pyw", ".pyi",
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".vue", ".svelte",
    ".java", ".kt", ".kts", ".groovy",
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh",
    ".cs",
    ".go", ".rs",
    ".php", ".phtml", ".rb", ".rake", ".pl", ".pm",
    ".swift", ".m", ".mm",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    ".sql",
}

CONFIG_EXTENSIONS = {
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".conf", ".properties", ".xml", ".env",
}

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".adoc", ".log", ".csv"
}

DOCUMENT_NAMES = {
    "README", "README.md", "README.txt",
    "LICENSE", "LICENSE.txt"
}

OUTPUT_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock"
}

SPECIAL_CODE_NAMES = {
    "Dockerfile", "Makefile", "CMakeLists.txt", "Procfile"
}


def category(path: Path) -> str | None:
    """Определяет категорию файла для фильтрации в GUI."""
    name = path.name
    suffix = path.suffix.lower()

    if name in SPECIAL_CODE_NAMES or suffix in CODE_EXTENSIONS:
        return "code"

    if suffix in CONFIG_EXTENSIONS:
        return "config"

    if name in DOCUMENT_NAMES:
        return "document"

    if name in OUTPUT_NAMES:
        return "output"

    if suffix in TEXT_EXTENSIONS:
        return "text"

    if is_probably_text_file(path):
        return "text"

    return None


def is_probably_text_file(path: Path) -> bool:
    """Грубая проверка: можно ли считать файл текстовым."""
    if path.name in DOCUMENT_NAMES or path.name in OUTPUT_NAMES:
        return True

    if path.name in SPECIAL_CODE_NAMES:
        return True

    if path.suffix.lower() in (
        CODE_EXTENSIONS | CONFIG_EXTENSIONS | TEXT_EXTENSIONS
    ):
        return True

    if not path.suffix:
        try:
            with path.open("rb") as f:
                sample = f.read(8192)
        except OSError:
            return False

        # Именно нулевой байт, а не литерал "\x00" из четырёх символов.
        if b"\x00" in sample:
            return False

        try:
            sample.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False

    return False


def collect_all_paths(
    root: Path,
    ignored_dirs: set[str] | None = None,
) -> list[Path]:
    """Возвращает все доступные файлы и каталоги, кроме исключённых папок."""
    ignored = {
        item.lower()
        for item in (
            ignored_dirs if ignored_dirs is not None else DEFAULT_IGNORED_DIRS
        )
    }

    result: list[Path] = []

    def walk(current: Path) -> None:
        try:
            entries = sorted(
                current.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except OSError:
            return

        for item in entries:
            if item.is_dir():
                if item.name.lower() in ignored:
                    continue
                result.append(item)
                walk(item)
            else:
                result.append(item)

    walk(root)
    return result


def build_tree_text(root: Path, paths: list[Path]) -> str:
    """Строит читаемое ASCII-дерево проекта."""
    lines = [f"ROOT: {root.resolve()}", ""]

    rel_dirs: set[Path] = set()
    children: dict[Path, list[Path]] = {}

    for path in paths:
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue

        if path.is_dir():
            rel_dirs.add(rel)

        children.setdefault(rel.parent, []).append(rel)

    def render(parent: Path, prefix: str = "") -> None:
        direct = [
            rel for rel in children.get(parent, [])
            if len(rel.parts) == len(parent.parts) + 1
        ]
        direct.sort(key=lambda p: (p not in rel_dirs, p.name.lower()))

        for index, rel in enumerate(direct):
            is_last = index == len(direct) - 1
            connector = "└── " if is_last else "├── "

            lines.append(prefix + connector + rel.name)

            if rel in rel_dirs:
                extension = "    " if is_last else "│   "
                render(rel, prefix + extension)

    lines.append(root.name + "/")
    render(Path("."), "")

    return "\n".join(lines)


def format_size(num_bytes: int | float) -> str:
    """Человекочитаемый размер."""
    value = float(num_bytes)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024

    return f"{value:.1f} TB"


def read_text_file(
    path: Path,
    max_bytes: int | None = None,
) -> tuple[str | None, str | None]:
    """
    Возвращает (текст, ошибка).

    Сначала проверяет «шапку» файла на нуль-байт, потом читает целиком
    и пытается декодировать в нескольких кодировках.
    """
    try:
        file_size = path.stat().st_size

        if max_bytes is not None and file_size > max_bytes:
            max_mb = max_bytes / (1024 * 1024)
            return None, f"Файл слишком большой (> {max_mb:.2f} MB)"

        with path.open("rb") as handle:
            head = handle.read(8192)

            # Проверяем первые 8 КБ на нуль-байт (признак бинарника).
            if b"\x00" in head:
                return None, "Похож на бинарный файл"

            raw = head + handle.read()

        for encoding in ("utf-8", "utf-8-sig", "cp1251"):
            try:
                return raw.decode(encoding), None
            except UnicodeDecodeError:
                continue

        # Последняя попытка: декодируем с заменами и оцениваем качество.
        decoded = raw.decode("utf-8", errors="replace")

        if decoded:
            bad_ratio = decoded.count("\ufffd") / len(decoded)
            if bad_ratio > 0.05:
                return None, "Похож на бинарный файл"

        return decoded, None

    except OSError as exc:
        return None, f"Ошибка чтения: {exc}"


def parse_exclusions(text: str) -> set[str]:
    """Преобразует строку со списком каталогов в set."""
    result = set()

    for item in text.replace(";", ",").replace("\n", ",").split(","):
        item = item.strip().lower()
        if item:
            result.add(item)

    return result


def parse_extensions(text: str) -> set[str]:
    """Парсит строку расширений: 'css, html js' -> {'.css', '.html', '.js'}."""
    result: set[str] = set()

    normalized = (
        text.replace(";", ",")
        .replace("\n", ",")
        .replace("\t", ",")
        .replace(" ", ",")
    )

    for item in normalized.split(","):
        item = item.strip().lower()

        if not item:
            continue

        if not item.startswith("."):
            item = "." + item

        result.add(item)

    return result


def build_context(
    root: Path,
    include_tree: bool,
    enabled_categories: dict[str, bool],
    include_empty: bool,
    max_mb: float,
    ignored_dirs: set[str],
    ext_filter: set[str] | None = None,
    ext_exclude: bool = False,
) -> tuple[str, dict]:
    """
    Собирает итоговый текст контекста и статистику.

    Фильтр категорий и фильтр расширений применяются вместе:
    файл должен подойти И по категории, И по расширению.
    """
    entries = collect_all_paths(root, ignored_dirs)
    files = [path for path in entries if path.is_file()]

    max_bytes = max(1, int(max_mb * 1024 * 1024))

    selected: list[tuple[Path, str]] = []

    for path in files:
        suffix = path.suffix.lower()

        # 1. Фильтр по расширениям (если задан).
        if ext_filter:
            if ext_exclude:
                if suffix in ext_filter:
                    continue
            else:
                if suffix not in ext_filter:
                    continue

        # 2. Фильтр по категориям.
        file_category = category(path)
        if file_category is None:
            continue

        if not enabled_categories.get(file_category, False):
            continue

        selected.append((path, file_category))

    parts = [
        "# PROJECT CONTEXT",
        "",
        "Generated by Project Context Builder.",
        f"Project root: {root.resolve()}",
    ]

    if include_tree:
        tree = build_tree_text(root, entries)
        parts += [
            "",
            "#" * 110,
            "# FULL DIRECTORY TREE",
            "#" * 110,
            "",
            tree,
        ]

    parts += [
        "",
        "#" * 110,
        "# FILE CONTENTS",
        "#" * 110,
    ]

    included = 0
    skipped: list[tuple[str, str]] = []

    for path, file_category in sorted(
        selected,
        key=lambda item: item[0].relative_to(root).as_posix().lower(),
    ):
        relative_path = path.relative_to(root)

        text, error = read_text_file(path, max_bytes=max_bytes)

        if error is not None:
            skipped.append((relative_path.as_posix(), error))
            continue

        if text is None:
            skipped.append((relative_path.as_posix(), "Ошибка чтения"))
            continue

        if not include_empty and not text.strip():
            skipped.append((relative_path.as_posix(), "Пустой файл"))
            continue

        rel = relative_path.as_posix()

        parts += [
            "",
            "=" * 110,
            f"FILE: {rel}",
            f"TYPE: {file_category}",
            "=" * 110,
            f"--- BEGIN FILE: {rel} ---",
            text.rstrip(),
            f"--- END FILE: {rel} ---",
            "=" * 110,
        ]

        included += 1

    parts += [
        "",
        "#" * 110,
        "# COLLECTION SUMMARY",
        "#" * 110,
        f"Total entries in tree: {len(entries)}",
        f"Total files: {len(files)}",
        f"Selected files: {len(selected)}",
        f"Included contents: {included}",
        f"Skipped: {len(skipped)}",
    ]

    if ext_filter:
        mode = "EXCLUDE" if ext_exclude else "INCLUDE only"
        parts.append(
            f"Extension filter ({mode}): {', '.join(sorted(ext_filter))}"
        )

    if skipped:
        parts += [
            "",
            "Skipped files:",
        ]
        parts += [
            f"- {name} -> {reason}"
            for name, reason in skipped
        ]

    output = "\n".join(parts)

    stats = {
        "entries": len(entries),
        "files": len(files),
        "selected": len(selected),
        "included": included,
        "skipped": skipped,
        "size": len(output.encode("utf-8")),
    }

    return output, stats