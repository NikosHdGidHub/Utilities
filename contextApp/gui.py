from __future__ import annotations

import os
import platform
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import core


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
        self.geometry("1100x820")
        self.minsize(1000, 740)

        self.context = ""

        self.root_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.max_var = tk.StringVar(value="2")

        self.tree_var = tk.BooleanVar(value=True)
        self.code_var = tk.BooleanVar(value=True)
        self.style_var = tk.BooleanVar(value=True)
        self.config_var = tk.BooleanVar(value=True)
        self.doc_var = tk.BooleanVar(value=True)
        self.text_var = tk.BooleanVar(value=True)
        self.data_var = tk.BooleanVar(value=True)
        self.log_var = tk.BooleanVar(value=True)
        self.output_files_var = tk.BooleanVar(value=False)
        self.empty_var = tk.BooleanVar(value=False)
        # По умолчанию .env* исключены — там могут быть секреты.
        self.env_files_var = tk.BooleanVar(value=False)

        self.exclude_var = tk.StringVar(
            value=", ".join(sorted(core.DEFAULT_IGNORED_DIRS))
        )
        self.ext_filter_var = tk.StringVar()
        self.ext_exclude_var = tk.BooleanVar(value=False)

        self.status_var = tk.StringVar(value="Выберите каталог проекта.")
        self.stats_var = tk.StringVar(value="Статистика: —")

        self.setup_ui()

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

        frame = ttk.Frame(self.canvas, padding=15)
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

        ttk.Label(
            frame,
            text=APP_TITLE,
            font=("Segoe UI", 17, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            frame,
            text=(
                "Настройте состав контекста и одним кликом "
                "соберите проект для ChatGPT."
            ),
        ).pack(anchor="w", pady=(2, 12))

        # ----- 1. Проект -----
        project_group = ttk.LabelFrame(frame, text="1. Проект", padding=10)
        project_group.pack(fill="x", pady=5)

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

        ttk.Button(
            project_group,
            text="Выбрать…",
            command=self.choose_root,
        ).grid(row=0, column=2)

        project_group.columnconfigure(1, weight=1)

        # ----- 2. Что включать -----
        include_group = ttk.LabelFrame(frame, text="2. Что включать", padding=10)
        include_group.pack(fill="x", pady=5)

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
                anchor="w", pady=2
            )

        for text, var in [
            ("Документация (.md, README, LICENSE)", self.doc_var),
            ("Текст (.txt)", self.text_var),
            ("Данные (.csv, .tsv, .jsonl)", self.data_var),
            ("Логи (.log)", self.log_var),
        ]:
            ttk.Checkbutton(col2, text=text, variable=var).pack(
                anchor="w", pady=2
            )

        for text, var in [
            ("Lock-файлы (package-lock.json, …)", self.output_files_var),
            ("Пустые файлы", self.empty_var),
            (".env-файлы (секреты!)", self.env_files_var),
        ]:
            ttk.Checkbutton(col3, text=text, variable=var).pack(
                anchor="w", pady=2
            )

        presets = ttk.Frame(include_group)
        presets.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(12, 0),
        )

        ttk.Label(presets, text="Быстрые настройки:").pack(
            side="left", padx=(0, 8)
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

        # Максимальный размер файла.
        ttk.Label(
            include_group,
            text="Максимальный размер одного файла:",
        ).grid(
            row=2,
            column=0,
            sticky="w",
            pady=(12, 0),
        )

        size_frame = ttk.Frame(include_group)
        size_frame.grid(
            row=2,
            column=1,
            columnspan=2,
            sticky="w",
            pady=(12, 0),
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

        # ----- 3. Фильтр по расширениям -----
        filter_group = ttk.LabelFrame(
            frame,
            text="3. Фильтр по расширениям (необязательно)",
            padding=10,
        )
        filter_group.pack(fill="x", pady=5)

        ttk.Label(
            filter_group,
            text=(
                "Пусто — фильтр выключен. Иначе: без галочки — попадут "
                "только файлы этих расширений (и только включённых "
                "категорий), с галочкой — наоборот, будут исключены."
            ),
            wraplength=1020,
            justify="left",
        ).pack(anchor="w")

        filter_row = ttk.Frame(filter_group)
        filter_row.pack(fill="x", pady=(4, 4))

        ttk.Entry(
            filter_row,
            textvariable=self.ext_filter_var,
        ).pack(
            side="left",
            fill="x",
            expand=True,
        )

        ttk.Checkbutton(
            filter_row,
            text="Исключать выбранные",
            variable=self.ext_exclude_var,
        ).pack(side="left", padx=(8, 0))

        quick = ttk.Frame(filter_group)
        quick.pack(fill="x")

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

        # ----- 4. Исключить каталоги -----
        exclude_group = ttk.LabelFrame(
            frame,
            text="4. Исключить каталоги",
            padding=10,
        )
        exclude_group.pack(fill="x", pady=5)

        ttk.Entry(
            exclude_group,
            textvariable=self.exclude_var,
        ).pack(fill="x")

        ttk.Label(
            exclude_group,
            text="Названия через запятую: node_modules, .git, venv, dist …",
        ).pack(anchor="w", pady=(4, 0))

        # ----- 5. Результат -----
        result_group = ttk.LabelFrame(
            frame,
            text="5. Результат",
            padding=10,
        )
        result_group.pack(fill="x", pady=5)

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
        actions.pack(fill="x", pady=8)

        ttk.Button(
            actions,
            text="СОБРАТЬ КОНТЕКСТ",
            command=self.build,
        ).pack(side="left")

        ttk.Button(
            actions,
            text="📋 Копировать",
            command=self.copy,
        ).pack(side="left", padx=7)

        ttk.Button(
            actions,
            text="💾 Сохранить",
            command=self.save,
        ).pack(side="left")

        ttk.Button(
            actions,
            text="📂 Открыть папку",
            command=self.open_folder,
        ).pack(side="left", padx=7)

        ttk.Label(
            frame,
            textvariable=self.stats_var,
        ).pack(fill="x", pady=(2, 5))

        # ----- Журнал -----
        log_frame = ttk.LabelFrame(
            frame,
            text="Журнал",
            padding=6,
        )
        log_frame.pack(fill="both", expand=True)

        self.log = ScrolledText(
            log_frame,
            height=12,
            wrap="word",
            font=("Consolas", 9),
            state="disabled",
        )
        self.log.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            textvariable=self.status_var,
            relief="sunken",
            anchor="w",
            padding=5,
        ).pack(fill="x", pady=(6, 0))

        self.log_msg("Приложение готово.")

    # ---- Пресеты ----

    def preset_only_tree(self) -> None:
        """Снять всё, кроме структуры каталога."""
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
        """Вернуть исходный набор галочек."""
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

    # ---- Утилиты ----

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

    # ---- Действия ----

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

        self.log_msg(f"Корень: {root}")
        self.status_var.set("Сканирование проекта…")

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
            )
        except Exception as exc:
            self.status_var.set("Ошибка.")
            messagebox.showerror(
                APP_TITLE,
                f"Не удалось собрать контекст:\n\n{exc}",
            )
            return

        self.context = context

        if not self.output_var.get().strip():
            self.output_var.set(
                str(root / f"{root.name}_context.txt")
            )

        output_path = Path(self.output_var.get()).expanduser()

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

    def save(self) -> None:
        if not self.context:
            messagebox.showwarning(
                APP_TITLE,
                "Сначала соберите контекст.",
            )
            return

        output_text = self.output_var.get().strip()

        if not output_text:
            chosen = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt")],
            )

            if not chosen:
                return

            output_text = chosen
            self.output_var.set(chosen)

        output_path = Path(output_text).expanduser()

        if self._write_context(output_path):
            self.status_var.set("Файл сохранён.")
            self.log_msg(f"Сохранено: {output_path}")

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