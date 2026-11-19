"""Merge selected PDF files into one PDF. Requires: pip install pypdf"""

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

try:
    from pypdf import PdfWriter
except ImportError:
    print("Не найдена библиотека pypdf. Установите её: python -m pip install pypdf")
    sys.exit(1)


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        files = filedialog.askopenfilenames(
            parent=root,
            title="Выберите PDF-файлы для объединения",
            filetypes=[("PDF-файлы", "*.pdf")],
        )
        if not files:
            return

        output = filedialog.asksaveasfilename(
            parent=root,
            title="Сохранить объединённый PDF",
            defaultextension=".pdf",
            initialfile="merged.pdf",
            filetypes=[("PDF-файлы", "*.pdf")],
        )
        if not output:
            return

        destination = Path(output).resolve()
        if destination in (Path(f).resolve() for f in files):
            messagebox.showerror(
                "Ошибка",
                "Результат нельзя сохранить поверх одного из исходных файлов.",
                parent=root,
            )
            return

        writer = PdfWriter()
        try:
            for file in files:
                writer.append(file)
            with destination.open("wb") as target:
                writer.write(target)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ошибка объединения", str(exc), parent=root)
            return
        finally:
            writer.close()

        messagebox.showinfo(
            "Готово",
            f"Объединено файлов: {len(files)}\nРезультат: {destination}",
            parent=root,
        )
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
