python - <<'PY'
from pathlib import Path

p = Path("gui.py")
s = p.read_text(encoding="utf-8")

# --- (1) Кнопка ↻ рядом с комбобоксом ---
old = '''        ttk.Label(
            changed_row,
            textvariable=self.changed_warning_var,
            foreground="#B8860B",  # тёмно-золотой, читается на белом
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(10, 0))

        # Строка под селектором: предупреждение «git не найден»'''
new = '''        ttk.Label(
            changed_row,
            textvariable=self.changed_warning_var,
            foreground="#B8860B",  # тёмно-золотой, читается на белом
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(10, 0))

        ttk.Button(
            changed_row,
            text="↻",
            width=3,
            command=self._on_manual_git_refresh,
        ).pack(side="left", padx=(10, 0))

        # Строка под селектором: предупреждение «git не найден»'''
if new not in s:
    assert old in s, "gui.py: warning label + git_row header not found"
    s = s.replace(old, new, 1)

# --- (2) FocusIn на главном окне: обновляем при возврате фокуса ---
old = '''        self.bind("<Control-Return>", self._on_hotkey_build)
        # На macOS принят Cmd+Enter.
        self.bind("<Command-Return>", self._on_hotkey_build)'''
new = '''        self.bind("<Control-Return>", self._on_hotkey_build)
        # На macOS принят Cmd+Enter.
        self.bind("<Command-Return>", self._on_hotkey_build)

        # При возврате фокуса на главное окно перечитываем git-состояние:
        # пользователь мог сделать новый коммит в терминале / IDE.
        # Дебаунс внутри _schedule_git_refresh() защищает от лишних
        # вызовов git при переключении между виджетами.
        self.bind("<FocusIn>", self._on_app_focus_in, add="+")'''
if new not in s:
    assert old in s, "gui.py: hotkey bind block not found"
    s = s.replace(old, new, 1)

# --- (3) Обработчики: FocusIn + ручное обновление ---
old = '''    def _schedule_git_refresh(self) -> None:
        if self._git_refresh_after_id is not None:
            self.after_cancel(self._git_refresh_after_id)
        self._git_refresh_after_id = self.after(
            400, self._refresh_git_state
        )
'''
new = '''    def _on_app_focus_in(self, event) -> None:
        # FocusIn всплывает от любого дочернего виджета — реагируем
        # только на фокус самого окна.
        if event.widget is not self:
            return
        self._schedule_git_refresh()

    def _on_manual_git_refresh(self) -> None:
        # Ручное обновление: без дебаунса, сразу.
        if self._git_refresh_after_id is not None:
            self.after_cancel(self._git_refresh_after_id)
            self._git_refresh_after_id = None
        self._refresh_git_state()

    def _schedule_git_refresh(self) -> None:
        if self._git_refresh_after_id is not None:
            self.after_cancel(self._git_refresh_after_id)
        self._git_refresh_after_id = self.after(
            400, self._refresh_git_state
        )
'''
if new not in s:
    assert old in s, "gui.py: _schedule_git_refresh block not found"
    s = s.replace(old, new, 1)

# --- (4) _apply_git_state: сохраняем текущий выбор по хешу ---
old = '''        # Восстановление сохранённого коммита — один раз при первом
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
        self._update_changed_count_inline()'''
new = '''        # Восстановление сохранённого коммита — один раз при первом
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

        # Периодическое обновление (фокус / кнопка ↻):
        # метка содержит относительное время («2 ч назад»), которое
        # со временем меняется — поэтому сверяем по хешу и
        # переустанавливаем метку. Иначе выбор «слетит» из-за
        # устаревшего текста.
        elif (
            reason == "ok"
            and self._changed_mode == git_utils.MODE_SINCE_COMMIT
            and self._changed_commit_hash
        ):
            matched = next(
                (c for c in commits
                 if c["hash"] == self._changed_commit_hash),
                None,
            )
            if matched is not None:
                self.changed_only_display_var.set(matched["label"])
            else:
                self.log_msg(
                    f"Коммит «{self._changed_commit_subject}» больше "
                    "не в списке последних 15 — режим сброшен "
                    "на «Выключено»."
                )
                self._changed_mode = "off"
                self._changed_commit_hash = None
                self._changed_commit_subject = ""
                self.changed_only_display_var.set(
                    CHANGED_KEY_TO_LABEL["off"]
                )

        self._update_changed_warning()
        self._update_changed_count_inline()'''
if new not in s:
    assert old in s, "gui.py: _apply_git_state restore block not found"
    s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("gui.py: patched")
PY