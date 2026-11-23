# {{project_name}} · Python

Выполняйте команды из папки проекта.

## Python

- Windows PowerShell: `.\.venv\Scripts\Activate.ps1`
- Linux / macOS: `source .venv/bin/activate`
- Запуск: `python main.py`
- Список библиотек: `python -m pip list`. Удаление: `python -m pip uninstall имя-пакета`.
- Установить пакет: `python -m pip install имя-пакета`
- Сохранить список зависимостей: `python -m pip freeze > requirements.txt`
- Установить зависимости из списка: `python -m pip install -r requirements.txt`
- Выйти из окружения: `deactivate`

Если PowerShell запрещает активацию, запускайте команды напрямую, например
`.\.venv\Scripts\python.exe main.py`.

## Git

- `git status` — посмотреть изменения.
- `git diff` — посмотреть правки перед добавлением.
- `git add .` и `git commit -m "Описание изменения"` — сохранить новые изменения.
- `git switch -c feature/my-change` — создать рабочую ветку после первого коммита.
- `git switch main` — вернуться в main.
- `git log --oneline` — посмотреть историю.
- `git remote add origin URL` и `git push -u origin main` — отправить main в созданный удалённый репозиторий.

## GitHub CLI

`gh auth status` показывает текущую авторизацию. Для входа выполните `gh auth login`.
`gh repo view --web` открывает опубликованный репозиторий. Для первой публикации
из каталога с коммитом используйте `gh repo create ИМЯ --private --source=. --remote=origin --push`.
Если Git просит указать автора, задайте `git config user.name "Имя"` и `git config user.email "Почта"`.
