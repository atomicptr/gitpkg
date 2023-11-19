import os
from pathlib import Path

import pytest
import tomllib
from _pytest.capture import CaptureFixture

from gitpkg.cli import CLI
from tests.git_composer import GitComposer


def assert_destination_exists(toml: Path, name: str) -> None:
    assert toml.exists()

    data = tomllib.loads(toml.read_text())
    assert "destinations" in data
    assert len(data["destinations"]) > 0
    assert len(list(filter(lambda d: d["name"] == name, data["destinations"]))) > 0


def assert_package_exists(toml: Path, dest: str, pkg: str) -> None:
    assert toml.exists()

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

    def test_register_destination(self, capsys: CaptureFixture[str]):
        repo = self._git.create_repository("test_repo")
        os.chdir(repo.path())
        vendor_dir = repo.path() / "vendor"
        vendor_dir.mkdir(parents=True, exist_ok=True)

        cli = CLI()
        cli.run([__file__, "dest:register", vendor_dir.name])

        toml_path = vendor_dir / ".." / ".gitpkg.toml"

        assert toml_path.exists()

        assert_destination_exists(toml_path, "vendor")

        cli.run([__file__, "dest:list"])
        captured = capsys.readouterr()

        assert "vendor" in captured.out
        assert "test_repo" in captured.out

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

    def test_add_package_multiple_destinations(self):
        remote_repo = self._git.create_repository("remote_repo")
        remote_repo.commit_new_file("yolo.txt")

        repo = self._git.create_repository("test_repo")
        os.chdir(repo.path())

        cli = CLI()

        vendor_dir1 = repo.path() / "libs"
        vendor_dir1.mkdir(parents=True, exist_ok=True)
        cli.run([__file__, "dest:register", "libs"])

        vendor_dir2 = repo.path() / "vendor"
        vendor_dir2.mkdir(parents=True, exist_ok=True)
        cli.run([__file__, "dest:register", "vendor"])

        toml_path = repo.path() / ".gitpkg.toml"

        assert_destination_exists(toml_path, "libs")
        assert_destination_exists(toml_path, "vendor")

        # test with no dest should raise error
        with pytest.raises(SystemExit) as err:
            cli.run([__file__, "add", str(remote_repo.path().absolute())])
        assert err.type == SystemExit
        assert err.value.code == 1

        # installing at both places should work
        cli.run(
            [__file__, "add", str(remote_repo.path().absolute()), "--dest-name", "libs"]
        )
        cli.run(
            [
                __file__,
                "add",
                str(remote_repo.path().absolute()),
                "--dest-name",
                "vendor",
            ]
        )

        assert_package_exists(toml_path, "libs", "remote_repo")
        assert_package_exists(toml_path, "vendor", "remote_repo")

        # installing same package again should cause error
        with pytest.raises(SystemExit) as err:
            cli.run(
                [
                    __file__,
                    "add",
                    str(remote_repo.path().absolute()),
                    "--dest-name",
                    "libs",
                ]
            )
        assert err.type == SystemExit
        assert err.value.code == 1

        with pytest.raises(SystemExit) as err:
            cli.run(
                [
                    __file__,
                    "add",
                    str(remote_repo.path().absolute()),
                    "--dest-name",
                    "vendor",
                ]
            )
        assert err.type == SystemExit
        assert err.value.code == 1

    def test_add_package_with_one_destination(self):
        remote_repo = self._git.create_repository("remote_repo")
        remote_repo.commit_new_file("404.txt")
        remote_repo.commit_new_file("subdir/yolo.txt")

        repo = self._git.create_repository("test_repo")
        os.chdir(repo.path())

        cli = CLI()

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        cli.run([__file__, "dest:register", "libs"])

        toml_path = repo.path() / ".gitpkg.toml"

        cli.run([__file__, "add", str(remote_repo.path().absolute()), "-r", "subdir"])

        assert_destination_exists(toml_path, "libs")
        assert_package_exists(toml_path, "libs", "remote_repo")

        # test if subdir works
        assert (repo.path() / "libs" / "remote_repo" / "yolo.txt").exists()
        assert not (repo.path() / "libs" / "remote_repo" / "404.txt").exists()

        # try to install from unknown dest
        with pytest.raises(SystemExit) as err:
            cli.run(
                [
                    __file__,
                    "add",
                    str(remote_repo.path().absolute()),
                    "--dest-name",
                    "unknown",
                ]
            )
        assert err.type == SystemExit
        assert err.value.code == 1


# TODO: test cmd: list
# TODO: test cmd: remove
# TODO: test cmd: install, with nothing present
# TODO: test cmd: install, with only .gitpkg/... part deleted
# TODO: test cmd: install, with only .gitmodules part deleted
# TODO: test cmd: update
# TODO: test cmd: update, with local changes
