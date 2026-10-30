"""Утилиты для работы с git: получение списка изменённых файлов.

Используется фильтром «Только изменённые» в GUI. Все команды
выполняются через subprocess с флагом -C <root>, так что исходный
проект может быть подкаталогом git-репозитория.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path


MODE_OFF = "off"
MODE_UNCOMMITTED = "uncommitted"
MODE_SINCE_COMMIT = "since_commit"

ALL_MODES = (MODE_OFF, MODE_UNCOMMITTED, MODE_SINCE_COMMIT)


def _run_git(
    root: Path,
    args: list[str],
    timeout: int = 15,
) -> tuple[bool, str]:
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
    ok, output = _run_git(path, ["rev-parse", "--show-toplevel"])
    if not ok:
        return None
    p = Path(output.strip())
    if not p.is_dir():
        return None
    return p


def _resolve_files(repo_root: Path, rel_paths: list[str]) -> set[Path]:
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


def _files_since_commit(
    root: Path,
    repo_root: Path,
    commit_hash: str,
) -> set[Path]:
    """Файлы, изменённые между <commit>^ и HEAD (включая сам коммит)."""
    ok, output = _run_git(root, [
        "diff", "--name-only", "--no-renames",
        f"{commit_hash}^..HEAD",
    ])
    if ok:
        return _resolve_files(repo_root, output.splitlines())

    # Первый коммит в репозитории — родителя нет, берём пустое дерево.
    empty_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    ok, output = _run_git(root, [
        "diff", "--name-only", "--no-renames",
        empty_tree, "HEAD",
    ])
    if ok:
        return _resolve_files(repo_root, output.splitlines())

    return set()


def get_changed_files(
    root: Path,
    mode: str,
    commit_hash: str | None = None,
) -> set[Path] | None:
    """None — фильтр выключен. set() — включён, но ничего не нашли."""
    if mode == MODE_OFF:
        return None

    repo_root = get_repo_root(root)
    if repo_root is None:
        return set()

    if mode == MODE_UNCOMMITTED:
        return _files_uncommitted(root, repo_root)

    if mode == MODE_SINCE_COMMIT:
        if not commit_hash:
            return set()
        return _files_since_commit(root, repo_root, commit_hash)

    return None


# ---------- Список последних коммитов для выпадающего списка ----------

def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


def _relative_time(timestamp: int) -> str:
    if timestamp <= 0:
        return "?"
    diff = int(time.time()) - timestamp
    if diff < 0:
        diff = 0
    if diff < 60:
        return "только что"
    if diff < 3600:
        return f"{diff // 60} мин назад"
    if diff < 86400:
        return f"{diff // 3600} ч назад"
    if diff < 86400 * 30:
        return f"{diff // 86400} дн назад"
    if diff < 86400 * 365:
        return f"{diff // (86400 * 30)} мес назад"
    return f"{diff // (86400 * 365)} г назад"


def get_recent_commits(root: Path, limit: int = 15) -> list[dict]:
    """Последние limit коммитов.

    Каждый элемент: {hash, short_hash, subject, timestamp, label}.
    label = "<subject[:48]> · <относительное время>".
    """
    ok, output = _run_git(root, [
        "log",
        f"-n{limit}",
        "--pretty=format:%H%x00%h%x00%s%x00%ct",
    ])
    if not ok:
        return []

    commits: list[dict] = []
    for line in output.splitlines():
        parts = line.split(chr(0))
        if len(parts) != 4:
            continue
        full_hash, short_hash, subject, ct_str = parts
        try:
            timestamp = int(ct_str)
        except ValueError:
            timestamp = 0
        commits.append({
            "hash": full_hash,
            "short_hash": short_hash,
            "subject": subject,
            "timestamp": timestamp,
            "label": f"{_truncate(subject, 48)} · {_relative_time(timestamp)}",
        })
    return commits