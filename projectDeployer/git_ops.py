from common import Command


def steps():
    return (
        Command("Создать ветку main", ("git", "init", "--initial-branch=main")),
        Command("Проверьте git config user.name", ("git", "config", "--get", "user.name")),
        Command("Проверьте git config user.email", ("git", "config", "--get", "user.email")),
        Command("Добавить файлы", ("git", "add", "--all")),
        Command("Создать первый коммит", ("git", "commit", "-m", "Initial commit")),
    )
