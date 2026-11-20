"""Tk interface for choosing presets and monitoring project creation."""

from __future__ import annotations

import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font, messagebox, ttk

from deployer import (
    BUNDLED_TEMPLATES,
    DeploymentError,
    Preset,
    deploy,
    load_presets,
    project_variables,
    render,
    user_templates,
)


BACKGROUND = "#eef2f7"
PANEL = "#ffffff"
INK = "#17243a"
MUTED = "#4c5b70"
ACCENT = "#2456cc"
HEADER = "#162744"
INLINE_CODE = re.compile(r"`([^`]+)`")


class App(tk.Tk):
    def __init__(self, presets: list[Preset] | None = None) -> None:
        super().__init__()
        self.title("Развёртывание проектов")
        self.geometry("940x720")
        self.minsize(790, 630)
        self.configure(background=BACKGROUND)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.busy = False
        self.automatic_folder = True
        self.syncing_folder = False

        self.name = tk.StringVar(self)
        self.folder = tk.StringVar(self)
        self.parent = tk.StringVar(self, str(Path.home()))
        self.status = tk.StringVar(self, "Готово к созданию проекта")
        self.preset_description = tk.StringVar(self)
        self.controls: list[ttk.Widget] = []
        self.ui_font = font.nametofont("TkDefaultFont", root=self).actual("family")
        self.presets, errors = (
            load_presets(BUNDLED_TEMPLATES, user_templates())
            if presets is None else (presets, [])
        )
        self.configure_styles()
        self.build_interface()
        self.name.trace_add("write", self.name_changed)
        self.folder.trace_add("write", self.folder_changed)
        if self.presets:
            self.preset_list.selection_set(0)
            self.show_preset()
            self.name_entry.focus_set()
        else:
            self.status.set("Нет доступных шаблонов")
            self.create_button.state(["disabled"])
        if errors:
            self.append_log("Не удалось загрузить шаблоны:\n" + "\n".join(errors))
            self.tabs.select(self.log_tab)

    def configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BACKGROUND)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BACKGROUND, foreground=INK, font=(self.ui_font, 10))
        style.configure("Panel.TLabel", background=PANEL)
        style.configure("Section.TLabel", background=PANEL, font=(self.ui_font, 11, "bold"))
        style.configure("Hint.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Status.TLabel", foreground=MUTED)
        style.configure("TEntry", foreground=INK, bordercolor="#bdc8db", padding=(8, 6))
        style.configure("TButton", padding=(10, 6), foreground=INK, background="#e9eef7",
                        bordercolor="#c6d1e3", lightcolor="#e9eef7", darkcolor="#e9eef7")
        style.configure("Primary.TButton", padding=(17, 10), background=ACCENT, foreground="white",
                        bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
        style.map("Primary.TButton", background=[
            ("disabled", "#d5deee"), ("pressed", "#163a96"), ("active", "#204bb2"),
        ], foreground=[("disabled", MUTED)])
        style.configure("TNotebook", background=PANEL, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 7), background="#e9eef7")
        style.map("TNotebook.Tab", foreground=[("selected", ACCENT)], background=[("selected", PANEL)])
        style.configure("Vertical.TScrollbar", background="#dce4f2", troughcolor="#eef2f7",
                        bordercolor="#dce4f2", lightcolor="#dce4f2", darkcolor="#dce4f2")
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#dbe5f7")

    def build_interface(self) -> None:
        header = tk.Frame(self, bg=HEADER, padx=24, pady=16)
        header.pack(fill="x")
        tk.Label(
            header, text="Развёртывание проектов", bg=HEADER, fg="white",
            font=(self.ui_font, 21, "bold"),
        ).pack(anchor="w")

        footer = ttk.Frame(self, padding=(22, 0, 22, 16))
        footer.pack(side="bottom", fill="x")
        self.create_button = ttk.Button(
            footer, text="Создать проект", style="Primary.TButton", command=self.start_deployment,
        )
        self.create_button.pack(side="right")
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=95)
        self.status_label = ttk.Label(footer, textvariable=self.status, style="Status.TLabel",
                                      wraplength=480)
        self.status_label.pack(side="left", fill="x", expand=True)

        body = ttk.Frame(self, padding=(20, 18))
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        sidebar = ttk.Frame(body, style="Panel.TFrame", padding=16)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        ttk.Label(sidebar, text="Шаблоны", style="Section.TLabel").pack(anchor="w", pady=(0, 12))

        choices = ttk.Frame(sidebar, style="Panel.TFrame")
        choices.pack(fill="x")
        self.preset_list = tk.Listbox(
            choices, width=27, height=7, bg="#f3f6fc", fg=INK, borderwidth=0,
            highlightthickness=1, highlightbackground="#d8e0ef", highlightcolor=ACCENT,
            selectbackground=ACCENT, selectforeground="white", activestyle="none",
            exportselection=False, font=(self.ui_font, 10),
        )
        scroll = ttk.Scrollbar(choices, orient="vertical", command=self.preset_list.yview)
        self.preset_list.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.preset_list.pack(side="left", fill="both", expand=True)
        for preset in self.presets:
            self.preset_list.insert("end", preset.name)
        self.preset_list.bind("<<ListboxSelect>>", self.show_preset)
        ttk.Label(
            sidebar, textvariable=self.preset_description, style="Hint.TLabel", wraplength=205,
            justify="left",
        ).pack(anchor="w", pady=(14, 0))

        panel = ttk.Frame(body, style="Panel.TFrame", padding=18)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(7, weight=1)
        self.name_entry = self.add_field(panel, 0, "Название проекта", self.name)
        self.add_field(panel, 2, "Имя папки проекта", self.folder, "Как название", self.use_project_name)
        self.add_field(panel, 4, "Родительский каталог", self.parent, "Обзор…", self.choose_parent)

        self.tabs = ttk.Notebook(panel)
        self.tabs.grid(row=7, column=0, sticky="nsew", pady=(14, 0))
        cheatsheet_tab, self.cheatsheet = self.add_text_tab("Шпаргалка")
        self.log_tab, self.log = self.add_text_tab("Журнал")
        self.tabs.select(cheatsheet_tab)

    def add_field(
        self, panel: ttk.Frame, row: int, label: str, variable: tk.StringVar,
        button_text: str = "", command=None,
    ) -> ttk.Entry:
        ttk.Label(panel, text=label, style="Panel.TLabel").grid(
            row=row, column=0, sticky="w", pady=(5, 4),
        )
        line = ttk.Frame(panel, style="Panel.TFrame")
        line.grid(row=row + 1, column=0, sticky="ew", pady=(0, 3))
        entry = ttk.Entry(line, textvariable=variable)
        entry.pack(side="left", fill="x", expand=True)
        self.controls.append(entry)
        if command:
            button = ttk.Button(line, text=button_text, command=command)
            button.pack(side="right", padx=(8, 0))
            self.controls.append(button)
        return entry

    def add_text_tab(self, label: str) -> tuple[ttk.Frame, tk.Text]:
        tab = ttk.Frame(self.tabs, style="Panel.TFrame")
        self.tabs.add(tab, text=label)
        text = tk.Text(
            tab, wrap="word", bg="#f6f8fc", fg=INK, border=0, padx=12, pady=9,
            height=9, width=1, highlightthickness=0, state="disabled", cursor="arrow",
            font=(self.ui_font, 10), spacing1=1, spacing3=2,
        )
        text.tag_configure("heading", foreground=ACCENT, font=(self.ui_font, 10, "bold"))
        text.tag_configure("code", font="TkFixedFont", foreground="#233f75")
        scroll = ttk.Scrollbar(tab, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        return tab, text

    def selected_preset(self) -> Preset | None:
        selection = self.preset_list.curselection()
        return self.presets[selection[0]] if selection else None

    def show_preset(self, _event=None) -> None:
        preset = self.selected_preset()
        if preset is None:
            return
        self.preset_description.set(preset.description)
        variables = project_variables(self.name.get().strip() or "Мой проект", self.folder.get())
        content = render(preset.cheatsheet, variables)
        self.cheatsheet.configure(state="normal")
        self.cheatsheet.delete("1.0", "end")
        for line in content.splitlines():
            if line.startswith("# ") or line.startswith("## "):
                self.cheatsheet.insert("end", line.lstrip("# ") + "\n", "heading")
            else:
                if line.startswith("- "):
                    line = "• " + line[2:]
                for index, segment in enumerate(INLINE_CODE.split(line)):
                    self.cheatsheet.insert("end", segment, "code" if index % 2 else ())
                self.cheatsheet.insert("end", "\n")
        self.cheatsheet.configure(state="disabled")

    def name_changed(self, *_args) -> None:
        if self.automatic_folder:
            self.use_project_name()
        else:
            self.show_preset()

    def folder_changed(self, *_args) -> None:
        if not self.syncing_folder:
            self.automatic_folder = False
        self.show_preset()

    def use_project_name(self) -> None:
        self.automatic_folder = True
        self.syncing_folder = True
        self.folder.set(self.name.get().strip())
        self.syncing_folder = False

    def choose_parent(self) -> None:
        selected = filedialog.askdirectory(parent=self, initialdir=self.parent.get(), mustexist=True)
        if selected:
            self.parent.set(selected)

    def append_log(self, text: str, *, clear: bool = False) -> None:
        self.log.configure(state="normal")
        if clear:
            self.log.delete("1.0", "end")
        if text:
            self.log.insert("end", text + "\n")
            self.log.see("end")
        self.log.configure(state="disabled")

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.preset_list.configure(state="disabled" if busy else "normal")
        for widget in [*self.controls, self.create_button]:
            widget.state(["disabled" if busy else "!disabled"])
        if busy:
            self.progress.pack(side="right", padx=12, before=self.status_label)
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.pack_forget()

    def start_deployment(self) -> None:
        preset = self.selected_preset()
        if self.busy or preset is None:
            return
        values = self.name.get(), self.folder.get(), self.parent.get()
        self.append_log("", clear=True)
        self.tabs.select(self.log_tab)
        self.status.set("Создаю проект…")
        self.set_busy(True)
        threading.Thread(target=self.deploy_in_background, args=(preset, values), daemon=True).start()
        self.after(35, self.receive_events)

    def deploy_in_background(self, preset: Preset, values: tuple[str, str, str]) -> None:
        try:
            destination = deploy(preset, *values, lambda line: self.events.put(("log", line)))
        except DeploymentError as exc:
            self.events.put(("error", str(exc)))
        except Exception as exc:
            self.events.put(("error", f"Ошибка создания проекта: {exc}"))
        else:
            self.events.put(("done", str(destination)))

    def receive_events(self) -> None:
        for _ in range(100):
            try:
                kind, text = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.append_log(text)
                continue
            self.set_busy(False)
            if kind == "done":
                self.append_log(f"Готово. Проект создан: {text}")
                self.status.set("Проект создан · команды в CHEATSHEET.md")
            else:
                self.append_log(text)
                self.status.set("Не удалось создать проект · подробности в журнале")
            return
        self.after(35, self.receive_events)

    def close(self) -> None:
        if self.busy:
            messagebox.showinfo(self.title(), "Дождитесь завершения создания проекта.", parent=self)
        else:
            self.destroy()
