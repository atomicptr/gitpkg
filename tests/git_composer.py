from __future__ import annotations

import random
import tempfile
from hashlib import sha3_256
from pathlib import Path

from git import Repo


class GitComposer:
    temp_dir: tempfile.TemporaryDirectory

    def path(self) -> Path:
        return Path(self.temp_dir.name)

    def setup(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="gitpkg_tests")
        self.path().mkdir(parents=True, exist_ok=True)

    def teardown(self):
        self.temp_dir.cleanup()

    def create_repository(self, name: str) -> GitComposerRepo:
        repo_path = self.path() / name
        repo = GitComposerRepo(Repo.init(repo_path), repo_path)

        repo.commit_new_file("test.txt")
        repo.change_file("test.txt")
        repo.commit_new_file("test2.txt")
        repo.change_file("test2.txt")

        return repo


class GitComposerRepo:
    _repo: Repo
    _path: Path

    def __init__(self, repo: Repo, path: Path):
        self._repo = repo
        self._path = path

    def abs(self) -> Path:
        return self._path.absolute()

    def commit_new_file(self, filename: str, message: str = None):
        filepath = self._path / filename

        lines = [_random_str() for _ in range(100)]
        filepath.write_text("\n".join(lines))

        self._repo.index.add(filename)

        if not message:
            message = f"add {filename}"

        self._repo.index.commit(message)

    def change_file(self, filename: str):
        filepath = self._path / filename

        lines = filepath.read_text().splitlines()

        index = random.randint(0, len(lines))
        lines[index] = _random_str()
        filepath.write_text("\n".join(lines))

        self._repo.index.add(filename)
        self._repo.index.commit(f"update {filename}")


def _random_str() -> str:
    hasher = sha3_256()
    hasher.update(
        str(random.randint(0, 1000000)).encode("utf-8")
    )
    return hasher.hexdigest()
