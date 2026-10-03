# Project Context Builder

Desktop-приложение на Python для сбора контекста проекта в один TXT-файл.

## Структура

- `main.py` — точка запуска приложения.
- `gui.py` — графический интерфейс на Tkinter.
- `core.py` — логика сканирования, фильтрации и формирования контекста.

## Запуск

```powershell
python main.py
```

## Сборка EXE

```powershell
pyinstaller --onefile --windowed main.py
```

Готовый файл появится в `dist/`.

## Зависимости

Используется только стандартная библиотека Python.
