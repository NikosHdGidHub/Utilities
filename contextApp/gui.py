from __future__ import annotations

import os
import platform
import subprocess
import prompt_preview
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import core
import file_picker
import git_utils

APP_TITLE = "Project Context Builder"

QUICK_EXTENSIONS = (
    ".css",
    ".html",
    ".js",
    ".md",
    ".txt",
    ".py",
    ".json",
)

# Статические режимы фильтра «только изменённые»: (ключ, метка).
# Коммиты добавляются динамически в выпадающий список.
CHANGED_MODES_STATIC: tuple[tuple[str, str], ...] = (
    ("off", "Выключено"),
    ("uncommitted", "Незакоммиченные"),
)

CHANGED_KEY_TO_LABEL = {key: label for key, label in CHANGED_MODES_STATIC}
CHANGED_LABEL_TO_KEY = {label: key for key, label in CHANGED_MODES_STATIC}

# Задержка автосохранения настроек после последнего изменения.
AUTOSAVE_DELAY_MS = 1500


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title(APP_TITLE)
        self.geometry("1000x720")
        self.minsize(900, 640)

        self.context = ""
        self._advanced_window: tk.Toplevel | None = None
        self._autosave_after_id: str | None = None

        # Настройки читаем ДО создания переменных — чтобы сразу
        # подставить сохранённые значения.
        settings = core.load_settings()
        cats = settings.get("categories") or {}

        self._initial_prompt_attach = bool(
            settings.get("prompt_attach_enabled", False)
        )

        self.root_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.max_var = tk.StringVar(
            value=str(settings.get("max_mb", "2"))
        )

        self.tree_var = tk.BooleanVar(value=bool(cats.get("tree", True)))
        self.code_var = tk.BooleanVar(value=bool(cats.get("code", True)))
        self.style_var = tk.BooleanVar(value=bool(cats.get("style", True)))
        self.config_var = tk.BooleanVar(value=bool(cats.get("config", True)))
        self.doc_var = tk.BooleanVar(value=bool(cats.get("document", True)))
        self.text_var = tk.BooleanVar(value=bool(cats.get("text", True)))
        self.data_var = tk.BooleanVar(value=bool(cats.get("data", True)))
        self.log_var = tk.BooleanVar(value=bool(cats.get("log", True)))
        self.output_files_var = tk.BooleanVar(
            value=bool(cats.get("output_files", False))
        )
        self.empty_var = tk.BooleanVar(
            value=bool(cats.get("empty", False))
        )
        self.env_files_var = tk.BooleanVar(
            value=bool(cats.get("env_files", False))
        )

        self.exclude_var = tk.StringVar(
            value=str(
                settings.get(
                    "excluded_dirs",
                    ", ".join(sorted(core.DEFAULT_IGNORED_DIRS)),
                )
            )
        )
        self.ext_filter_var = tk.StringVar(
            value=str(settings.get("extension_filter", ""))
        )
        self.ext_exclude_var = tk.BooleanVar(
            value=bool(settings.get("extension_exclude", False))
        )

        # Обрезка длинных файлов.
        self.truncate_var = tk.BooleanVar(
            value=bool(settings.get("truncate_enabled", False))
        )
        self.truncate_lines_var = tk.StringVar(
            value=str(settings.get("truncate_max_lines", "1000"))
        )

        # Фильтр «только изменённые».
        _saved_mode = str(settings.get("changed_only_mode", "off"))
        _saved_subject = str(settings.get("changed_commit_subject", ""))

        self._changed_commit_hash: str | None = None
        self._changed_commit_subject: str = _saved_subject
        self._recent_commits: list[dict] = []
        self._repo_root: Path | None = None
        self._git_refresh_after_id: str | None = None

        # Хотим восстановить сохранённый коммит при первом успешном
        # обновлении git-состояния (по совпадению subject).
        self._pending_commit_restore = (
            _saved_mode == "since_commit" and bool(_saved_subject)
        )

        if _saved_mode not in CHANGED_KEY_TO_LABEL:
            _saved_mode = "off"
        if self._pending_commit_restore:
            # Пока не подтвердили наличие коммита — показываем «Выключено».
            _saved_mode = "off"

        self._changed_mode = _saved_mode
        self.changed_only_display_var = tk.StringVar(
            value=CHANGED_KEY_TO_LABEL[self._changed_mode]
        )
        self.changed_count_var = tk.StringVar(value="")
        self.changed_warning_var = tk.StringVar(value="")
        self.git_warn_var = tk.StringVar(value="")
        self.git_info_var = tk.StringVar(value="")
        self._changed_count_after_id: str | None = None

        self.recent_projects: list[str] = list(
            settings.get("recent_projects") or []
        )
        self.recent_outputs: dict[str, str] = dict(
            settings.get("recent_outputs") or {}
        )

        # Ручной выбор файлов.
        # None = «все подходящие под фильтры».
        # set[Path] = whitelist выбранных путей.
        # _selected_files_root — к какому проекту относится выбор;
        # если пользователь сменил проект, выбор не применяем.
        self.selected_files: set[Path] | None = None
        self._selected_files_root: str | None = None
        self.selected_files_var = tk.StringVar(value="все подходящие")

        self.status_var = tk.StringVar(value="Выберите каталог проекта.")
        self.stats_var = tk.StringVar(value="Статистика: —")
        self.advanced_summary_var = tk.StringVar(value="")

        self.prompt_attach_var = tk.BooleanVar(
            value=self._initial_prompt_attach
        )
        self.prompt_status_var = tk.StringVar(value="")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.setup_ui()

        self.ext_filter_var.trace_add(
            "write", lambda *_: self._update_advanced_summary()
        )
        self.ext_exclude_var.trace_add(
            "write", lambda *_: self._update_advanced_summary()
        )
        self.exclude_var.trace_add(
            "write", lambda *_: self._update_advanced_summary()
        )
        self._update_advanced_summary()
        self._refresh_recent_menu()
        self._update_selected_files_var()
        self._setup_autosave()

        # Фильтр «только изменённые».
        self.changed_only_display_var.trace_add(
            "write", lambda *_: self._on_changed_mode_changed()
        )
        def _on_root_changed(*_) -> None:
            # При смене корня выбранный коммит относится к старому репо —
            # сбрасываем. Если ещё ждём восстановление из настроек —
            # не трогаем, оно сработает после refresh.
            if (
                not self._pending_commit_restore
                and self._changed_mode == git_utils.MODE_SINCE_COMMIT
            ):
                self._changed_mode = "off"
                self._changed_commit_hash = None
                self._changed_commit_subject = ""
                self.changed_only_display_var.set(
                    CHANGED_KEY_TO_LABEL["off"]
                )
            self._schedule_git_refresh()
            self._update_prompt_status()

        self.root_var.trace_add("write", _on_root_changed)
        self._schedule_git_refresh()
        self._update_prompt_status()
        self._update_changed_warning()

        # Горячая клавиша: Ctrl+Enter — собрать контекст.
        # Биндим на self (главное окно), событие всплывает от любого
        # дочернего виджета. Диалоги (file_picker, advanced) — отдельные
        # Toplevel, они сюда не пробьются, и это правильно.
        self.bind("<Control-Return>", self._on_hotkey_build)
        # На macOS принят Cmd+Enter.
        self.bind("<Command-Return>", self._on_hotkey_build)

    # ---------- UI ----------

    def setup_ui(self) -> None:
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            outer,
            orient="vertical",
            command=self.canvas.yview,
        )

        self.canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        frame = ttk.Frame(self.canvas, padding=12)
        self._canvas_window = self.canvas.create_window(
            (0, 0),
            window=frame,
            anchor="nw",
        )

        def on_frame_configure(_event) -> None:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        def on_canvas_configure(event) -> None:
            self.canvas.itemconfigure(
                self._canvas_window,
                width=event.width,
            )

        frame.bind("<Configure>", on_frame_configure)
        self.canvas.bind("<Configure>", on_canvas_configure)

        def on_mousewheel(event) -> None:
            widget = self.winfo_containing(event.x_root, event.y_root)
            current = widget

            while current is not None:
                if isinstance(current, tk.Text):
                    return
                current = current.master

            delta = event.delta
            if abs(delta) >= 120:
                steps = delta // 120
            else:
                steps = 1 if delta > 0 else -1

            self.canvas.yview_scroll(-steps, "units")

        self.bind_all("<MouseWheel>", on_mousewheel)

        # ----- Заголовок -----
        header = ttk.Frame(frame)
        header.pack(fill="x")

        ttk.Label(
            header,
            text=APP_TITLE,
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            header,
            text=(
                "Настройте состав контекста и соберите проект "
                "для ChatGPT в один клик."
            ),
        ).pack(anchor="w", pady=(2, 10))

        # ----- 1. Проект -----
        project_group = ttk.LabelFrame(frame, text="1. Проект", padding=8)
        project_group.pack(fill="x", pady=(0, 6))

        ttk.Label(project_group, text="Каталог:").grid(
            row=0,
            column=0,
            sticky="w",
        )

        ttk.Entry(
            project_group,
            textvariable=self.root_var,
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=8,
        )

        # Меню недавних проектов.
        self.recent_menu = tk.Menu(self, tearoff=False)
        self.recent_menu_btn = ttk.Menubutton(
            project_group,
            text="▼",
            width=3,
            menu=self.recent_menu,
        )
        self.recent_menu_btn.grid(row=0, column=2, padx=(0, 4))

        ttk.Button(
            project_group,
            text="Выбрать…",
            command=self.choose_root,
        ).grid(row=0, column=3)

        project_group.columnconfigure(1, weight=1)

        # ----- 2. Что включать -----
        include_group = ttk.LabelFrame(frame, text="2. Что включать", padding=8)
        include_group.pack(fill="x", pady=(0, 6))

        col1 = ttk.Frame(include_group)
        col2 = ttk.Frame(include_group)
        col3 = ttk.Frame(include_group)

        col1.grid(row=0, column=0, sticky="nw", padx=(0, 30))
        col2.grid(row=0, column=1, sticky="nw", padx=(0, 30))
        col3.grid(row=0, column=2, sticky="nw")

        for text, var in [
            ("Структура каталога", self.tree_var),
            ("Код (.py, .js, .ts, .go, .rs …)", self.code_var),
            ("Стили (.css, .scss, .less, .svg)", self.style_var),
            ("Конфиги (.json, .yaml, .toml, .ini)", self.config_var),
        ]:
            ttk.Checkbutton(col1, text=text, variable=var).pack(
                anchor="w", pady=1
            )

        for text, var in [
            ("Документация (.md, README, LICENSE)", self.doc_var),
            ("Текст (.txt)", self.text_var),
            ("Данные (.csv, .tsv, .jsonl)", self.data_var),
            ("Логи (.log)", self.log_var),
        ]:
            ttk.Checkbutton(col2, text=text, variable=var).pack(
                anchor="w", pady=1
            )

        for text, var in [
            ("Lock-файлы (package-lock.json, …)", self.output_files_var),
            ("Пустые файлы", self.empty_var),
            (".env-файлы (секреты!)", self.env_files_var),
        ]:
            ttk.Checkbutton(col3, text=text, variable=var).pack(
                anchor="w", pady=1
            )

        # Пресеты + доп. настройки.
        presets = ttk.Frame(include_group)
        presets.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(10, 0),
        )

        ttk.Label(presets, text="Быстрые настройки:").pack(
            side="left", padx=(0, 6)
        )

        ttk.Button(
            presets,
            text="Только структура",
            command=self.preset_only_tree,
        ).pack(side="left", padx=2)

        ttk.Button(
            presets,
            text="По умолчанию",
            command=self.preset_default,
        ).pack(side="left", padx=2)

        # Размер файла.
        ttk.Label(
            include_group,
            text="Максимальный размер одного файла:",
        ).grid(
            row=2,
            column=0,
            sticky="w",
            pady=(10, 0),
        )

        size_frame = ttk.Frame(include_group)
        size_frame.grid(
            row=2,
            column=1,
            columnspan=2,
            sticky="w",
            pady=(10, 0),
        )

        ttk.Spinbox(
            size_frame,
            from_=0.1,
            to=1000,
            increment=0.5,
            width=8,
            textvariable=self.max_var,
        ).pack(side="left")

        ttk.Label(size_frame, text="MB").pack(side="left", padx=5)

        # Кнопка + резюме доп. настроек.
        advanced_row = ttk.Frame(include_group)
        advanced_row.grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(10, 0),
        )

        ttk.Button(
            advanced_row,
            text="⚙  Дополнительные настройки…",
            command=self.open_advanced_settings,
        ).pack(side="left")

        ttk.Label(
            advanced_row,
            textvariable=self.advanced_summary_var,
            foreground="#666666",
        ).pack(side="left", padx=(12, 0))

        # Точный выбор файлов.
        files_row = ttk.Frame(include_group)
        files_row.grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(10, 0),
        )

        ttk.Label(files_row, text="Точный выбор файлов:").pack(
            side="left", padx=(0, 8)
        )

        ttk.Button(
            files_row,
            text="📁 Открыть список…",
            command=self.open_file_picker,
        ).pack(side="left")

        ttk.Label(
            files_row,
            textvariable=self.selected_files_var,
            foreground="#666666",
        ).pack(side="left", padx=(10, 0))

        ttk.Button(
            files_row,
            text="✕",
            width=3,
            command=self.clear_file_selection,
        ).pack(side="left", padx=(6, 0))

        # Фильтр «только изменённые».
        changed_row = ttk.Frame(include_group)
        changed_row.grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(10, 0),
        )

        ttk.Label(changed_row, text="Только изменённые:").pack(
            side="left", padx=(0, 8)
        )

        self.changed_combo = ttk.Combobox(
            changed_row,
            textvariable=self.changed_only_display_var,
            values=[label for _, label in CHANGED_MODES_STATIC],
            state="readonly",
            width=48,
        )
        self.changed_combo.pack(side="left")

        ttk.Label(
            changed_row,
            textvariable=self.changed_count_var,
            foreground="#666666",
        ).pack(side="left", padx=(10, 0))

        ttk.Label(
            changed_row,
            textvariable=self.changed_warning_var,
            foreground="#B8860B",  # тёмно-золотой, читается на белом
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(10, 0))

        # Строка под селектором: предупреждение «git не найден»
        # и/или мелкая информация о найденном репозитории.
        git_row = ttk.Frame(include_group)
        git_row.grid(
            row=6,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(4, 0),
        )

        ttk.Label(
            git_row,
            textvariable=self.git_warn_var,
            foreground="#B8860B",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(8, 0))

        ttk.Label(
            git_row,
            textvariable=self.git_info_var,
            foreground="#888888",
            font=("Segoe UI", 8),
        ).pack(side="left", padx=(8, 0))

                # ----- 3. Промпт -----
        prompt_group = ttk.LabelFrame(
            frame, text="3. Промпт (необязательно)", padding=8
        )
        prompt_group.pack(fill="x", pady=(0, 6))

        prompt_row = ttk.Frame(prompt_group)
        prompt_row.pack(fill="x")

        ttk.Checkbutton(
            prompt_row,
            text="Прикрепить промпт из Prompt.md",
            variable=self.prompt_attach_var,
            command=self._on_prompt_attach_toggle,
        ).pack(side="left")

        ttk.Button(
            prompt_row,
            text="👁 Предпросмотр",
            command=self._on_preview_prompt,
        ).pack(side="left", padx=(12, 0))

        ttk.Button(
            prompt_row,
            text="📝 Открыть в редакторе",
            command=self._on_open_prompt,
        ).pack(side="left", padx=(6, 0))

        ttk.Label(
            prompt_group,
            textvariable=self.prompt_status_var,
            foreground="#666666",
        ).pack(anchor="w", pady=(4, 0))


        # ----- 4. Результат -----
        result_group = ttk.LabelFrame(frame, text="4. Результат", padding=8)
        result_group.pack(fill="x", pady=(0, 6))

        ttk.Label(result_group, text="TXT:").grid(
            row=0,
            column=0,
            sticky="w",
        )

        ttk.Entry(
            result_group,
            textvariable=self.output_var,
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=8,
        )

        ttk.Button(
            result_group,
            text="Куда сохранить…",
            command=self.choose_output,
        ).grid(row=0, column=2)

        result_group.columnconfigure(1, weight=1)

        # ----- Действия -----
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(2, 6))

        ttk.Button(
            actions,
            text="СОБРАТЬ КОНТЕКСТ",
            command=self.build,
        ).pack(side="left")

        ttk.Button(
            actions,
            text="📋 Копировать",
            command=self.copy,
        ).pack(side="left", padx=6)

        ttk.Button(
            actions,
            text="📄 Открыть TXT",
            command=self.open_output_file,
        ).pack(side="left")

        ttk.Button(
            actions,
            text="📂 Открыть папку",
            command=self.open_folder,
        ).pack(side="left", padx=6)

        # ----- Статистика -----
        ttk.Label(
            frame,
            textvariable=self.stats_var,
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        # ----- Журнал -----
        log_frame = ttk.LabelFrame(frame, text="Журнал", padding=4)
        log_frame.pack(fill="both", expand=True)

        self.log = ScrolledText(
            log_frame,
            height=6,
            wrap="word",
            font=("Consolas", 9),
            state="disabled",
        )
        self.log.pack(fill="both", expand=True)

        # ----- Статус -----
        ttk.Label(
            frame,
            textvariable=self.status_var,
            relief="sunken",
            anchor="w",
            padding=4,
        ).pack(fill="x", pady=(4, 0))

        self.log_msg("Приложение готово.")
        self.log_msg(f"Файл настроек: {core.settings_path()}")

    # ---------- Автосохранение ----------

    def _setup_autosave(self) -> None:
        watched = (
            self.tree_var,
            self.code_var,
            self.style_var,
            self.config_var,
            self.doc_var,
            self.text_var,
            self.data_var,
            self.log_var,
            self.output_files_var,
            self.empty_var,
            self.env_files_var,
            self.max_var,
            self.exclude_var,
            self.ext_filter_var,
            self.ext_exclude_var,
            self.truncate_var,
            self.truncate_lines_var,
            self.prompt_attach_var,
        )

        for var in watched:
            var.trace_add("write", lambda *_: self._schedule_autosave())


    def _on_hotkey_build(self, _event=None) -> str:
        self.build()
        return "break"

    def _compose_user_prompt(self, root: Path) -> str:
        """Читает Prompt.md и возвращает готовый текст промпта."""
        if not self.prompt_attach_var.get():
            return ""

        path = core.prompt_file_path(root)
        text, _ = core.parse_prompt_file(path)
        return text

    def _on_prompt_attach_toggle(self) -> None:
        self._update_prompt_status()
        self._schedule_autosave()

    def _update_prompt_status(self) -> None:
        root_text = self.root_var.get().strip()
        if not root_text:
            self.prompt_status_var.set("")
            return

        root = Path(root_text).expanduser()
        if not root.is_dir():
            self.prompt_status_var.set("")
            return

        path = core.prompt_file_path(root)
        if not path.exists():
            self.prompt_status_var.set(
                "Prompt.md ещё не создан — нажми «Предпросмотр» "
                "или «Открыть в редакторе»."
            )
            return
        
        _, stats = core.parse_prompt_file(path)
        if stats.get("error"):
            self.prompt_status_var.set(
                "Не удалось прочитать Prompt.md (проверь кодировку)."
            )
            return

        found = [
            name
            for name in ("HEADER", "QUESTS", "FREE", "QUESTIONS")
            if stats["sections"].get(name)
        ]
        sections_str = " / ".join(found) if found else "—"

        self.prompt_status_var.set(
            f"Prompt.md: активных {stats['active']}  •  "
            f"снятых {stats['skipped']}  •  "
            f"секции: {sections_str}"
        )

    def _on_open_prompt(self) -> None:
        """Открывает Prompt.md во внешнем редакторе."""
        root_text = self.root_var.get().strip()
        if not root_text:
            messagebox.showwarning(
                APP_TITLE,
                "Сначала выберите каталог проекта.",
            )
            return

        root = Path(root_text).expanduser().resolve()
        if not root.is_dir():
            messagebox.showwarning(
                APP_TITLE,
                "Каталог проекта не существует.",
            )
            return

        path, created = core.ensure_prompt_file(root)

        if not path.exists():
            messagebox.showerror(
                APP_TITLE,
                f"Не удалось создать файл:\n{path}",
            )
            return

        if created:
            self.log_msg(f"Создан шаблон промпта: {path}")
        else:
            self.log_msg(f"Открываю в редакторе: {path}")

        if self._open_path_external(path):
            self._update_prompt_status()

    def _on_preview_prompt(self) -> None:
        """Открывает модалку с распарсенным промптом."""
        root_text = self.root_var.get().strip()
        if not root_text:
            messagebox.showwarning(
                APP_TITLE,
                "Сначала выберите каталог проекта.",
            )
            return

        root = Path(root_text).expanduser().resolve()
        if not root.is_dir():
            messagebox.showwarning(
                APP_TITLE,
                "Каталог проекта не существует.",
            )
            return

        path, created = core.ensure_prompt_file(root)

        if not path.exists():
            messagebox.showerror(
                APP_TITLE,
                f"Не удалось создать файл:\n{path}",
            )
            return

        if created:
            self.log_msg(f"Создан шаблон промпта: {path}")

        prompt_preview.show_preview(
            self,
            path,
            on_open_editor=lambda: self._open_path_external(path),
        )
        self._update_prompt_status()

    def _open_path_external(self, path: Path) -> bool:
        """Открывает файл ассоциированным приложением. True при успехе."""
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(str(path))
            elif system == "Darwin":
                subprocess.run(["open", str(path)], check=False)
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
            return True
        except Exception as exc:
            messagebox.showerror(
                APP_TITLE,
                f"Не удалось открыть файл:\n\n{exc}",
            )
            return False

    def _schedule_autosave(self) -> None:
        if self._autosave_after_id is not None:
            self.after_cancel(self._autosave_after_id)
        self._autosave_after_id = self.after(
            AUTOSAVE_DELAY_MS, self._do_autosave
        )

    def _do_autosave(self) -> None:
        self._autosave_after_id = None
        self._save_settings()

    # ---------- Ручной выбор файлов ----------

    def _update_selected_files_var(self) -> None:
        if self.selected_files is None:
            self.selected_files_var.set("все подходящие")
        else:
            self.selected_files_var.set(
                f"выбрано вручную: {len(self.selected_files)}"
            )

    def _current_whitelist(self, root: Path) -> set[Path] | None:
        """Возвращает whitelist, только если он относится к этому root."""
        if self.selected_files is None:
            return None
        if self._selected_files_root != str(root):
            return None
        return self.selected_files

    def clear_file_selection(self) -> None:
        if self.selected_files is None:
            return
        self.selected_files = None
        self._selected_files_root = None
        self._update_selected_files_var()
        self.log_msg("Ручной выбор файлов сброшен.")

    def open_file_picker(self) -> None:
        try:
            root, _ = self.get_settings()
        except ValueError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            return

        enabled_categories = {
            "code": self.code_var.get(),
            "style": self.style_var.get(),
            "config": self.config_var.get(),
            "document": self.doc_var.get(),
            "text": self.text_var.get(),
            "data": self.data_var.get(),
            "log": self.log_var.get(),
            "output": self.output_files_var.get(),
        }

        ignored = core.parse_exclusions(self.exclude_var.get())
        ext_filter = core.parse_extensions(self.ext_filter_var.get())
        ext_exclude = self.ext_exclude_var.get()
        include_env = self.env_files_var.get()

        # Выходной файл не показываем в списке.
        exclude: set[Path] = set()
        output_text = self.output_var.get().strip()
        if output_text:
            exclude.add(Path(output_text).expanduser())

        changed_files, _ = self._get_changed_files_for_build(root)

        candidates = core.list_candidate_files(
            root=root,
            enabled_categories=enabled_categories,
            ignored_dirs=ignored,
            ext_filter=ext_filter,
            ext_exclude=ext_exclude,
            include_env_files=include_env,
            exclude_paths=exclude or None,
            changed_only_files=changed_files,
        )

        if not candidates:
            messagebox.showinfo(
                APP_TITLE,
                "Нет файлов, подходящих под текущие фильтры.",
            )
            return

        preselected = self._current_whitelist(root)

        result = file_picker.pick_files(
            parent=self,
            root=root,
            candidates=candidates,
            preselected=preselected,
        )

        if result is None:
            return

        self.selected_files = result
        self._selected_files_root = str(root)
        self._update_selected_files_var()

        self.log_msg(
            f"Ручной выбор: {len(result)} из {len(candidates)} файлов."
        )

    # ---------- Фильтр «только изменённые» ----------

    def _on_changed_mode_changed(self) -> None:
        label = self.changed_only_display_var.get()

        if label in CHANGED_LABEL_TO_KEY:
            self._changed_mode = CHANGED_LABEL_TO_KEY[label]
            self._changed_commit_hash = None
            self._changed_commit_subject = ""
        else:
            matched = next(
                (c for c in self._recent_commits if c["label"] == label),
                None,
            )
            if matched is not None:
                self._changed_mode = git_utils.MODE_SINCE_COMMIT
                self._changed_commit_hash = matched["hash"]
                self._changed_commit_subject = matched["subject"]
            else:
                self._changed_mode = "off"
                self._changed_commit_hash = None
                self._changed_commit_subject = ""
                self.changed_only_display_var.set(
                    CHANGED_KEY_TO_LABEL["off"]
                )

        self._update_changed_warning()
        self._schedule_changed_count_update()
        self._schedule_autosave()

    def _schedule_git_refresh(self) -> None:
        if self._git_refresh_after_id is not None:
            self.after_cancel(self._git_refresh_after_id)
        self._git_refresh_after_id = self.after(
            400, self._refresh_git_state
        )

    def _refresh_git_state(self) -> None:
        self._git_refresh_after_id = None

        root_text = self.root_var.get().strip()
        if not root_text:
            self._apply_git_state(reason="no_root")
            return

        root = Path(root_text).expanduser()
        if not root.is_dir():
            self._apply_git_state(reason="no_root")
            return

        repo_root = git_utils.get_repo_root(root)
        if repo_root is None:
            self._apply_git_state(reason="no_git")
            return

        commits = git_utils.get_recent_commits(root, 15)
        self._apply_git_state(
            reason="ok",
            repo_root=repo_root,
            commits=commits,
            project_root=root,
        )

    def _apply_git_state(
        self,
        reason: str,
        repo_root: Path | None = None,
        commits: list[dict] | None = None,
        project_root: Path | None = None,
    ) -> None:
        commits = commits or []
        self._repo_root = repo_root
        self._recent_commits = commits

        static_labels = [label for _, label in CHANGED_MODES_STATIC]
        commit_labels = [c["label"] for c in commits]
        self.changed_combo.configure(
            values=static_labels + commit_labels
        )

        if reason == "no_git":
            self.changed_combo.configure(state="disabled")
            self.git_info_var.set("")
            self.git_warn_var.set(
                "⚠  Git не найден в выбранном каталоге!"
            )

            if self._changed_mode != "off":
                self._changed_mode = "off"
                self._changed_commit_hash = None
                self._changed_commit_subject = ""
                self.changed_only_display_var.set(
                    CHANGED_KEY_TO_LABEL["off"]
                )
                self.log_msg(
                    "Git не найден — режим «Только изменённые» выключен."
                )

        else:
            self.changed_combo.configure(state="readonly")
            self.git_warn_var.set("")
            if reason == "ok" and repo_root is not None:
                repo_str = str(repo_root)
                show_parent_hint = (
                    project_root is not None
                    and repo_root.resolve() != project_root.resolve()
                )
                if show_parent_hint:
                    self.git_info_var.set(
                        f"Git: {repo_str}  (родительский каталог)"
                    )
                else:
                    self.git_info_var.set(f"Git: {repo_str}")
            else:
                self.git_info_var.set("")

        # Восстановление сохранённого коммита — один раз при первом
        # успешном обновлении состояния.
        if self._pending_commit_restore and reason == "ok":
            self._pending_commit_restore = False
            subject = self._changed_commit_subject
            matched = next(
                (c for c in commits if c["subject"] == subject),
                None,
            )
            if matched is not None:
                self._changed_mode = git_utils.MODE_SINCE_COMMIT
                self._changed_commit_hash = matched["hash"]
                self.changed_only_display_var.set(matched["label"])
            else:
                self.log_msg(
                    f"Коммит «{subject}» не найден среди последних 15 — "
                    "режим сброшен на «Выключено»."
                )
                self._changed_mode = "off"
                self._changed_commit_hash = None
                self._changed_commit_subject = ""
                self.changed_only_display_var.set(
                    CHANGED_KEY_TO_LABEL["off"]
                )

        self._update_changed_warning()
        self._update_changed_count_inline()

    def _update_changed_warning(self) -> None:
        if self._changed_mode == "off":
            self.changed_warning_var.set("")
        else:
            self.changed_warning_var.set(
                "⚠  Внимание — в сборку попадут не все файлы!"
            )

    def _schedule_changed_count_update(self) -> None:
        if self._changed_count_after_id is not None:
            self.after_cancel(self._changed_count_after_id)
        self._changed_count_after_id = self.after(
            400, self._update_changed_count
        )

    def _update_changed_count(self) -> None:
        self._changed_count_after_id = None
        self._update_changed_count_inline()

    def _update_changed_count_inline(self) -> None:
        if self._changed_mode == "off":
            self.changed_count_var.set("")
            return

        root_text = self.root_var.get().strip()
        if not root_text:
            self.changed_count_var.set("—")
            return

        root = Path(root_text).expanduser()
        if not root.is_dir() or self._repo_root is None:
            self.changed_count_var.set("не git-репозиторий")
            return

        try:
            if self._changed_mode == git_utils.MODE_SINCE_COMMIT:
                changed = git_utils.get_changed_files(
                    root,
                    self._changed_mode,
                    self._changed_commit_hash,
                )
            else:
                changed = git_utils.get_changed_files(
                    root, self._changed_mode
                )
        except Exception as exc:
            self.changed_count_var.set(f"ошибка: {exc}")
            return

        if changed is None:
            self.changed_count_var.set("")
        elif not changed:
            self.changed_count_var.set("нет изменений")
        else:
            self.changed_count_var.set(f"{len(changed)} файл(ов)")

    def _get_changed_files_for_build(
        self, root: Path
    ) -> tuple[set[Path] | None, str | None]:
        """Возвращает (set, label) для передачи в build_context."""
        if self._changed_mode == "off":
            return None, None

        try:
            if self._changed_mode == git_utils.MODE_SINCE_COMMIT:
                if not self._changed_commit_hash:
                    return set(), "git: since_commit (hash не разрешён)"
                changed = git_utils.get_changed_files(
                    root,
                    self._changed_mode,
                    self._changed_commit_hash,
                )
                subject_short = self._changed_commit_subject[:40]
                label = f"git: с «{subject_short}»"
            else:
                changed = git_utils.get_changed_files(
                    root, self._changed_mode
                )
                label = CHANGED_KEY_TO_LABEL.get(
                    self._changed_mode, self._changed_mode
                ).lower()
                label = f"git: {label}"
        except Exception:
            return set(), "git: ошибка"

        if changed is None:
            return None, None

        return changed, label

    # ---------- Недавние проекты ----------

    def _refresh_recent_menu(self) -> None:
        self.recent_menu.delete(0, "end")

        if not self.recent_projects:
            self.recent_menu.add_command(
                label="(пусто)",
                state="disabled",
            )
            return

        for path in self.recent_projects:
            display = path
            if len(display) > 70:
                display = "…" + display[-68:]

            self.recent_menu.add_command(
                label=display,
                command=lambda p=path: self._open_recent_project(p),
            )

        self.recent_menu.add_separator()
        self.recent_menu.add_command(
            label="Очистить список",
            command=self._clear_recent_projects,
        )

    def _add_recent_project(self, path: str) -> None:
        if not path:
            return

        # Убираем дубликат и добавляем в начало.
        self.recent_projects = [
            p for p in self.recent_projects if p != path
        ]
        self.recent_projects.insert(0, path)
        self.recent_projects = self.recent_projects[
            : core.MAX_RECENT_PROJECTS
        ]

        # Убираем карту путей для проектов, которых больше нет в списке.
        keep = set(self.recent_projects)
        self.recent_outputs = {
            k: v for k, v in self.recent_outputs.items() if k in keep
        }

        self._refresh_recent_menu()

    def _open_recent_project(self, path: str) -> None:
        p = Path(path).expanduser()

        if not p.is_dir():
            messagebox.showwarning(
                APP_TITLE,
                f"Каталог больше не существует:\n{path}",
            )
            self.recent_projects = [
                item for item in self.recent_projects if item != path
            ]
            self.recent_outputs.pop(path, None)
            self._refresh_recent_menu()
            return

        self.root_var.set(str(p))

        # Сброс ручного выбора при смене проекта.
        self.selected_files = None
        self._selected_files_root = None
        self._update_selected_files_var()

        saved_output = self.recent_outputs.get(path)
        if saved_output:
            self.output_var.set(saved_output)
            self.log_msg(f"Восстановлен путь сохранения: {saved_output}")
        else:
            self.output_var.set(str(p / f"{p.name}_context.txt"))

        self._update_prompt_status()
        self.status_var.set("Выбран проект из недавних.")
        self.log_msg(f"Недавний проект: {p}")

    def _clear_recent_projects(self) -> None:
        if not self.recent_projects:
            return

        if not messagebox.askyesno(
            APP_TITLE,
            "Очистить список недавних проектов?",
        ):
            return

        self.recent_projects = []
        self.recent_outputs = {}
        self._refresh_recent_menu()
        self.log_msg("Список недавних проектов очищен.")

    # ---------- Дополнительные настройки ----------

    def _update_advanced_summary(self) -> None:
        ext = self.ext_filter_var.get().strip()

        if not ext:
            ext_part = "расширения: все"
        elif self.ext_exclude_var.get():
            ext_part = f"расширения: исключая {ext}"
        else:
            ext_part = f"расширения: только {ext}"

        count = len(core.parse_exclusions(self.exclude_var.get()))
        excl_part = f"исключено папок: {count}"

        self.advanced_summary_var.set(f"{ext_part}  •  {excl_part}")

    def open_advanced_settings(self) -> None:
        existing = self._advanced_window
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.focus_force()
                    return
            except tk.TclError:
                pass

        win = tk.Toplevel(self)
        win.title("Дополнительные настройки")
        win.transient(self)
        win.resizable(False, False)
        self._advanced_window = win

        container = ttk.Frame(win, padding=15)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text="Дополнительные настройки",
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            container,
            text=(
                "Параметры не обязательные — по умолчанию работают "
                "разумные значения. Изменения применяются сразу "
                "и сохраняются автоматически."
            ),
            foreground="#666666",
        ).pack(anchor="w", pady=(2, 12))

        # --- Фильтр по расширениям ---
        filter_group = ttk.LabelFrame(
            container,
            text="Фильтр по расширениям",
            padding=10,
        )
        filter_group.pack(fill="x", pady=(0, 10))

        ttk.Label(
            filter_group,
            text=(
                "Пусто — фильтр выключен. Иначе: без галочки — попадут "
                "только файлы этих расширений (и только включённых "
                "категорий), с галочкой — наоборот, будут исключены."
            ),
            wraplength=640,
            justify="left",
        ).pack(anchor="w")

        filter_row = ttk.Frame(filter_group)
        filter_row.pack(fill="x", pady=(6, 4))

        ttk.Entry(
            filter_row,
            textvariable=self.ext_filter_var,
        ).pack(side="left", fill="x", expand=True)

        ttk.Checkbutton(
            filter_row,
            text="Исключать выбранные",
            variable=self.ext_exclude_var,
        ).pack(side="left", padx=(8, 0))

        quick = ttk.Frame(filter_group)
        quick.pack(fill="x", pady=(2, 0))

        ttk.Label(quick, text="Быстро:").pack(side="left")

        for ext in QUICK_EXTENSIONS:
            ttk.Button(
                quick,
                text=ext,
                width=6,
                command=lambda value=ext: self.add_ext(value),
            ).pack(side="left", padx=2)

        ttk.Button(
            quick,
            text="Очистить",
            command=lambda: self.ext_filter_var.set(""),
        ).pack(side="left", padx=(10, 0))

        # --- Исключённые каталоги ---
        exclude_group = ttk.LabelFrame(
            container,
            text="Исключённые каталоги",
            padding=10,
        )
        exclude_group.pack(fill="x", pady=(0, 10))

        ttk.Entry(
            exclude_group,
            textvariable=self.exclude_var,
        ).pack(fill="x")

        ttk.Label(
            exclude_group,
            text="Названия через запятую: node_modules, .git, venv, dist …",
            foreground="#666666",
        ).pack(anchor="w", pady=(4, 0))

        # --- Обрезка длинных файлов ---
        truncate_group = ttk.LabelFrame(
            container,
            text="Обрезка длинных файлов",
            padding=10,
        )
        truncate_group.pack(fill="x", pady=(0, 10))

        truncate_row = ttk.Frame(truncate_group)
        truncate_row.pack(fill="x")

        ttk.Checkbutton(
            truncate_row,
            text="Обрезать файлы длиннее",
            variable=self.truncate_var,
        ).pack(side="left")

        ttk.Spinbox(
            truncate_row,
            from_=100,
            to=100000,
            increment=100,
            width=8,
            textvariable=self.truncate_lines_var,
        ).pack(side="left", padx=(6, 4))

        ttk.Label(truncate_row, text="строк").pack(side="left")

        ttk.Label(
            truncate_group,
            text=(
                "Оставляет первые и последние N/2 строк, а в середине — "
                "пометку о пропуске. Полезно для package-lock.json "
                "и больших авто-сгенерированных файлов."
            ),
            foreground="#666666",
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

        # --- Кнопки ---
        btn_row = ttk.Frame(container)
        btn_row.pack(fill="x", pady=(6, 0))

        ttk.Button(
            btn_row,
            text="Сбросить расширения",
            command=self._reset_extension_filter,
        ).pack(side="left")

        ttk.Button(
            btn_row,
            text="Сбросить исключения",
            command=self._reset_excluded_dirs,
        ).pack(side="left", padx=(6, 0))

        ttk.Button(
            btn_row,
            text="Сбросить всё",
            command=self._reset_all_settings,
        ).pack(side="left", padx=(6, 0))

        ttk.Button(
            btn_row,
            text="Готово",
            command=win.destroy,
        ).pack(side="right")

        # Путь к файлу настроек — мелким шрифтом.
        ttk.Label(
            container,
            text=f"Файл настроек: {core.settings_path()}",
            foreground="#888888",
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(10, 0))

        win.bind("<Escape>", lambda _e: win.destroy())

        # Центрируем относительно главного окна.
        win.update_idletasks()
        w = win.winfo_width()
        h = win.winfo_height()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - w) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - h) // 3)
        win.geometry(f"+{x}+{y}")

        win.grab_set()
        win.focus_set()

    def _reset_extension_filter(self) -> None:
        self.ext_filter_var.set("")
        self.ext_exclude_var.set(False)
        self.log_msg("Сброшен фильтр расширений.")

    def _reset_excluded_dirs(self) -> None:
        self.exclude_var.set(", ".join(sorted(core.DEFAULT_IGNORED_DIRS)))
        self.log_msg("Сброшен список исключённых каталогов.")

    def _reset_all_settings(self) -> None:
        if not messagebox.askyesno(
            APP_TITLE,
            "Сбросить все настройки к значениям по умолчанию?",
        ):
            return

        defaults = core.default_settings()
        cats = defaults.get("categories") or {}

        self.tree_var.set(bool(cats.get("tree", True)))
        self.code_var.set(bool(cats.get("code", True)))
        self.style_var.set(bool(cats.get("style", True)))
        self.config_var.set(bool(cats.get("config", True)))
        self.doc_var.set(bool(cats.get("document", True)))
        self.text_var.set(bool(cats.get("text", True)))
        self.data_var.set(bool(cats.get("data", True)))
        self.log_var.set(bool(cats.get("log", True)))
        self.output_files_var.set(bool(cats.get("output_files", False)))
        self.empty_var.set(bool(cats.get("empty", False)))
        self.env_files_var.set(bool(cats.get("env_files", False)))

        self.max_var.set(str(defaults.get("max_mb", "2")))
        self.exclude_var.set(str(defaults.get("excluded_dirs", "")))
        self.ext_filter_var.set(str(defaults.get("extension_filter", "")))
        self.ext_exclude_var.set(
            bool(defaults.get("extension_exclude", False))
        )
        self.truncate_var.set(
            bool(defaults.get("truncate_enabled", False))
        )
        self.truncate_lines_var.set(
            str(defaults.get("truncate_max_lines", "1000"))
        )

        mode = str(defaults.get("changed_only_mode", "off"))
        if mode not in CHANGED_KEY_TO_LABEL:
            mode = "off"
        self._changed_mode = mode
        self._changed_commit_hash = None
        self._changed_commit_subject = ""
        self._pending_commit_restore = False
        self.changed_only_display_var.set(CHANGED_KEY_TO_LABEL[mode])
        self._update_changed_warning()

        self.prompt_attach_var.set(
            bool(defaults.get("prompt_attach_enabled", False))
        )
        self._update_prompt_status()

        self.selected_files = None
        self._selected_files_root = None
        self._update_selected_files_var()

        self.log_msg("Настройки сброшены к значениям по умолчанию.")

    # ---------- Настройки (JSON) ----------

    def _collect_settings(self) -> dict:
        # Запоминаем последний использованный путь сохранения для
        # текущего проекта, чтобы подставлять его при следующем открытии.
        root = self.root_var.get().strip()
        output = self.output_var.get().strip()

        if root and output:
            self.recent_outputs[root] = output

        # Убираем карту для проектов, которых нет в списке недавних.
        keep = set(self.recent_projects)
        self.recent_outputs = {
            k: v for k, v in self.recent_outputs.items() if k in keep
        }

        return {
            "version": core.SETTINGS_VERSION,
            "categories": {
                "tree": self.tree_var.get(),
                "code": self.code_var.get(),
                "style": self.style_var.get(),
                "config": self.config_var.get(),
                "document": self.doc_var.get(),
                "text": self.text_var.get(),
                "data": self.data_var.get(),
                "log": self.log_var.get(),
                "output_files": self.output_files_var.get(),
                "empty": self.empty_var.get(),
                "env_files": self.env_files_var.get(),
            },
            "max_mb": self.max_var.get(),
            "excluded_dirs": self.exclude_var.get(),
            "extension_filter": self.ext_filter_var.get(),
            "extension_exclude": self.ext_exclude_var.get(),
            "truncate_enabled": self.truncate_var.get(),
            "truncate_max_lines": self.truncate_lines_var.get(),
            "changed_only_mode": self._changed_mode,
            "changed_commit_subject": self._changed_commit_subject,
            "prompt_attach_enabled": self.prompt_attach_var.get(),
            "recent_projects": list(self.recent_projects),
            "recent_outputs": dict(self.recent_outputs),
        }
        

    def _save_settings(self) -> None:
        try:
            data = self._collect_settings()
            ok, error = core.save_settings(data)

            if not ok and error:
                print(f"[settings] не удалось сохранить: {error}")
        except Exception as exc:
            print(f"[settings] исключение при сохранении: {exc}")

    def _on_close(self) -> None:
        if self._autosave_after_id is not None:
            try:
                self.after_cancel(self._autosave_after_id)
            except tk.TclError:
                pass
            self._autosave_after_id = None

        self._save_settings()
        self.destroy()

    # ---------- Пресеты ----------

    def preset_only_tree(self) -> None:
        for var in (
            self.code_var,
            self.style_var,
            self.config_var,
            self.doc_var,
            self.text_var,
            self.data_var,
            self.log_var,
            self.output_files_var,
            self.empty_var,
            self.env_files_var,
        ):
            var.set(False)

        self.tree_var.set(True)
        self.log_msg("Пресет: только структура каталога.")

    def preset_default(self) -> None:
        self.tree_var.set(True)
        self.code_var.set(True)
        self.style_var.set(True)
        self.config_var.set(True)
        self.doc_var.set(True)
        self.text_var.set(True)
        self.data_var.set(True)
        self.log_var.set(True)
        self.output_files_var.set(False)
        self.empty_var.set(False)
        self.env_files_var.set(False)
        self.log_msg("Пресет: настройки по умолчанию.")

    # ---------- Утилиты ----------

    def log_msg(self, msg: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.configure(state="disabled")
        self.log.after_idle(self.log.see, "end")

    def _play_success_sound(self) -> None:
        """Короткий системный сигнал «успех». Тихо молчит на не-Windows."""
        try:
            if platform.system() == "Windows":
                import winsound
                winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass     

    def add_ext(self, ext: str) -> None:
        current = self.ext_filter_var.get().strip()
        existing = core.parse_extensions(current)

        if ext.lower() in existing:
            return

        new_value = f"{current}, {ext}" if current else ext
        self.ext_filter_var.set(new_value)

    def choose_root(self) -> None:
        selected = filedialog.askdirectory(
            title="Выберите корневой каталог проекта"
        )

        if not selected:
            return

        root = Path(selected).resolve()

        self.root_var.set(str(root))
        self.output_var.set(str(root / f"{root.name}_context.txt"))
        self._update_prompt_status()

        # Сброс ручного выбора при смене проекта.
        self.selected_files = None
        self._selected_files_root = None
        self._update_selected_files_var()

        self._add_recent_project(str(root))
        self.status_var.set("Каталог выбран.")
        self.log_msg(f"Выбран проект: {root}")

    def choose_output(self) -> None:
        root = (
            Path(self.root_var.get()).expanduser()
            if self.root_var.get().strip()
            else Path.home()
        )

        selected = filedialog.asksaveasfilename(
            title="Сохранить контекст проекта",
            initialdir=str(root if root.exists() else Path.home()),
            initialfile=(
                f"{root.name}_context.txt"
                if root.name
                else "project_context.txt"
            ),
            defaultextension=".txt",
            filetypes=[
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )

        if selected:
            self.output_var.set(selected)

    def get_settings(self) -> tuple[Path, float]:
        root_text = self.root_var.get().strip()

        if not root_text:
            raise ValueError("Сначала выберите каталог проекта.")

        root = Path(root_text).expanduser().resolve()

        if not root.is_dir():
            raise ValueError("Каталог проекта не существует.")

        try:
            max_mb = float(self.max_var.get().replace(",", "."))
        except ValueError as exc:
            raise ValueError(
                "Максимальный размер файла должен быть числом."
            ) from exc

        if max_mb <= 0:
            raise ValueError(
                "Максимальный размер должен быть больше 0."
            )

        return root, max_mb

    def _get_truncate_max_lines(self) -> int:
        try:
            value = int(
                float(self.truncate_lines_var.get().replace(",", "."))
            )
        except (ValueError, AttributeError):
            return 1000

        return max(50, value)

    def _write_context(self, output_path: Path) -> bool:
        try:
            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            output_path.write_text(
                self.context,
                encoding="utf-8",
            )
            return True
        except OSError as exc:
            messagebox.showerror(
                APP_TITLE,
                f"Не удалось сохранить TXT:\n\n{exc}",
            )
            return False

    # ---------- Действия ----------

    def _build_context(self) -> bool:
        """Собирает контекст и пишет TXT. True при успехе.

        Все диалоговые окна — только для ошибок. Успех отражается
        в статусной строке, журнале и звуковом сигнале.
        """
        try:
            root, max_mb = self.get_settings()
        except ValueError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            return False

        enabled_categories = {
            "code": self.code_var.get(),
            "style": self.style_var.get(),
            "config": self.config_var.get(),
            "document": self.doc_var.get(),
            "text": self.text_var.get(),
            "data": self.data_var.get(),
            "log": self.log_var.get(),
            "output": self.output_files_var.get(),
        }

        ignored = core.parse_exclusions(self.exclude_var.get())
        ext_filter = core.parse_extensions(self.ext_filter_var.get())
        ext_exclude = self.ext_exclude_var.get()
        include_env = self.env_files_var.get()
        truncate_on = self.truncate_var.get()
        truncate_lines = self._get_truncate_max_lines()

        self.log_msg("=== СБОРКА ===")

        if ext_filter:
            mode = "исключение" if ext_exclude else "включение"
            self.log_msg(
                f"Фильтр расширений ({mode}): "
                f"{', '.join(sorted(ext_filter))}"
            )

        if include_env:
            self.log_msg(
                "ВНИМАНИЕ: включена обработка .env-файлов "
                "(могут содержать секреты)."
            )

        if truncate_on:
            self.log_msg(
                f"Обрезка длинных файлов: до {truncate_lines} строк."
            )

        whitelist = self._current_whitelist(root)
        if whitelist is not None:
            self.log_msg(f"Ручной выбор: {len(whitelist)} файл(ов).")

        changed_files, changed_label = self._get_changed_files_for_build(root)
        if changed_files is not None:
            self.log_msg(
                f"Только изменённые ({changed_label}): "
                f"{len(changed_files)} файл(ов)."
            )

        self.log_msg(f"Корень: {root}")
        self.status_var.set("Сканирование проекта…")

        if not self.output_var.get().strip():
            self.output_var.set(
                str(root / f"{root.name}_context.txt")
            )

        output_path = Path(self.output_var.get()).expanduser()

        user_prompt = self._compose_user_prompt(root)
        if user_prompt:
            self.log_msg(
                f"Промпт: {len(user_prompt)} символов — "
                "будет вставлен в начало."
            )

        try:
            context, stats = core.build_context(
                root=root,
                include_tree=self.tree_var.get(),
                enabled_categories=enabled_categories,
                include_empty=self.empty_var.get(),
                max_mb=max_mb,
                ignored_dirs=ignored,
                ext_filter=ext_filter,
                ext_exclude=ext_exclude,
                include_env_files=include_env,
                file_whitelist=whitelist,
                output_path=output_path,
                truncate_long_files=truncate_on,
                truncate_max_lines=truncate_lines,
                changed_only_files=changed_files,
                changed_only_label=changed_label,
                user_prompt=user_prompt,
            )
        except Exception as exc:
            self.status_var.set("Ошибка.")
            messagebox.showerror(
                APP_TITLE,
                f"Не удалось собрать контекст:\n\n{exc}",
            )
            return False

        self.context = context

        if not self._write_context(output_path):
            return False

        tokens_str = core.format_tokens(stats["tokens"])
        warning = (
            " ⚠️"
            if stats["tokens"] > core.TOKEN_WARNING_THRESHOLD
            else ""
        )

        self.stats_var.set(
            "Статистика: "
            f"элементов {stats['entries']} • "
            f"файлов {stats['files']} • "
            f"выбрано {stats['selected']} • "
            f"включено {stats['included']} • "
            f"размер {core.format_size(stats['size'])} • "
            f"~{tokens_str} токенов{warning}"
        )

        self.log_msg(
            f"Выбрано: {stats['selected']}; "
            f"включено: {stats['included']}; "
            f"пропущено: {len(stats['skipped'])}"
        )
        self.log_msg(
            f"~{tokens_str} токенов (оценка), "
            f"{core.format_size(stats['size'])}"
        )
        self.log_msg(f"Сохранено: {output_path}")

        if stats["tokens"] > core.TOKEN_WARNING_THRESHOLD:
            self.log_msg(
                f"⚠️ Контекст ~{tokens_str} токенов — может не влезть "
                "в одну сессию ChatGPT (типичный лимит 128k). "
                "Попробуйте отключить логи/данные или использовать "
                "точный выбор файлов."
            )

        self.status_var.set("Готово. Контекст собран.")
        return True

    def build(self) -> None:
        if self._build_context():
            self._play_success_sound()

    def copy(self) -> None:
        """Собирает контекст и сразу копирует в буфер обмена."""
        if not self._build_context():
            return

        try:
            self.clipboard_clear()
            self.clipboard_append(self.context)
            self.update()

            size = core.format_size(len(self.context.encode("utf-8")))
            self.status_var.set("Контекст скопирован в буфер обмена.")
            self.log_msg(f"Скопировано в буфер: {size}")
            self._play_success_sound()

        except tk.TclError as exc:
            messagebox.showerror(
                APP_TITLE,
                f"Ошибка буфера обмена:\n\n{exc}",
            )
    
    
    def open_output_file(self) -> None:
        """Собирает контекст и сразу открывает TXT."""
        if not self._build_context():
            return

        output_text = self.output_var.get().strip()
        if not output_text:
            return

        path = Path(output_text).expanduser()
        if not path.exists():
            messagebox.showwarning(
                APP_TITLE,
                f"Файл ещё не создан:\n{path}",
            )
            return

        if self._open_path_external(path):
            self._play_success_sound()

    def open_folder(self) -> None:
        output_text = self.output_var.get().strip()
        target = Path(output_text).expanduser() if output_text else Path.home()

        if target.is_dir():
            folder = target
        elif target.parent.exists():
            folder = target.parent
        else:
            folder = Path.home()

        if not folder.exists():
            messagebox.showwarning(
                APP_TITLE,
                "Папка ещё не существует.",
            )
            return

        try:
            system = platform.system()

            if system == "Windows":
                os.startfile(str(folder))
            elif system == "Darwin":
                subprocess.run(["open", str(folder)], check=False)
            else:
                subprocess.run(["xdg-open", str(folder)], check=False)

        except Exception as exc:
            messagebox.showerror(
                APP_TITLE,
                f"Не удалось открыть папку:\n\n{exc}",
            )