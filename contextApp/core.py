from __future__ import annotations

import json
import os
import platform
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
    ".svg",
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


# Насколько «тяжёлым» считаем контекст в токенах.
# Типичный лимит одной сессии ChatGPT — 128k токенов,
# но с системным промптом и историей остаётся меньше.
TOKEN_WARNING_THRESHOLD = 100_000


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
    """Грубая проверка: можно ли считать файл текстовым."""
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
    """
    Строит читаемое ASCII-дерево проекта с размерами.

    У файлов — собственный размер. У папок — суммарный размер
    всех файлов внутри (рекурсивно).
    """
    lines = [f"ROOT: {root.resolve()}", ""]

    rel_dirs: set[Path] = set()
    children: dict[Path, list[Path]] = {}
    file_sizes: dict[Path, int] = {}   # полный путь -> размер
    dir_sizes: dict[Path, int] = {}    # полный путь -> суммарный размер

    for path in paths:
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue

        if path.is_dir():
            rel_dirs.add(rel)
        else:
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            file_sizes[path] = size

            # Накручиваем размер на всех предков до корня.
            ancestor = path.parent
            while True:
                dir_sizes[ancestor] = dir_sizes.get(ancestor, 0) + size
                if ancestor == root or ancestor == ancestor.parent:
                    break
                ancestor = ancestor.parent

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

            full = root / rel

            if rel in rel_dirs:
                size = dir_sizes.get(full, 0)
                size_str = f"  [{format_size_short(size)}]"
                lines.append(prefix + connector + rel.name + size_str)
                extension = "    " if is_last else "│   "
                render(rel, prefix + extension)
            else:
                size = file_sizes.get(full)
                size_str = (
                    f"  [{format_size_short(size)}]"
                    if size is not None
                    else ""
                )
                lines.append(prefix + connector + rel.name + size_str)

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

def format_size_short(num_bytes: int | float) -> str:
    """Компактный размер для дерева: '512B', '4.2KB', '1.2MB'."""
    value = float(num_bytes)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)}B"
            return f"{value:.1f}{unit}"
        value /= 1024

    return f"{value:.1f}TB"

def format_tokens(count: int) -> str:
    """'1234' -> '1.2k', '1234567' -> '1.2M'."""
    if count < 1000:
        return str(count)
    if count < 1_000_000:
        return f"{count / 1000:.1f}k"
    return f"{count / 1_000_000:.1f}M"


def estimate_tokens(text: str) -> int:
    """
    Грубая оценка количества токенов.

    Формула эмпирическая:
      - кириллица → ~2.5 символа на токен
      - латиница/цифры/пунктуация → ~4 символа на токен

    Точность ±20%, но для «влезет / не влезет» этого достаточно.
    """
    if not text:
        return 0

    cyrillic = 0
    for ch in text:
        if "\u0400" <= ch <= "\u04FF":
            cyrillic += 1

    other = len(text) - cyrillic
    return int(cyrillic / 2.5 + other / 4.0)


def truncate_text(text: str, max_lines: int) -> tuple[str, int]:
    """
    Обрезает текст до max_lines строк: оставляет по половине
    сверху и снизу, в середине — пометку о пропуске.

    Возвращает (результат, исходное_количество_строк).
    Если строк <= max_lines — возвращает исходный текст без изменений.
    """
    if max_lines <= 0:
        return text, 0

    lines = text.splitlines()

    if len(lines) <= max_lines:
        return text, len(lines)

    head = max_lines // 2
    tail = max_lines - head
    omitted = len(lines) - max_lines

    kept = (
        lines[:head]
        + [f"... [{omitted} lines omitted] ..."]
        + lines[-tail:]
    )
    return "\n".join(kept), len(lines)


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


def list_candidate_files(
    root: Path,
    enabled_categories: dict[str, bool],
    ignored_dirs: set[str],
    ext_filter: set[str] | None = None,
    ext_exclude: bool = False,
    include_env_files: bool = False,
    entries: list[Path] | None = None,
    exclude_paths: set[Path] | None = None,
) -> list[tuple[Path, str]]:
    """
    Возвращает (path, category) для файлов, попадающих в контекст
    при текущих настройках. Содержимое файлов не читается — только
    фильтрация по имени/расширению/категории.

    exclude_paths — пути, которые нужно игнорировать (например,
    сам выходной файл контекста: иначе он попадёт в себя).
    """
    if entries is None:
        entries = collect_all_paths(root, ignored_dirs)

    if exclude_paths:
        resolved: set[Path] = set()
        for p in exclude_paths:
            try:
                resolved.add(p.resolve())
            except OSError:
                continue
        if resolved:
            entries = [
                e for e in entries if e.resolve() not in resolved
            ]

    files = [path for path in entries if path.is_file()]

    if include_env_files:
        excluded_files: set[str] = set()
    else:
        excluded_files = {name.lower() for name in DEFAULT_EXCLUDED_FILES}

    any_category_enabled = any(enabled_categories.values())
    override_mode = (
        bool(ext_filter)
        and not ext_exclude
        and not any_category_enabled
    )

    result: list[tuple[Path, str]] = []

    for path in files:
        if path.name.lower() in excluded_files:
            continue

        name_lower = path.name.lower()
        suffix = path.suffix.lower()

        if ext_filter:
            matched = (
                suffix in ext_filter
                or name_lower in ext_filter
            )

            if ext_exclude:
                if matched:
                    continue
            else:
                if not matched:
                    continue

        file_category = category(path)
        if file_category is None:
            continue

        if override_mode:
            result.append((path, file_category))
            continue

        if not enabled_categories.get(file_category, False):
            continue

        result.append((path, file_category))

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
    file_whitelist: set[Path] | None = None,
    output_path: Path | None = None,
    truncate_long_files: bool = False,
    truncate_max_lines: int = 1000,
) -> tuple[str, dict]:
    """
    Собирает итоговый текст контекста и статистику.

    file_whitelist — необязательный набор абсолютных путей. Если задан,
    в контекст попадут только файлы из него.

    output_path — путь самого выходного файла. Он исключается из скана,
    иначе контекст будет включать сам себя и удваиваться с каждой сборкой.

    truncate_long_files — если True, файлы длиннее truncate_max_lines
    строк обрезаются (половина сверху + половина снизу + пометка).
    """
    entries = collect_all_paths(root, ignored_dirs)

    if output_path is not None:
        try:
            output_resolved = output_path.resolve()
            entries = [
                p for p in entries
                if p.resolve() != output_resolved
            ]
        except OSError:
            pass

    files = [path for path in entries if path.is_file()]

    max_bytes = max(1, int(max_mb * 1024 * 1024))

    candidates = list_candidate_files(
        root=root,
        enabled_categories=enabled_categories,
        ignored_dirs=ignored_dirs,
        ext_filter=ext_filter,
        ext_exclude=ext_exclude,
        include_env_files=include_env_files,
        entries=entries,
    )

    manual_selection_active = file_whitelist is not None
    if file_whitelist is not None:
        candidates = [
            (p, c) for p, c in candidates if p in file_whitelist
        ]

    selected = candidates
    skipped: list[tuple[str, str]] = []

    # Отдельно показываем .env-файлы как пропущенные.
    if not include_env_files:
        excluded_names = {name.lower() for name in DEFAULT_EXCLUDED_FILES}
        for path in files:
            if path.name.lower() in excluded_names:
                rel = path.relative_to(root).as_posix()
                skipped.append(
                    (rel, "Исключён по умолчанию (может содержать секреты)")
                )

    any_category_enabled = any(enabled_categories.values())
    override_mode = (
        bool(ext_filter)
        and not ext_exclude
        and not any_category_enabled
    )

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
    file_sizes: list[tuple[str, int]] = []
    truncated_files: list[tuple[str, int, int]] = []

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

        # Размер исходного файла (до обрезки).
        try:
            original_size = path.stat().st_size
        except OSError:
            original_size = 0

        # Обрезка длинных файлов.
        note_line = ""
        if truncate_long_files and truncate_max_lines > 0:
            text, original_lines = truncate_text(
                text, truncate_max_lines
            )
            if original_lines > truncate_max_lines:
                note_line = (
                    f"NOTE: truncated from {original_lines} "
                    f"to {truncate_max_lines} lines"
                )
                truncated_files.append(
                    (rel, original_lines, truncate_max_lines)
                )

        # Размер того, что реально пойдёт в контекст.
        content_size = len(text.encode("utf-8"))
        file_sizes.append((rel, content_size))

        block = [
            "",
            "=" * 110,
            f"FILE: {rel}",
            f"TYPE: {file_category}",
            f"SIZE: {format_size(original_size)}",
        ]
        if note_line:
            block.append(note_line)
        block += [
            "=" * 110,
            f"--- BEGIN FILE: {rel} ---",
            text.rstrip(),
            f"--- END FILE: {rel} ---",
            "=" * 110,
        ]
        parts += block

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
        (
            "  Truncate long files: "
            f"{'yes, at ' + str(truncate_max_lines) + ' lines' if truncate_long_files else 'no'}"
        ),
    ]

    if ext_filter:
        mode = "EXCLUDE" if ext_exclude else "INCLUDE only"
        parts.append(
            f"  Extension filter ({mode}): "
            f"{', '.join(sorted(ext_filter))}"
        )
        if override_mode:
            parts.append(
                "  Filter override: on "
                "(all categories disabled, filter is the only selector)"
            )
    else:
        parts.append("  Extension filter: off")

    if manual_selection_active:
        parts.append(
            f"  Manual file selection: {len(candidates)} file(s) "
            "(whitelist from file picker)"
        )

    # Считаем размер и токены один раз на финальной строке.
    # Собираем output здесь, чтобы stats были точными, но в файл
    # добавим уже с этими значениями — поэтому сначала строки-заготовки,
    # затем финальный join.
    stats_placeholder = "\n".join(parts)  # временно
    preliminary_size = len(stats_placeholder.encode("utf-8"))
    preliminary_tokens = estimate_tokens(stats_placeholder)

    parts += [
        "",
        "Statistics:",
        f"  Total entries in tree: {len(entries)}",
        f"  Total files: {len(files)}",
        f"  Selected files: {len(selected)}",
        f"  Included contents: {included}",
        f"  Skipped: {len(skipped)}",
        f"  Context size: {format_size(preliminary_size)}",
        f"  Estimated tokens: ~{format_tokens(preliminary_tokens)}",
    ]

    if not include_env_files:
        excluded_names = {name.lower() for name in DEFAULT_EXCLUDED_FILES}
        if excluded_names:
            parts.append(
                "  Excluded by default (secrets): "
                f"{', '.join(sorted(excluded_names))}"
            )


    if truncated_files:
        parts += [
            "",
            "Truncated files:",
        ]
        for name, original, kept in truncated_files:
            parts.append(f"  {name}  ({original} -> {kept} lines)")

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

    # Финальный размер/токены уже по готовому тексту.
    final_size = len(output.encode("utf-8"))
    final_tokens = estimate_tokens(output)

    stats = {
        "entries": len(entries),
        "files": len(files),
        "selected": len(selected),
        "included": included,
        "skipped": skipped,
        "size": final_size,
        "tokens": final_tokens,
        "file_sizes": file_sizes,
        "truncated_files": truncated_files,
    }

    return output, stats


# =====================================================================
# Settings (JSON persistence)
# =====================================================================

SETTINGS_VERSION = 1
MAX_RECENT_PROJECTS = 10


def settings_path() -> Path:
    """Кроссплатформенный путь к файлу настроек."""
    home = Path.home()
    system = platform.system()

    if system == "Windows":
        base = Path(
            os.environ.get("APPDATA", home / "AppData" / "Roaming")
        )
    elif system == "Darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(
            os.environ.get("XDG_CONFIG_HOME", home / ".config")
        )

    return base / "ProjectContextBuilder" / "settings.json"


def default_settings() -> dict:
    """Свежий словарь настроек по умолчанию."""
    return {
        "version": SETTINGS_VERSION,
        "categories": {
            "tree": True,
            "code": True,
            "style": True,
            "config": True,
            "document": True,
            "text": True,
            "data": True,
            "log": True,
            "output_files": False,
            "empty": False,
            "env_files": False,
        },
        "max_mb": "2",
        "excluded_dirs": ", ".join(sorted(DEFAULT_IGNORED_DIRS)),
        "extension_filter": "",
        "extension_exclude": False,
        "truncate_enabled": False,
        "truncate_max_lines": "1000",
        "recent_projects": [],
        "recent_outputs": {},
    }


def load_settings() -> dict:
    """
    Читает настройки из файла.

    При любой ошибке (нет файла, битый JSON, не тот тип) —
    возвращает дефолты. Никогда не бросает исключений.
    """
    path = settings_path()

    if not path.exists():
        return default_settings()

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return default_settings()

    if not isinstance(data, dict):
        return default_settings()

    return _merge_settings(default_settings(), data)


def _merge_settings(defaults: dict, data: dict) -> dict:
    """
    Глубокий merge: если в data чего-то нет, берём из defaults.
    Отсеивает значения очевидно неверного типа.
    """
    result: dict = {}

    for key, default_value in defaults.items():
        if key not in data:
            result[key] = default_value
            continue

        value = data[key]

        if isinstance(default_value, dict):
            if not isinstance(value, dict):
                result[key] = default_value
            elif not default_value:
                result[key] = {
                    k: v for k, v in value.items()
                    if isinstance(k, str) and isinstance(v, str)
                }
            else:
                result[key] = _merge_settings(default_value, value)

        elif isinstance(default_value, list):
            if not isinstance(value, list):
                result[key] = default_value
            else:
                cleaned = [
                    item for item in value
                    if isinstance(item, str) and item.strip()
                ]

                seen: set[str] = set()
                unique: list[str] = []
                for item in cleaned:
                    if item not in seen:
                        seen.add(item)
                        unique.append(item)

                result[key] = unique[:MAX_RECENT_PROJECTS]

        elif isinstance(default_value, bool) and not isinstance(value, bool):
            result[key] = default_value

        elif isinstance(default_value, str) and not isinstance(value, str):
            result[key] = default_value

        else:
            result[key] = value

    return result


def save_settings(data: dict) -> tuple[bool, str | None]:
    """
    Атомарно сохраняет настройки.

    Возвращает (успех, текст ошибки). Никогда не бросает.
    """
    path = settings_path()

    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = json.dumps(data, ensure_ascii=False, indent=2)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)

        return True, None
    except OSError as exc:
        return False, str(exc)