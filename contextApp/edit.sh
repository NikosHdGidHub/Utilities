python - <<'PY'
from pathlib import Path

# =========================================================
# core.py — одна строка в default_settings()
# =========================================================
p = Path("core.py")
s = p.read_text(encoding="utf-8")

old = '''        "changed_only_mode": "off",
        "prompt_attach_enabled": False,'''
new = '''        "changed_only_mode": "off",
        "changed_commit_subject": "",
        "prompt_attach_enabled": False,'''

if new in s:
    print("core.py: already patched")
else:
    assert old in s, (
        "core.py: default_settings changed_only_mode block not found"
    )
    s = s.replace(old, new, 1)
    p.write_text(s, encoding="utf-8")
    print("core.py: patched")

# =========================================================
# gui.py
# =========================================================
p = Path("gui.py")
s = p.read_text(encoding="utf-8")

# --- (1) Константы: только два статических режима ---
old = '''# Режимы фильтра «только изменённые»: (ключ, отображаемая метка).
CHANGED_MODES: tuple[tuple[str, str], ...] = (
    ("off", "Выключено"),
    ("uncommitted", "Незакоммиченные"),
    ("since_last_commit", "Из последнего коммита"),
    ("last_2_commits", "Последние 2 коммита"),
    ("yesterday", "Вчера"),
    ("day_before_yesterday", "Позавчера"),
)

CHANGED_LABEL_TO_KEY = {label: key for key, label in CHANGED_MODES}
CHANGED_KEY_TO_LABEL = {key: label for key, label in CHANGED_MODES}'''
new = '''# Статические режимы фильтра «только изменённые»: (ключ, метка).
# Коммиты добавляются динамически в выпадающий список.
CHANGED_MODES_STATIC: tuple[tuple[str, str], ...] = (
    ("off", "Выключено"),
    ("uncommitted", "Незакоммиченные"),
)

CHANGED_KEY_TO_LABEL = {key: label for key, label in CHANGED_MODES_STATIC}'''
if new not in s:
    assert old in s, "gui.py: CHANGED_MODES block not found"
    s = s.replace(old, new, 1)

# --- (2) __init__: состояние фильтра «только изменённые» ---
old = '''        # Фильтр «только изменённые».
        _initial_mode = str(settings.get("changed_only_mode", "off"))
        if _initial_mode not in CHANGED_KEY_TO_LABEL:
            _initial_mode = "off"
        self._changed_mode = _initial_mode
        self.changed_only_display_var = tk.StringVar(
            value=CHANGED_KEY_TO_LABEL[_initial_mode]
        )
        self.changed_count_var = tk.StringVar(value="")
        self.changed_warning_var = tk.StringVar(value="")
        self._changed_count_after_id: str | None = None'''
new = '''        # Фильтр «только изменённые».
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
        self._changed_count_after_id: str | None = None'''
if new not in s:
    assert old in s, "gui.py: __init__ changed block not found"
    s = s.replace(old, new, 1)

# --- (3) Комбобокс: шире + статические значения ---
old = '''        self.changed_combo = ttk.Combobox(
            changed_row,
            textvariable=self.changed_only_display_var,
            values=[label for _, label in CHANGED_MODES],
            state="readonly",
            width=24,
        )'''
new = '''        self.changed_combo = ttk.Combobox(
            changed_row,
            textvariable=self.changed_only_display_var,
            values=[label for _, label in CHANGED_MODES_STATIC],
            state="readonly",
            width=48,
        )'''
if new not in s:
    assert old in s, "gui.py: changed_combo block not found"
    s = s.replace(old, new, 1)

# --- (4) Строка под селектором: git-warn / git-info ---
old = '''        ttk.Label(
            changed_row,
            textvariable=self.changed_warning_var,
            foreground="#B8860B",  # тёмно-золотой, читается на белом
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(10, 0))

                # ----- 3. Промпт -----'''
new = '''        ttk.Label(
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

                # ----- 3. Промпт -----'''
if new not in s:
    assert old in s, "gui.py: warning label + prompt header block not found"
    s = s.replace(old, new, 1)

# --- (5) Инициализация: schedule_git_refresh вместо счётчика, сброс при смене root ---
old = '''        def _on_root_changed(*_) -> None:
            self._schedule_changed_count_update()
            self._update_prompt_status()

        self.root_var.trace_add("write", _on_root_changed)
        self._schedule_changed_count_update()
        self._update_prompt_status()
        self._update_changed_warning()'''
new = '''        def _on_root_changed(*_) -> None:
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
        self._update_changed_warning()'''
if new not in s:
    assert old in s, "gui.py: _on_root_changed init block not found"
    s = s.replace(old, new, 1)

# --- (6) _on_changed_mode_changed + новые методы git-состояния ---
old = '''    def _on_changed_mode_changed(self) -> None:
        label = self.changed_only_display_var.get()
        self._changed_mode = CHANGED_LABEL_TO_KEY.get(label, "off")
        self._update_changed_warning()
        self._schedule_changed_count_update()
        self._schedule_autosave()
'''
new = '''    def _on_changed_mode_changed(self) -> None:
        label = self.changed_only_display_var.get()

        if label in CHANGED_KEY_TO_LABEL:
            self._changed_mode = CHANGED_KEY_TO_LABEL[label]
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
'''
if new not in s:
    assert old in s, "gui.py: _on_changed_mode_changed not found"
    s = s.replace(old, new, 1)

# --- (7) _update_changed_count: обёртка + inline-версия ---
old = '''    def _update_changed_count(self) -> None:
        self._changed_count_after_id = None

        if self._changed_mode == "off":
            self.changed_count_var.set("")
            return

        root_text = self.root_var.get().strip()
        if not root_text:
            self.changed_count_var.set("—")
            return

        root = Path(root_text).expanduser()
        if not root.is_dir():
            self.changed_count_var.set("—")
            return

        if git_utils.get_repo_root(root) is None:
            self.changed_count_var.set("не git-репозиторий")
            return

        try:
            changed = git_utils.get_changed_files(root, self._changed_mode)
        except Exception as exc:
            self.changed_count_var.set(f"ошибка: {exc}")
            return

        if changed is None:
            self.changed_count_var.set("")
        elif not changed:
            self.changed_count_var.set("нет изменений")
        else:
            self.changed_count_var.set(f"{len(changed)} файл(ов)")
'''
new = '''    def _update_changed_count(self) -> None:
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
'''
if new not in s:
    assert old in s, "gui.py: _update_changed_count block not found"
    s = s.replace(old, new, 1)

# --- (8) _get_changed_files_for_build ---
old = '''    def _get_changed_files_for_build(
        self, root: Path
    ) -> tuple[set[Path] | None, str | None]:
        """Возвращает (set, label) для передачи в build_context."""
        if self._changed_mode == "off":
            return None, None

        try:
            changed = git_utils.get_changed_files(root, self._changed_mode)
        except Exception:
            changed = set()

        if changed is None:
            return None, None

        label = CHANGED_KEY_TO_LABEL.get(
            self._changed_mode, self._changed_mode
        )
        return changed, f"git: {label.lower()}"
'''
new = '''    def _get_changed_files_for_build(
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
'''
if new not in s:
    assert old in s, "gui.py: _get_changed_files_for_build not found"
    s = s.replace(old, new, 1)

# --- (9) _collect_settings: сохраняем subject ---
old = '''            "changed_only_mode": self._changed_mode,
            "prompt_attach_enabled": self.prompt_attach_var.get(),'''
new = '''            "changed_only_mode": self._changed_mode,
            "changed_commit_subject": self._changed_commit_subject,
            "prompt_attach_enabled": self.prompt_attach_var.get(),'''
if new not in s:
    assert old in s, "gui.py: _collect_settings changed_only_mode not found"
    s = s.replace(old, new, 1)

# --- (10) _reset_all_settings ---
old = '''        mode = str(defaults.get("changed_only_mode", "off"))
        if mode not in CHANGED_KEY_TO_LABEL:
            mode = "off"
        self._changed_mode = mode
        self.changed_only_display_var.set(CHANGED_KEY_TO_LABEL[mode])
        self._update_changed_warning()'''
new = '''        mode = str(defaults.get("changed_only_mode", "off"))
        if mode not in CHANGED_KEY_TO_LABEL:
            mode = "off"
        self._changed_mode = mode
        self._changed_commit_hash = None
        self._changed_commit_subject = ""
        self._pending_commit_restore = False
        self.changed_only_display_var.set(CHANGED_KEY_TO_LABEL[mode])
        self._update_changed_warning()'''
if new not in s:
    assert old in s, "gui.py: _reset_all_settings changed block not found"
    s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("gui.py: patched")
PY