python - <<'PY'
from pathlib import Path

p = Path("gui.py")
s = p.read_text(encoding="utf-8")

# 1) Добавляем обратный словарь метка → ключ
old = '''CHANGED_KEY_TO_LABEL = {key: label for key, label in CHANGED_MODES_STATIC}'''
new = '''CHANGED_KEY_TO_LABEL = {key: label for key, label in CHANGED_MODES_STATIC}
CHANGED_LABEL_TO_KEY = {label: key for key, label in CHANGED_MODES_STATIC}'''
if new not in s:
    assert old in s, "gui.py: CHANGED_KEY_TO_LABEL definition not found"
    s = s.replace(old, new, 1)

# 2) В _on_changed_mode_changed сверяем метку с метками, а не с ключами
old = '''    def _on_changed_mode_changed(self) -> None:
        label = self.changed_only_display_var.get()

        if label in CHANGED_KEY_TO_LABEL:
            self._changed_mode = CHANGED_KEY_TO_LABEL[label]
            self._changed_commit_hash = None
            self._changed_commit_subject = ""
        else:'''
new = '''    def _on_changed_mode_changed(self) -> None:
        label = self.changed_only_display_var.get()

        if label in CHANGED_LABEL_TO_KEY:
            self._changed_mode = CHANGED_LABEL_TO_KEY[label]
            self._changed_commit_hash = None
            self._changed_commit_subject = ""
        else:'''
if new not in s:
    assert old in s, "gui.py: _on_changed_mode_changed block not found"
    s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("gui.py: patched")
PY