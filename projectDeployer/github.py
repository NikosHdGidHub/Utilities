"""Publish the committed project, checkpointing confirmed remote creation."""
import re
from dataclasses import dataclass

from common import Command, DeploymentError, prepare_command, run_command


def valid_name(name):
    return isinstance(name, str) and name not in (".", "..") and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name)


@dataclass
class Publication:
    name: str
    public: bool = False
    created_url: str = ""

    def publish(self, directory, log):
        def run(*args):
            lines = []
            def receive(line):
                log(line)
                lines.append(line)
            run_command(prepare_command(Command(args[0], args), {}), directory, receive)
            return lines[1:]

        if not valid_name(self.name):
            raise DeploymentError("Недопустимое имя репозитория GitHub")
        run("gh", "auth", "status", "--hostname", "github.com")
        response = run("gh", "api", "--hostname", "github.com", "user", "--jq", ".login")
        owner = response[-1].strip() if response else ""
        if not re.fullmatch(r"[A-Za-z0-9-]+", owner):
            raise DeploymentError("Не удалось определить аккаунт GitHub")
        url = f"https://github.com/{owner}/{self.name}.git"
        if self.created_url and self.created_url != url:
            raise DeploymentError("Аккаунт GitHub изменился")
        remotes = run("git", "remote")
        if "origin" in remotes:
            urls = run("git", "remote", "get-url", "--push", "--all", "origin")
            if not self.created_url or urls != [url]:
                raise DeploymentError("origin уже существует. Проверьте адрес перед публикацией.")
        if not self.created_url:
            run("gh", "api", "--hostname", "github.com", "--method", "POST", "user/repos",
                "-f", f"name={self.name}", "-F", f"private={str(not self.public).lower()}", "--silent")
            self.created_url = url
        if "origin" not in remotes:
            run("git", "remote", "add", "origin", url)
        run("git", "-c", "credential.https://github.com.helper=",
            "-c", "credential.https://github.com.helper=!gh auth git-credential", "push", "-u", "origin", "main")
