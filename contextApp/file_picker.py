"""Модальное окно для ручного выбора файлов проекта.

Показывает дерево файлов, соответствующих текущим фильтрам,
с чекбоксами для включения/исключения отдельных файлов.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk


CHECKED = "☑"
UNCHECKED = "☐"
FOLDER = "📁"


def _is_descendant(path: Path, folder: Path) -> bool:
    try:
        path.relative_to(folder)
        return True
    except ValueError:
        return False


class FilePickerDialog(tk.Toplevel):
    """Диалог выбора файлов. Результат доступен через .result."""

    def __init__(
        self,
        parent: tk.Misc,
        root: Path,
        candidates: list[tuple[Path, str]],
        preselected: set[Path] | None = None,
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]

        self.title("Выбор файлов")
        self.transient(parent)  # type: ignore[arg-type]
        self.minsize(760, 580)

        self._root = root
        self._candidates: list[Path] = [p for p, _ in candidates]
        self._candidate_set: set[Path] = set(self._candidates)
        self._selected: set[Path] = (
            set(preselected) if preselected is not None
            else set(self._candidates)
        )
        self._selected &= self._candidate_set

        self._item_to_path: dict[str, Path] = {}
        self._dir_items: set[str] = set()

        self._result: set[Path] | None = None
        self._search_after_id: str | None = None

        self._build_ui()
        self._populate_tree()
        self._update_count()

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Escape>", lambda _e: self._on_cancel())

        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - w) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - h) // 3)
        self.geometry(f"+{x}+{y}")

        self.grab_set()
        self.focus_set()

    @property
    def result(self) -> set[Path] | None:
        return self._result

    # ---------- UI ----------

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=12)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text="Выбор файлов для контекста",
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            container,
            text=(
                "По умолчанию выбраны все файлы, соответствующие "
                "текущим фильтрам. Снимите галочки у лишних файлов "
                "или у целых папок."
            ),
            foreground="#666666",
        ).pack(anchor="w", pady=(2, 10))

        search_row = ttk.Frame(container)
        search_row.pack(fill="x", pady=(0, 6))

        ttk.Label(search_row, text="Поиск:").pack(side="left")

        self._search_var = tk.StringVar()
        ttk.Entry(
            search_row,
            textvariable=self._search_var,
        ).pack(side="left", fill="x", expand=True, padx=(6, 6))

        self._search_var.trace_add(
            "write", lambda *_: self._on_search()
        )

        ttk.Button(
            search_row,
            text="Очистить",
            command=lambda: self._search_var.set(""),
        ).pack(side="left")

        tree_frame = ttk.Frame(container)
        tree_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            tree_frame,
            show="tree",
            selectmode="none",
        )
        self.tree.column("#0", width=600, stretch=True)

        tree_scroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        self.tree.bind("<Button-1>", self._on_click)

        bulk = ttk.Frame(container)
        bulk.pack(fill="x", pady=(8, 0))

        ttk.Button(
            bulk,
            text="Выбрать все",
            command=self._select_all,
        ).pack(side="left")

        ttk.Button(
            bulk,
            text="Снять все",
            command=self._select_none,
        ).pack(side="left", padx=(6, 0))

        ttk.Button(
            bulk,
            text="Сбросить к фильтрам",
            command=self._reset_to_filters,
        ).pack(side="left", padx=(6, 0))

        self._count_var = tk.StringVar(value="")
        ttk.Label(
            container,
            textvariable=self._count_var,
            foreground="#333333",
        ).pack(anchor="w", pady=(8, 0))

        bottom = ttk.Frame(container)
        bottom.pack(fill="x", pady=(8, 0))

        ttk.Button(
            bottom,
            text="Отмена",
            command=self._on_cancel,
        ).pack(side="right")

        ttk.Button(
            bottom,
            text="Применить",
            command=self._on_apply,
        ).pack(side="right", padx=(0, 6))

    # ---------- Дерево ----------

    def _populate_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._item_to_path.clear()
        self._dir_items.clear()

        children: dict[Path, list[Path]] = {}
        dir_files: dict[Path, list[Path]] = {}

        for full in self._candidates:
            try:
                rel = full.relative_to(self._root)
            except ValueError:
                continue

            for i in range(1, len(rel.parts) + 1):
                child = Path(*rel.parts[:i])
                parent = (
                    Path(*rel.parts[:i - 1]) if i > 1 else Path(".")
                )
                bucket = children.setdefault(parent, [])
                if child not in bucket:
                    bucket.append(child)

            ancestor = full.parent
            while True:
                dir_files.setdefault(ancestor, []).append(full)
                if ancestor == self._root:
                    break
                if ancestor == ancestor.parent:
                    break
                ancestor = ancestor.parent

        for parent in children:
            children[parent].sort(
                key=lambda p: (
                    not (self._root / p).is_dir(),
                    p.name.lower(),
                )
            )

        query = self._search_var.get().strip().lower()

        def rel_str(p: Path) -> str:
            return str(p).replace("\\", "/").lower()

        def matches(full: Path) -> bool:
            if not query:
                return True
            try:
                rel = full.relative_to(self._root)
            except ValueError:
                return False
            return query in rel_str(rel)

        matching_dirs: set[Path] = set()
        if query:
            for d, descendants in dir_files.items():
                for f in descendants:
                    if matches(f):
                        matching_dirs.add(d)
                        break

        def add(parent_rel: Path, parent_item: str = "") -> None:
            for rel in children.get(parent_rel, []):
                full = self._root / rel
                is_dir = full.is_dir()

                if is_dir:
                    if query and full not in matching_dirs:
                        continue
                    if not dir_files.get(full):
                        continue

                    item = self.tree.insert(
                        parent_item,
                        "end",
                        text=f"{FOLDER} {rel.name}",
                        open=(parent_item == ""),
                    )
                    self._item_to_path[item] = full
                    self._dir_items.add(item)
                    add(rel, item)
                else:
                    if query and not matches(full):
                        continue
                    checked = full in self._selected
                    symbol = CHECKED if checked else UNCHECKED
                    item = self.tree.insert(
                        parent_item,
                        "end",
                        text=f"{symbol} {rel.name}",
                    )
                    self._item_to_path[item] = full

        add(Path("."))

    def _on_search(self) -> None:
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(200, self._rebuild_tree)

    def _rebuild_tree(self) -> None:
        self._search_after_id = None
        self._populate_tree()

    def _refresh_labels(self) -> None:
        for item, path in self._item_to_path.items():
            if item in self._dir_items:
                continue
            try:
                rel = path.relative_to(self._root)
            except ValueError:
                continue
            checked = path in self._selected
            symbol = CHECKED if checked else UNCHECKED
            self.tree.item(item, text=f"{symbol} {rel.name}")
        self._update_count()

    def _update_count(self) -> None:
        total = len(self._candidates)
        chosen = len(self._selected & self._candidate_set)
        self._count_var.set(f"Выбрано файлов: {chosen} из {total}")

    def _toggle_item(self, item: str) -> None:
        path = self._item_to_path.get(item)
        if path is None:
            return

        if item in self._dir_items:
            descendants = [
                p for p in self._candidates if _is_descendant(p, path)
            ]
            if not descendants:
                return
            all_on = all(p in self._selected for p in descendants)
            for p in descendants:
                if all_on:
                    self._selected.discard(p)
                else:
                    self._selected.add(p)
        else:
            if path in self._selected:
                self._selected.discard(path)
            else:
                self._selected.add(path)

        self._refresh_labels()

    def _on_click(self, event) -> None:
        element = self.tree.identify_element(event.x, event.y)
        if element and "indicator" in element:
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        self._toggle_item(item)

    # ---------- Действия ----------

    def _select_all(self) -> None:
        self._selected = set(self._candidates)
        self._refresh_labels()

    def _select_none(self) -> None:
        self._selected = set()
        self._refresh_labels()

    def _reset_to_filters(self) -> None:
        self._selected = set(self._candidates)
        self._refresh_labels()

    def _on_apply(self) -> None:
        self._result = set(self._selected & self._candidate_set)
        self.destroy()

    def _on_cancel(self) -> None:
        self._result = None
        self.destroy()


def pick_files(
    parent: tk.Misc,
    root: Path,
    candidates: list[tuple[Path, str]],
    preselected: set[Path] | None = None,
) -> set[Path] | None:
    """Открывает диалог и возвращает выбранные пути (или None)."""
    dialog = FilePickerDialog(parent, root, candidates, preselected)
    parent.wait_window(dialog)
    return dialog.result