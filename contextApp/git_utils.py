"""Утилиты для работы с git: получение списка изменённых файлов.

Используется фильтром «Только изменённые» в GUI. Все команды
выполняются через subprocess с флагом -C <root>, так что исходный
проект может быть подкаталогом git-репозитория.
"""

from __future__ import annotations

import subprocess
from datetime import date, datetime, time, timedelta
from pathlib import Path


MODE_OFF = "off"
MODE_UNCOMMITTED = "uncommitted"
MODE_SINCE_LAST_COMMIT = "since_last_commit"
MODE_LAST_2_COMMITS = "last_2_commits"
MODE_YESTERDAY = "yesterday"
MODE_DAY_BEFORE_YESTERDAY = "day_before_yesterday"

ALL_MODES = (
    MODE_OFF,
    MODE_UNCOMMITTED,
    MODE_SINCE_LAST_COMMIT,
    MODE_LAST_2_COMMITS,
    MODE_YESTERDAY,
    MODE_DAY_BEFORE_YESTERDAY,
)


def _run_git(
    root: Path,
    args: list[str],
    timeout: int = 15,
) -> tuple[bool, str]:
    """
    Запускает git-команду в каталоге root.

    Возвращает (ok, output_or_error). Никогда не бросает.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C", str(root),
                "-c", "core.quotepath=false",
                *args,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)

    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip()
    return True, result.stdout


def get_repo_root(path: Path) -> Path | None:
    """Возвращает корень git-репозитория для указанного пути или None."""
    ok, output = _run_git(path, ["rev-parse", "--show-toplevel"])
    if not ok:
        return None
    p = Path(output.strip())
    if not p.is_dir():
        return None
    return p


def _resolve_files(repo_root: Path, rel_paths: list[str]) -> set[Path]:
    """Преобразует относительные пути (от repo_root) в существующие файлы."""
    result: set[Path] = set()
    for rel in rel_paths:
        rel = rel.strip()
        if not rel:
            continue
        full = repo_root / rel
        try:
            if full.is_file():
                result.add(full)
        except OSError:
            continue
    return result


def _files_uncommitted(root: Path, repo_root: Path) -> set[Path]:
    """Изменённые файлы, которые ещё не в коммите."""
    ok, output = _run_git(root, [
        "status",
        "--porcelain",
        "-z",
        "--untracked-files=all",
        "--no-renames",
    ])
    if not ok:
        return set()

    paths: list[str] = []
    for entry in output.split("\0"):
        if len(entry) < 4:
            continue
        status = entry[:2]
        if "D" in status:
            continue
        paths.append(entry[3:])

    return _resolve_files(repo_root, paths)


def _files_since_last_commit(root: Path, repo_root: Path) -> set[Path]:
    """Файлы, изменённые с HEAD: staged + unstaged + untracked."""
    result: set[Path] = set()

    ok, output = _run_git(root, [
        "diff", "--name-only", "--no-renames", "HEAD",
    ])
    if ok:
        result |= _resolve_files(repo_root, output.splitlines())

    ok, output = _run_git(root, [
        "ls-files", "--others", "--exclude-standard",
    ])
    if ok:
        result |= _resolve_files(repo_root, output.splitlines())

    return result


def _files_last_2_commits(root: Path, repo_root: Path) -> set[Path]:
    """Файлы, изменённые в последних двух коммитах."""
    ok, output = _run_git(root, [
        "diff", "--name-only", "--no-renames", "HEAD~2", "HEAD",
    ])
    if ok:
        return _resolve_files(repo_root, output.splitlines())

    empty_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    ok, output = _run_git(root, [
        "diff", "--name-only", "--no-renames", empty_tree, "HEAD",
    ])
    if ok:
        return _resolve_files(repo_root, output.splitlines())

    return set()


def _files_by_dates(
    root: Path,
    repo_root: Path,
    since: datetime,
    until: datetime,
) -> set[Path]:
    """Файлы, упомянутые в коммитах в диапазоне дат."""
    ok, output = _run_git(root, [
        "log",
        f"--since={since.isoformat(sep=' ')}",
        f"--until={until.isoformat(sep=' ')}",
        "--name-only",
        "--pretty=format:",
        "--no-renames",
    ])
    if not ok:
        return set()

    paths = [line for line in output.splitlines() if line.strip()]
    return _resolve_files(repo_root, paths)


def get_changed_files(root: Path, mode: str) -> set[Path] | None:
    """
    Возвращает набор абсолютных путей изменённых файлов.

    None — фильтр выключен (mode == "off").
    set() — фильтр включён, но ничего не найдено или проект не git.
    """
    if mode == MODE_OFF:
        return None

    repo_root = get_repo_root(root)
    if repo_root is None:
        return set()

    if mode == MODE_UNCOMMITTED:
        return _files_uncommitted(root, repo_root)

    if mode == MODE_SINCE_LAST_COMMIT:
        return _files_since_last_commit(root, repo_root)

    if mode == MODE_LAST_2_COMMITS:
        return _files_last_2_commits(root, repo_root)

    if mode == MODE_YESTERDAY:
        today = date.today()
        yesterday = today - timedelta(days=1)
        since = datetime.combine(yesterday, time(0, 0, 0))
        until = datetime.combine(yesterday, time(23, 59, 59))
        return _files_by_dates(root, repo_root, since, until)

    if mode == MODE_DAY_BEFORE_YESTERDAY:
        today = date.today()
        day = today - timedelta(days=2)
        since = datetime.combine(day, time(0, 0, 0))
        until = datetime.combine(day, time(23, 59, 59))
        return _files_by_dates(root, repo_root, since, until)

    return None