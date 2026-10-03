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

# Файлы, которые исключаются по умолчанию (могут содержать секреты).
DEFAULT_EXCLUDED_FILES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.staging",
    ".env.test",
    ".env.ci",
}

CODE_EXTENSIONS = {
    ".py", ".pyw", ".pyi",
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    ".html", ".htm",
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

STYLE_EXTENSIONS = {
    ".css", ".scss", ".sass", ".less", ".styl",
    ".svg",  # SVG — текстовый векторный формат, часто идёт рядом со стилями
}

# Дополнительные расширения кода — часто встречаются, но не в основных наборах.
EXTRA_CODE_EXTENSIONS = {
    ".spec",     # PyInstaller (это Python-код)
    ".gradle",   # Gradle
    ".cmake",    # CMake
    ".mk",       # Makefile-фрагменты
}

CONFIG_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".conf", ".properties", ".xml",
}

EXTRA_CONFIG_EXTENSIONS = {
    ".tmpl",
    ".template",
}

# Dot-файлы конфигурации — у большинства нет расширения.
DOTFILE_CONFIG_NAMES = {
    ".gitignore", ".gitattributes", ".dockerignore", ".npmignore",
    ".editorconfig", ".npmrc", ".nvmrc", ".yarnrc",
    ".prettierrc", ".prettierignore",
    ".eslintrc", ".eslintignore",
    ".babelrc", ".browserslistrc",
    ".flake8", ".pylintrc", ".isort.cfg",
    ".rubocop.yml",
    ".clang-format",
}

# Документация.
DOCUMENT_EXTENSIONS = {
    ".md", ".markdown", ".rst", ".adoc",
}

DOCUMENT_NAMES = {
    "README", "README.md", "README.txt",
    "LICENSE", "LICENSE.txt",
}

# Простой текст.
TEXT_EXTENSIONS = {
    ".txt",
}

# Данные — «плоские» табличные и построчные форматы.
DATA_EXTENSIONS = {
    ".csv", ".tsv", ".jsonl", ".ndjson",
}

# Логи.
LOG_EXTENSIONS = {
    ".log",
}

OUTPUT_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock",
}

SPECIAL_CODE_NAMES = {
    "Dockerfile", "Makefile", "CMakeLists.txt", "Procfile",
}

# Человекочитаемые ярлыки категорий для COLLECTION SUMMARY.
# Английский — потому что контекст читает ChatGPT, ему так проще.
CATEGORY_LABELS = {
    "code": "Code (.py, .js, .ts, .go, .rs, ...)",
    "style": "Styles (.css, .scss, .less, .svg)",
    "config": "Configs (.json, .yaml, .toml, .ini, .gitignore)",
    "document": "Documentation (.md, README, LICENSE)",
    "text": "Text (.txt)",
    "data": "Data (.csv, .tsv, .jsonl)",
    "log": "Logs (.log)",
    "output": "Lock files (package-lock.json, poetry.lock, ...)",
}


def _is_env_like(name: str) -> bool:
    """'.env' или '.env.local' / '.env.production' и т.п."""
    lower = name.lower()
    return lower == ".env" or lower.startswith(".env.")


def category(path: Path) -> str | None:
    """Определяет категорию файла для фильтрации в GUI."""
    name = path.name
    suffix = path.suffix.lower()

    # .env* — конфигурация. Отдельное исключение делается в build_context.
    if _is_env_like(name):
        return "config"

    if (
        name in SPECIAL_CODE_NAMES
        or suffix in CODE_EXTENSIONS
        or suffix in EXTRA_CODE_EXTENSIONS
    ):
        return "code"

    if suffix in STYLE_EXTENSIONS:
        return "style"

    if (
        name in DOTFILE_CONFIG_NAMES
        or suffix in CONFIG_EXTENSIONS
        or suffix in EXTRA_CONFIG_EXTENSIONS
    ):
        return "config"

    if name in DOCUMENT_NAMES or suffix in DOCUMENT_EXTENSIONS:
        return "document"

    if name in OUTPUT_NAMES:
        return "output"

    if suffix in TEXT_EXTENSIONS:
        return "text"

    if suffix in DATA_EXTENSIONS:
        return "data"

    if suffix in LOG_EXTENSIONS:
        return "log"

    if is_probably_text_file(path):
        return "text"

    return None


def is_probably_text_file(path: Path) -> bool:
    """
    Грубая проверка: можно ли считать файл текстовым.

    Для известных расширений сразу True. Для всех остальных —
    читаем «шапку» файла.
    """
    name = path.name

    if (
        name in DOCUMENT_NAMES
        or name in OUTPUT_NAMES
        or name in SPECIAL_CODE_NAMES
        or name in DOTFILE_CONFIG_NAMES
    ):
        return True

    if _is_env_like(name):
        return True

    suffix = path.suffix.lower()

    if suffix in (
        CODE_EXTENSIONS
        | STYLE_EXTENSIONS
        | CONFIG_EXTENSIONS
        | DOCUMENT_EXTENSIONS
        | TEXT_EXTENSIONS
        | DATA_EXTENSIONS
        | LOG_EXTENSIONS
        | EXTRA_CODE_EXTENSIONS
        | EXTRA_CONFIG_EXTENSIONS
    ):
        return True

    try:
        with path.open("rb") as f:
            sample = f.read(8192)
    except OSError:
        return False

    if b"\x00" in sample:
        return False

    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
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

            if b"\x00" in head:
                return None, "Похож на бинарный файл"

            raw = head + handle.read()

        for encoding in ("utf-8", "utf-8-sig", "cp1251"):
            try:
                return raw.decode(encoding), None
            except UnicodeDecodeError:
                continue

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
    include_env_files: bool = False,
) -> tuple[str, dict]:
    """
    Собирает итоговый текст контекста и статистику.

    Фильтр категорий и фильтр расширений применяются вместе:
    файл должен подойти И по категории, И по расширению.

    Файлы из DEFAULT_EXCLUDED_FILES (в первую очередь .env*) не попадают
    в контекст, если include_env_files=False.
    """
    entries = collect_all_paths(root, ignored_dirs)
    files = [path for path in entries if path.is_file()]

    max_bytes = max(1, int(max_mb * 1024 * 1024))

    if include_env_files:
        excluded_files: set[str] = set()
    else:
        excluded_files = {name.lower() for name in DEFAULT_EXCLUDED_FILES}

    selected: list[tuple[Path, str]] = []
    skipped: list[tuple[str, str]] = []

    for path in files:
        relative = path.relative_to(root).as_posix()

        if path.name.lower() in excluded_files:
            skipped.append(
                (relative, "Исключён по умолчанию (может содержать секреты)")
            )
            continue

        suffix = path.suffix.lower()

        if ext_filter:
            if ext_exclude:
                if suffix in ext_filter:
                    continue
            else:
                if suffix not in ext_filter:
                    continue

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

    # ---------------- COLLECTION SUMMARY ----------------
    parts += [
        "",
        "#" * 110,
        "# COLLECTION SUMMARY",
        "#" * 110,
        "",
        "Settings:",
        f"  Directory tree: {'yes' if include_tree else 'no'}",
    ]

    for key, label in CATEGORY_LABELS.items():
        enabled = enabled_categories.get(key, False)
        parts.append(f"  {label}: {'yes' if enabled else 'no'}")

    parts += [
        f"  Empty files: {'yes' if include_empty else 'no'}",
        f"  .env files (secrets!): {'yes' if include_env_files else 'no'}",
        f"  Max file size: {max_mb:g} MB",
    ]

    if ext_filter:
        mode = "EXCLUDE" if ext_exclude else "INCLUDE only"
        parts.append(
            f"  Extension filter ({mode}): "
            f"{', '.join(sorted(ext_filter))}"
        )
    else:
        parts.append("  Extension filter: off")

    parts += [
        "",
        "Statistics:",
        f"  Total entries in tree: {len(entries)}",
        f"  Total files: {len(files)}",
        f"  Selected files: {len(selected)}",
        f"  Included contents: {included}",
        f"  Skipped: {len(skipped)}",
    ]

    if not include_env_files and excluded_files:
        parts.append(
            f"  Excluded by default (secrets): "
            f"{', '.join(sorted(excluded_files))}"
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