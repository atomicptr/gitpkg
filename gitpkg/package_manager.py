from pathlib import Path

from git import Repo


class PackageManager:
    _repo: Repo

    def __init__(self, repo: Repo):
        self._repo = repo

    @staticmethod
    def from_environment():
        repo = Repo(Path.cwd(), search_parent_directories=True)
        return PackageManager(repo)