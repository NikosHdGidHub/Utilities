from __future__ import annotations

import os
import platform
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import core
import file_picker


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


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title(APP_TITLE)
        self.geometry("1000x720")
        self.minsize(900, 640)

        self.context = ""
        self._advanced_window: tk.Toplevel | None = None

        # Настройки читаем ДО создания переменных — чтобы сразу
        # подставить сохранённые значения.
        settings = core.load_settings()
        cats = settings.get("categories") or {}

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

        # ----- 3. Результат -----
        result_group = ttk.LabelFrame(frame, text="3. Результат", padding=8)
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

        candidates = core.list_candidate_files(
            root=root,
            enabled_categories=enabled_categories,
            ignored_dirs=ignored,
            ext_filter=ext_filter,
            ext_exclude=ext_exclude,
            include_env_files=include_env,
            exclude_paths=exclude or None,
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
                "разумные значения. Изменения применяются сразу."
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
            "recent_projects": list(self.recent_projects),
            "recent_outputs": dict(self.recent_outputs),
        }

    def _save_settings_on_exit(self) -> None:
        data = self._collect_settings()
        ok, error = core.save_settings(data)

        if not ok and error:
            print(f"[settings] не удалось сохранить: {error}")

    def _on_close(self) -> None:
        self._save_settings_on_exit()
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

    def build(self) -> None:
        try:
            root, max_mb = self.get_settings()
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

        whitelist = self._current_whitelist(root)
        if whitelist is not None:
            self.log_msg(
                f"Ручной выбор: {len(whitelist)} файл(ов)."
            )

        self.log_msg(f"Корень: {root}")
        self.status_var.set("Сканирование проекта…")

        # Путь к выходному файлу вычисляем ДО сборки — чтобы
        # исключить его из скана (иначе файл попадёт в самого себя).
        if not self.output_var.get().strip():
            self.output_var.set(
                str(root / f"{root.name}_context.txt")
            )

        output_path = Path(self.output_var.get()).expanduser()

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
            )
        except Exception as exc:
            self.status_var.set("Ошибка.")
            messagebox.showerror(
                APP_TITLE,
                f"Не удалось собрать контекст:\n\n{exc}",
            )
            return

        self.context = context

        if not self._write_context(output_path):
            return

        self.stats_var.set(
            "Статистика: "
            f"элементов {stats['entries']} • "
            f"файлов {stats['files']} • "
            f"выбрано {stats['selected']} • "
            f"включено {stats['included']} • "
            f"размер {core.format_size(stats['size'])}"
        )

        self.log_msg(
            f"Выбрано: {stats['selected']}; "
            f"включено: {stats['included']}; "
            f"пропущено: {len(stats['skipped'])}"
        )
        self.log_msg(f"Сохранено: {output_path}")

        self.status_var.set("Готово. Контекст собран.")

        messagebox.showinfo(
            APP_TITLE,
            "Готово!\n\n"
            f"Включено файлов: {stats['included']}\n"
            f"Размер: {core.format_size(stats['size'])}",
        )

    def copy(self) -> None:
        if not self.context:
            messagebox.showwarning(
                APP_TITLE,
                "Сначала соберите контекст.",
            )
            return

        try:
            self.clipboard_clear()
            self.clipboard_append(self.context)
            self.update()

            self.status_var.set(
                "Контекст скопирован в буфер обмена."
            )

            self.log_msg(
                "Скопировано в буфер: "
                f"{core.format_size(len(self.context.encode('utf-8')))}"
            )

            messagebox.showinfo(
                APP_TITLE,
                "Готово!\n\n"
                "Теперь можно вставить контекст в ChatGPT через Ctrl+V.",
            )

        except tk.TclError as exc:
            messagebox.showerror(
                APP_TITLE,
                f"Ошибка буфера обмена:\n\n{exc}",
            )

    def open_output_file(self) -> None:
        output_text = self.output_var.get().strip()

        if not output_text:
            messagebox.showwarning(
                APP_TITLE,
                "Путь к файлу не задан.",
            )
            return

        path = Path(output_text).expanduser()

        if not path.exists():
            messagebox.showwarning(
                APP_TITLE,
                f"Файл ещё не создан:\n{path}",
            )
            return

        try:
            system = platform.system()

            if system == "Windows":
                os.startfile(str(path))
            elif system == "Darwin":
                subprocess.run(["open", str(path)], check=False)
            else:
                subprocess.run(["xdg-open", str(path)], check=False)

        except Exception as exc:
            messagebox.showerror(
                APP_TITLE,
                f"Не удалось открыть файл:\n\n{exc}",
            )

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