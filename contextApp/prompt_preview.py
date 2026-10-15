"""Модальное окно предпросмотра промпта.

Показывает, что попадёт в блок USER TASK при текущих галочках
в Prompt.md. Файл автоматически перечитывается, если он менялся
(по mtime) — удобно держать окно открытым и править Prompt.md
в редакторе.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable

import core


# Интервал опроса mtime файла (мс).
POLL_INTERVAL_MS = 1500


class PromptPreviewDialog(tk.Toplevel):
    """Диалог предпросмотра промпта. Модальный, закрывается по Esc."""

    def __init__(
        self,
        parent: tk.Misc,
        prompt_path: Path,
        on_open_editor: Callable[[], object] | None = None,
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]

        self.title("Предпросмотр промпта")
        self.transient(parent)  # type: ignore[arg-type]
        self.minsize(760, 560)

        self._path = prompt_path
        self._on_open_editor = on_open_editor
        self._poll_id: str | None = None
        self._last_mtime: float | None = None

        self._build_ui()
        self._refresh()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda _e: self._on_close())

        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - w) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - h) // 3)
        self.geometry(f"+{x}+{y}")

        self.grab_set()
        self.focus_set()
        self._schedule_poll()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=12)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text="Предпросмотр промпта",
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            container,
            text=(
                "Этот текст будет вставлен в начало контекста как блок "
                "USER TASK. Если файл изменится в редакторе, окно "
                "обновится автоматически."
            ),
            foreground="#666666",
        ).pack(anchor="w", pady=(2, 10))

        self._stats_var = tk.StringVar(value="")
        ttk.Label(
            container,
            textvariable=self._stats_var,
            foreground="#666666",
        ).pack(anchor="w", pady=(0, 6))

        self._text = ScrolledText(
            container,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
        )
        self._text.pack(fill="both", expand=True)

        bottom = ttk.Frame(container)
        bottom.pack(fill="x", pady=(10, 0))

        if self._on_open_editor is not None:
            ttk.Button(
                bottom,
                text="📝 Открыть в редакторе",
                command=self._on_open_editor,
            ).pack(side="left")

        ttk.Button(
            bottom,
            text="🔄 Обновить",
            command=self._refresh,
        ).pack(side="left", padx=(6, 0))

        ttk.Button(
            bottom,
            text="Закрыть",
            command=self._on_close,
        ).pack(side="right")

    # ---------- Логика ----------

    def _refresh(self) -> None:
        # Запоминаем mtime, чтобы поллинг не дёргал refresh зря.
        try:
            self._last_mtime = self._path.stat().st_mtime
        except OSError:
            self._last_mtime = None

        if not self._path.exists():
            self._set_text("Файл Prompt.md не найден.")
            self._stats_var.set("")
            return

        text, stats = core.parse_prompt_file(self._path)

        if stats.get("error"):
            self._set_text(
                "Не удалось прочитать файл Prompt.md — "
                "проверь кодировку (ожидается UTF-8)."
            )
            self._stats_var.set("")
            return

        if not text.strip():
            self._set_text(
                "Промпт пуст — в Prompt.md не отмечено ни одного пункта.\n\n"
                "Открой файл в редакторе и поставь галочки у нужных строк."
            )
        else:
            self._set_text(text)

        found = [
            name
            for name in ("HEADER", "QUESTS", "FREE", "QUESTIONS")
            if stats["sections"].get(name)
        ]
        sections_str = " / ".join(found) if found else "—"

        self._stats_var.set(
            f"Активных: {stats['active']}  •  "
            f"Снятых: {stats['skipped']}  •  "
            f"Секции: {sections_str}"
        )

    def _set_text(self, content: str) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", content)
        self._text.configure(state="disabled")

    # ---------- Поллинг mtime ----------

    def _schedule_poll(self) -> None:
        self._poll_id = self.after(POLL_INTERVAL_MS, self._poll)

    def _poll(self) -> None:
        self._poll_id = None

        try:
            mtime = self._path.stat().st_mtime
        except OSError:
            mtime = None

        if mtime != self._last_mtime:
            self._refresh()

        self._schedule_poll()

    def _on_close(self) -> None:
        if self._poll_id is not None:
            try:
                self.after_cancel(self._poll_id)
            except tk.TclError:
                pass
            self._poll_id = None
        self.destroy()


def show_preview(
    parent: tk.Misc,
    prompt_path: Path,
    on_open_editor: Callable[[], object] | None = None,
) -> None:
    """Открывает модальный предпросмотр и ждёт закрытия."""
    dialog = PromptPreviewDialog(parent, prompt_path, on_open_editor)
    parent.wait_window(dialog)