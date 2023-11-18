from __future__ import annotations

import random
import shutil
import tempfile
from hashlib import sha3_256
from pathlib import Path
from typing import ClassVar

from git import Repo


class GitComposer:
    temp_dir: Path

    to_be_deleted: ClassVar[list[Path]] = []

    def setup(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="gitpkg_tests"))
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def teardown(self):
        GitComposer.to_be_deleted.append(self.temp_dir)

    def create_repository(self, name: str) -> GitComposerRepo:
        repo_path = self.temp_dir / name
        repo = GitComposerRepo(Repo.init(repo_path), repo_path)

        repo.commit_new_file("test.txt")
        repo.change_file("test.txt")
        repo.commit_new_file("test2.txt")
        repo.change_file("test2.txt")

        return repo

    @staticmethod
    def cleanup():
        for directory in GitComposer.to_be_deleted:
            shutil.rmtree(directory)


class GitComposerRepo:
    _repo: Repo
    _path: Path

    def __init__(self, repo: Repo, path: Path):
        self._repo = repo
        self._path = path

    def path(self) -> Path:
        return self._path

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

        index = random.randint(0, len(lines) - 1)
        lines[index] = _random_str()
        filepath.write_text("\n".join(lines))

        self._repo.index.add([str(filepath)])
        self._repo.index.commit(f"update {filename}")


def _random_str() -> str:
    hasher = sha3_256()
    hasher.update(str(random.randint(0, 1000000)).encode("utf-8"))
    return hasher.hexdigest()
