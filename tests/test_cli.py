import os
from pathlib import Path

import tomllib

from gitpkg.cli import CLI
from tests.git_composer import GitComposer


def assert_destination_exists(toml: Path, name: str) -> None:
    data = tomllib.loads(toml.read_text())
    assert "destinations" in data
    assert len(data["destinations"]) > 0
    assert len(list(filter(lambda d: d["name"] == name, data["destinations"]))) > 0


def assert_package_exists(toml: Path, dest: str, pkg: str) -> None:
    data = tomllib.loads(toml.read_text())
    assert "packages" in data
    assert dest in data["packages"]
    assert len(list(filter(lambda p: p["name"] == pkg, data["packages"][dest]))) > 0


class TestCLI:
    _git: GitComposer

    def setup_method(self):
        self._git = GitComposer()
        self._git.setup()

    def teardown_method(self):
        self._git.teardown()

    def test_register_destination(self):
        repo = self._git.create_repository("test_repo")
        os.chdir(repo.path())
        vendor_dir = repo.path() / "vendor"
        vendor_dir.mkdir(parents=True, exist_ok=True)

        cli = CLI()
        cli.run([__file__, "dest:register", vendor_dir.name])

        toml_path = vendor_dir / ".." / ".gitpkg.toml"

        assert toml_path.exists()

        assert_destination_exists(toml_path, "vendor")

    def test_add_package(self):
        remote_repo = self._git.create_repository("remote_repo")
        remote_repo.commit_new_file("yolo.txt")

        repo = self._git.create_repository("test_repo")
        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        cli = CLI()
        cli.run([__file__, "add", str(remote_repo.path().absolute())])

        toml_path = vendor_dir / ".." / ".gitpkg.toml"

        assert toml_path.exists()

        assert_destination_exists(toml_path, "libs")
        assert_package_exists(toml_path, "libs", "remote_repo")
