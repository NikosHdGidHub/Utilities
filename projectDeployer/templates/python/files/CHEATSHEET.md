# {{project_name}} · Python

Выполняйте команды из папки проекта.

## Python

- Windows PowerShell: `.\.venv\Scripts\Activate.ps1`
- Linux / macOS: `source .venv/bin/activate`
- Запуск: `python main.py`
- Тесты: `python -m unittest discover -v`
- Установить пакет: `python -m pip install имя-пакета`
- Сохранить список зависимостей: `python -m pip freeze > requirements.txt`
- Установить зависимости из списка: `python -m pip install -r requirements.txt`
- Выйти из окружения: `deactivate`

Если PowerShell запрещает активацию, запускайте команды напрямую, например
`.\.venv\Scripts\python.exe main.py`.

## Git

- `git status` — посмотреть изменения.
- `git diff` — посмотреть правки перед добавлением.
- `git add .` и `git commit -m "Initial commit"` — создать первый коммит в main.
- `git switch -c feature/my-change` — создать рабочую ветку после первого коммита.
- `git switch main` — вернуться в main.
- `git log --oneline` — посмотреть историю.
- `git remote add origin URL` и `git push -u origin main` — отправить main в созданный удалённый репозиторий.
