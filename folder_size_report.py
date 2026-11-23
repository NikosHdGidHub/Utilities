"""Отчёт о размерах вложенных папок. Python 3.8+, только стандартная библиотека.

Запуск (Windows): py folder_size_report.py
"""

import os
import queue
import stat
import tempfile
import threading
import time
from datetime import datetime
from tkinter import BOTH, LEFT, StringVar, Tk, filedialog, messagebox, ttk


class Folder:
    __slots__ = (
        "files",
        "folders",
        "name",
        "own_size",
        "path",
        "read_error",
        "total_size",
    )

    def __init__(self, name, path):
        self.name = name
        self.path = path
        self.folders = []
        self.files = []
        self.own_size = 0
        self.total_size = 0
        self.read_error = False


class ScanCancelled(Exception):
    pass


def format_size(size):
    units = ("Б", "КиБ", "МиБ", "ГиБ", "ТиБ", "ПиБ")
    val = float(size)
    index = 0
    while val >= 1024 and index < len(units) - 1:
        val /= 1024
        index += 1
    return f"{size} {units[0]}" if index == 0 else f"{val:.2f} {units[index]}"


def add_issue(issues, errors, path, reason):
    errors[0] += 1
    if len(issues) < 100:
        issues.append(f"{path} — {reason}")


def scan_tree(root_path, include_files, cancel, progress=None):
    """Один обход дерева; ссылки на каталоги не открываются."""
    name = os.path.basename(os.path.normpath(root_path)) or root_path
    root = Folder(name, root_path)
    pending = [root]
    all_folders = []
    issues = []
    error_count = [0]
    skipped_links = 0
    files_count = 0
    last_progress = 0.0
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

    while pending:
        if cancel.is_set():
            raise ScanCancelled()
        folder = pending.pop()
        all_folders.append(folder)
        try:
            with os.scandir(folder.path) as iterator:
                for entry in iterator:
                    if cancel.is_set():
                        raise ScanCancelled()
                    try:
                        info = entry.stat(follow_symlinks=False)
                        is_dir = stat.S_ISDIR(info.st_mode)
                        # Windows junctions / reparse directories, symbolic links:
                        # do not follow: they may point back into the tree or outside it.
                        is_reparse_directory = is_dir and bool(
                            getattr(info, "st_file_attributes", 0) & reparse_flag
                        )
                        if stat.S_ISLNK(info.st_mode) or is_reparse_directory:
                            skipped_links += 1
                            continue
                        if is_dir:
                            child = Folder(entry.name, entry.path)
                            folder.folders.append(child)
                            pending.append(child)
                        elif stat.S_ISREG(info.st_mode):
                            file_bytes = max(0, info.st_size)
                            folder.own_size += file_bytes
                            files_count += 1
                            if include_files:
                                folder.files.append((entry.name, file_bytes))
                    except OSError as exc:
                        add_issue(issues, error_count, entry.path, str(exc))
        except ScanCancelled:
            raise
        except OSError as exc:
            folder.read_error = True
            add_issue(issues, error_count, folder.path, str(exc))

        now = time.monotonic()
        if progress is not None and now - last_progress > 0.35:
            progress(len(all_folders), files_count)
            last_progress = now

    # Bottom-up: папки агрегируют размеры файлов и дочерних папок.
    for folder in reversed(all_folders):
        folder.total_size = folder.own_size + sum(
            child.total_size for child in folder.folders
        )
    if progress is not None:
        progress(len(all_folders), files_count)
    return root, len(all_folders), files_count, skipped_links, error_count[0], issues


def write_report(output_path, scanned_path, include_files, result, cancel):
    root, n_folders, n_files, n_links, n_errors, issues = result
    out_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(out_dir, exist_ok=True)
    # Запись в промежуточный файл: отмена не оставит неполный отчёт.
    fd, tmp_path = tempfile.mkstemp(prefix="folder_report_", suffix=".tmp", dir=out_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="\n") as out:
            out.write("ОТЧЁТ О РАЗМЕРАХ ПАПОК\n")
            out.write("Дата: {}\n".format(datetime.now().strftime("%d.%m.%Y %H:%M:%S")))
            out.write(f"Путь: {scanned_path}\n")
            out.write(
                "Режим: {}\n".format(
                    "Папки + файлы"
                    if include_files
                    else "Только папки (файлы учитываются в размере)"
                )
            )
            out.write(
                "Размер: {} ({} байт)\n".format(
                    format_size(root.total_size),
                    f"{root.total_size:,}".replace(",", " "),
                )
            )
            out.write(f"Найдено папок: {n_folders}, файлов: {n_files}\n")
            out.write(
                f"Пропущено ссылок/системных переходов: {n_links}; ошибок чтения: {n_errors}\n"
            )
            out.write(
                "Примечание: это логические размеры файлов, не точный объём на диске.\n"
            )
            out.write(
                "Ссылки и точки соединения каталогов не обходятся, чтобы не считать данные дважды.\n"
            )
            out.write("Папки и файлы отсортированы по убыванию размера.\n")
            if n_errors:
                out.write(
                    "ВНИМАНИЕ: из-за ошибок доступа некоторые размеры могут быть занижены.\n"
                )
            out.write("\nСТРУКТУРА\n")
            out.write(
                "[ПАПКА] {} — {} ({} байт); файлы прямо здесь: {}{}\n".format(
                    root.name,
                    format_size(root.total_size),
                    root.total_size,
                    format_size(root.own_size),
                    " [НЕ ПОЛНОСТЬЮ ПРОЧИТАНА]" if root.read_error else "",
                )
            )

            def push_items(folder, prefix, stack):
                directories = sorted(
                    folder.folders, key=lambda x: (-x.total_size, x.name.casefold())
                )
                items = [("dir", x) for x in directories]
                if include_files:
                    items.extend(
                        ("file", x)
                        for x in sorted(
                            folder.files, key=lambda x: (-x[1], x[0].casefold())
                        )
                    )
                for i in range(len(items) - 1, -1, -1):
                    kind, item = items[i]
                    stack.append((kind, item, prefix, i == len(items) - 1))

            stack = []
            push_items(root, "", stack)
            written = 0
            while stack:
                if cancel.is_set():
                    raise ScanCancelled()
                kind, item, prefix, is_last = stack.pop()
                branch = "└── " if is_last else "├── "
                if kind == "dir":
                    suffix = " [НЕ ПОЛНОСТЬЮ ПРОЧИТАНА]" if item.read_error else ""
                    out.write(
                        f"{prefix}{branch}[ПАПКА] {item.name} — {format_size(item.total_size)} ({item.total_size} байт); файлы прямо здесь: {format_size(item.own_size)}{suffix}\n"
                    )
                    next_prefix = prefix + ("    " if is_last else "│   ")
                    push_items(item, next_prefix, stack)
                else:
                    filename, size = item
                    out.write(
                        f"{prefix}{branch}[ФАЙЛ] {filename} — {format_size(size)} ({size} байт)\n"
                    )
                written += 1
                if written % 5000 == 0 and cancel.is_set():
                    raise ScanCancelled()

            if n_errors:
                out.write("\nОШИБКИ (первые 100)\n")
                for issue in issues:
                    out.write(f"- {issue}\n")
                if n_errors > len(issues):
                    out.write(f"... и ещё {n_errors - len(issues)} ошибок\n")
        if cancel.is_set():
            raise ScanCancelled()
        os.replace(tmp_path, output_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


class App:
    def __init__(self, window):
        self.window = window
        window.title("Отчёт о размерах папок")
        window.geometry("720x390")
        window.minsize(650, 340)
        self.folder = StringVar()
        self.output = StringVar()
        self.mode = StringVar(value="dirs")
        self.status = StringVar(value="Выберите папку для анализа.")
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        window.columnconfigure(0, weight=1)

        frame = ttk.Frame(window, padding=16)
        frame.pack(fill=BOTH, expand=True)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Папка для сканирования:").grid(
            row=0, column=0, sticky="w"
        )
        rr = ttk.Frame(frame)
        rr.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        rr.columnconfigure(0, weight=1)
        ttk.Entry(rr, textvariable=self.folder).grid(row=0, column=0, sticky="ew")
        ttk.Button(rr, text="Обзор…", command=self.choose_folder).grid(
            row=0, column=1, padx=(10, 0)
        )

        ttk.Label(frame, text="Состав текстового отчёта:").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Radiobutton(
            frame,
            text="Только папки (размеры включают файлы внутри)",
            variable=self.mode,
            value="dirs",
        ).grid(row=3, column=0, sticky="w", pady=(4, 2))
        ttk.Radiobutton(
            frame,
            text="Папки и все файлы (подробный отчёт)",
            variable=self.mode,
            value="all",
        ).grid(row=4, column=0, sticky="w", pady=(2, 12))

        ttk.Label(frame, text="Сохранить отчёт в:").grid(row=5, column=0, sticky="w")
        oo = ttk.Frame(frame)
        oo.grid(row=6, column=0, sticky="ew", pady=(4, 10))
        oo.columnconfigure(0, weight=1)
        ttk.Entry(oo, textvariable=self.output).grid(row=0, column=0, sticky="ew")
        ttk.Button(oo, text="Обзор…", command=self.choose_output).grid(
            row=0, column=1, padx=(10, 0)
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, sticky="w", pady=(0, 8))
        self.start_button = ttk.Button(buttons, text="Сканировать", command=self.start)
        self.start_button.pack(side=LEFT)
        self.stop_button = ttk.Button(
            buttons, text="Отмена", command=self.stop, state="disabled"
        )
        self.stop_button.pack(side=LEFT, padx=(12, 0))
        ttk.Label(frame, textvariable=self.status, wraplength=665).grid(
            row=8, column=0, sticky="w"
        )

        window.after(150, self.process_events)
        window.protocol("WM_DELETE_WINDOW", self.on_close)

    def choose_folder(self):
        path = filedialog.askdirectory(title="Выберите папку")
        if path:
            self.folder.set(path)
            if not self.output.get():
                destination = os.path.join(os.path.expanduser("~"), "Documents")
                if not os.path.isdir(destination):
                    destination = os.path.expanduser("~")
                name = "folder_sizes_{}.txt".format(
                    datetime.now().strftime("%Y%m%d_%H%M%S")
                )
                self.output.set(os.path.join(destination, name))

    def choose_output(self):
        path = filedialog.asksaveasfilename(
            title="Куда сохранить отчёт",
            defaultextension=".txt",
            filetypes=[("Текстовый файл", "*.txt"), ("Все файлы", "*.*")],
            initialfile=os.path.basename(self.output.get()) or "folder_sizes.txt",
        )
        if path:
            self.output.set(path)

    def start(self):
        target = os.path.abspath(
            os.path.expandvars(os.path.expanduser(self.folder.get().strip()))
        )
        outfile = os.path.abspath(
            os.path.expandvars(os.path.expanduser(self.output.get().strip()))
        )
        if not self.folder.get().strip() or not os.path.isdir(target):
            messagebox.showerror("Ошибка", "Выберите существующую папку.")
            return
        if not self.output.get().strip():
            messagebox.showerror("Ошибка", "Выберите путь для текстового отчёта.")
            return
        if os.path.normcase(target) == os.path.normcase(outfile):
            messagebox.showerror(
                "Ошибка", "Путь отчёта должен указывать на файл, а не на папку."
            )
            return
        if os.path.exists(outfile) and not messagebox.askyesno(
            "Подтверждение", "Отчёт уже существует. Перезаписать его?"
        ):
            return
        self.cancel.clear()
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.status.set("Сканирование…")
        include_files = self.mode.get() == "all"
        self.worker = threading.Thread(
            target=self.work, args=(target, outfile, include_files), daemon=True
        )
        self.worker.start()

    def work(self, target, outfile, include_files):
        try:

            def progress(dirs, files):
                self.events.put(("progress", (dirs, files)))

            result = scan_tree(target, include_files, self.cancel, progress)
            self.events.put(("progress_text", "Сканирование завершено. Запись отчёта…"))
            write_report(outfile, target, include_files, result, self.cancel)
            self.events.put(
                ("done", (outfile, result[0].total_size, result[1], result[2]))
            )
        except ScanCancelled:
            self.events.put(("cancelled", None))
        except Exception as exc:  # noqa: BLE001
            self.events.put(("error", str(exc)))

    def stop(self):
        self.cancel.set()
        self.stop_button.config(state="disabled")
        self.status.set("Остановка сканирования…")

    def process_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "progress" and not self.cancel.is_set():
                    self.status.set(
                        "Обработано папок: {:,}; файлов: {:,}".format(*value).replace(
                            ",", " "
                        )
                    )
                elif kind == "progress_text":
                    self.status.set(value)
                elif kind in ("done", "cancelled", "error"):
                    self.start_button.config(state="normal")
                    self.stop_button.config(state="disabled")
                    if kind == "done":
                        path, size, ndirs, nfiles = value
                        self.status.set(
                            f"Готово. Папок: {ndirs}; файлов: {nfiles}; размер: {format_size(size)}"
                        )
                        messagebox.showinfo("Отчёт создан", f"Файл сохранён:\n{path}")
                    elif kind == "cancelled":
                        self.status.set(
                            "Сканирование отменено, неполный отчёт не сохранён."
                        )
                    else:
                        self.status.set(f"Ошибка: {value}")
                        messagebox.showerror("Ошибка", value)
        except queue.Empty:
            pass
        self.window.after(150, self.process_events)

    def on_close(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(
                "Сканирование идёт", "Сначала нажмите «Отмена» и дождитесь остановки."
            )
            return
        self.window.destroy()


def main():
    window = Tk()
    App(window)
    window.mainloop()


if __name__ == "__main__":
    main()
