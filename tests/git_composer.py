from __future__ import annotations

import hashlib
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

    def setup(self, prefix_extra: str = ""):
        if len(prefix_extra) > 0:
            prefix_extra += "_"

        self.temp_dir = Path(tempfile.mkdtemp(prefix=f"gitpkg_{prefix_extra}"))
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def teardown(self):
        GitComposer.to_be_deleted.append(self.temp_dir)

    def create_repository(self, name: str) -> GitComposerRepo:
        repo_path = self.temp_dir / name
        repo = GitComposerRepo(Repo.init(repo_path), repo_path)

        repo.new_file("test.txt")
        repo.change_file("test.txt")
        repo.new_file("test2.txt")
        repo.change_file("test2.txt")

        return repo

    @staticmethod
    def cleanup():
        for directory in GitComposer.to_be_deleted:
            shutil.rmtree(directory)

    def __str__(self) -> str:
        return f"GitComposer ({self.temp_dir})"


class GitComposerRepo:
    _repo: Repo
    _path: Path

    def __init__(self, repo: Repo, path: Path):
        self._repo = repo
        self._path = path

    def path(self) -> Path:
        return self._path

    def new_file(self, filename: str, message: str = None):
        filepath = self._path / filename

        filepath.parent.mkdir(exist_ok=True, parents=True)

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

    def file_hash(self, filename: str) -> str:
        filepath = self._path / filename
        return checksum(filepath)

    def is_corrupted(self) -> bool:
        # first to the simplest check...
        if not bool(self._repo.head.commit.hexsha) or not bool(
            self._repo.head.commit.committed_datetime
        ):
            return True

        is_gitpkg_project = (self._path / ".gitpkg.toml").exists()

        # if this is not a gitpkg project probably not even corrupted lol
        if not is_gitpkg_project:
            return False

        packages_dir = self._path / ".gitpkgs"
        git_files = packages_dir.glob("*/.git")

        for git_file in git_files:
            if git_file.is_dir():
                continue

            data = git_file.read_text()

            if not data.startswith("gitdir: "):
                raise ValueError(f"Unknown .git file content found: {data}")

            prefix_len = len("gitdir: ")
            gitdir = git_file.parent / data[prefix_len:]

            if not gitdir.exists():
                return True
        return False

    def __str__(self) -> str:
        return f"GitComposerRepo ({self._path})"


def _random_str() -> str:
    hasher = sha3_256()
    hasher.update(str(random.randint(0, 1000000)).encode("utf-8"))
    return hasher.hexdigest()


def checksum(filepath: Path) -> str:
    hasher = hashlib.sha3_256()
    hasher.update(filepath.read_bytes())
    return hasher.hexdigest()
