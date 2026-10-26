python - <<'PY'
from pathlib import Path

# ============ core.py ============
p = Path("core.py")
s = p.read_text(encoding="utf-8")

# Убираем старую проверку OUTPUT_NAMES (она стояла после конфигов)
old = '''    if name in OUTPUT_NAMES:
        return "output"

    if suffix in TEXT_EXTENSIONS:
        return "text"'''
new = '''    if suffix in TEXT_EXTENSIONS:
        return "text"'''
assert old in s, "core.py: old OUTPUT_NAMES block not found"
s = s.replace(old, new, 1)

# Вставляем проверку OUTPUT_NAMES ПЕРЕД конфигами
old2 = '''    if suffix in STYLE_EXTENSIONS:
        return "style"

    if (
        name in DOTFILE_CONFIG_NAMES'''
new2 = '''    if suffix in STYLE_EXTENSIONS:
        return "style"

    # Lock-файлы (package-lock.json, yarn.lock, pnpm-lock.yaml,
    # poetry.lock, Pipfile.lock) — это отдельная категория "output",
    # а не "config". Расширение у них бывает .json / .yaml / .lock,
    # но по смыслу это lock-файлы зависимостей. Проверяем ДО конфигов,
    # чтобы категория "output" работала независимо от конфигов.
    if name in OUTPUT_NAMES:
        return "output"

    if (
        name in DOTFILE_CONFIG_NAMES'''
assert old2 in s, "core.py: config block not found"
s = s.replace(old2, new2, 1)

p.write_text(s, encoding="utf-8")
print("core.py: patched")

# ============ gui.py ============
p = Path("gui.py")
s = p.read_text(encoding="utf-8")

# (1) добавляем переменную для предупреждения
old = '''        self.changed_count_var = tk.StringVar(value="")
        self._changed_count_after_id: str | None = None'''
new = '''        self.changed_count_var = tk.StringVar(value="")
        self.changed_warning_var = tk.StringVar(value="")
        self._changed_count_after_id: str | None = None'''
assert old in s, "gui.py: changed_count_var block not found"
s = s.replace(old, new, 1)

# (2) добавляем Label в строку «Только изменённые»
old = '''        ttk.Label(
            changed_row,
            textvariable=self.changed_count_var,
            foreground="#666666",
        ).pack(side="left", padx=(10, 0))

                # ----- 3. Промпт -----'''
new = '''        ttk.Label(
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

                # ----- 3. Промпт -----'''
assert old in s, "gui.py: changed_row label block not found"
s = s.replace(old, new, 1)

# (3) _on_changed_mode_changed + новый метод _update_changed_warning
old = '''    def _on_changed_mode_changed(self) -> None:
        label = self.changed_only_display_var.get()
        self._changed_mode = CHANGED_LABEL_TO_KEY.get(label, "off")
        self._schedule_changed_count_update()
        self._schedule_autosave()'''
new = '''    def _on_changed_mode_changed(self) -> None:
        label = self.changed_only_display_var.get()
        self._changed_mode = CHANGED_LABEL_TO_KEY.get(label, "off")
        self._update_changed_warning()
        self._schedule_changed_count_update()
        self._schedule_autosave()

    def _update_changed_warning(self) -> None:
        if self._changed_mode == "off":
            self.changed_warning_var.set("")
        else:
            self.changed_warning_var.set(
                "⚠  Внимание — в сборку попадут не все файлы!"
            )'''
assert old in s, "gui.py: _on_changed_mode_changed not found"
s = s.replace(old, new, 1)

# (4) вызываем при инициализации — чтобы предупреждение появилось,
#     если режим сохранён из прошлого запуска
old = '''        self.root_var.trace_add("write", _on_root_changed)
        self._schedule_changed_count_update()
        self._update_prompt_status()'''
new = '''        self.root_var.trace_add("write", _on_root_changed)
        self._schedule_changed_count_update()
        self._update_prompt_status()
        self._update_changed_warning()'''
assert old in s, "gui.py: init-end block not found"
s = s.replace(old, new, 1)

# (5) обновляем в _reset_all_settings (на случай, если set() не вызовет trace)
old = '''        self._changed_mode = mode
        self.changed_only_display_var.set(CHANGED_KEY_TO_LABEL[mode])'''
new = '''        self._changed_mode = mode
        self.changed_only_display_var.set(CHANGED_KEY_TO_LABEL[mode])
        self._update_changed_warning()'''
assert old in s, "gui.py: _reset_all_settings changed block not found"
s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("gui.py: patched")
PY