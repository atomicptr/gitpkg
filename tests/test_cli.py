import os
import shutil
import sys
from pathlib import Path

import pytest

if sys.version_info < (3, 11):
    import tomli as tomllib  # pragma: no cover
else:
    import tomllib  # pragma: no cover

from _pytest.capture import CaptureFixture

from gitpkg.cli import CLI
from gitpkg.config import Config
from tests.git_composer import GitComposer, checksum


def assert_toml_dest_exists(toml: Path, name: str) -> None:
    assert toml.exists()

    data = tomllib.loads(toml.read_text())
    assert "destinations" in data
    assert len(data["destinations"]) > 0
    assert len(list(filter(lambda d: d["name"] == name, data["destinations"]))) > 0


def assert_toml_pkg_exists(toml: Path, dest: str, pkg: str) -> None:
    assert toml.exists()

    data = tomllib.loads(toml.read_text())
    assert "packages" in data
    assert dest in data["packages"]
    assert len(list(filter(lambda p: p["name"] == pkg, data["packages"][dest]))) > 0


class TestCLI:
    _git: GitComposer

    def setup_method(self, method):
        self._git = GitComposer()
        self._git.setup(method.__name__)

    def teardown_method(self):
        self._git.teardown()

    def test_register_destination(self, capsys: CaptureFixture[str]):
        repo = self._git.create_repository("test_repo")
        os.chdir(repo.path())
        vendor_dir = repo.path() / "vendor"
        vendor_dir.mkdir(parents=True, exist_ok=True)

        cli = CLI()

        cli.run([__file__, "dest:list"])

        captured = capsys.readouterr()
        assert "No destinations" in captured.out

        cli.run([__file__, "dest:register", vendor_dir.name])

        toml_path = vendor_dir / ".." / ".gitpkg.toml"

        assert toml_path.exists()

        assert_toml_dest_exists(toml_path, "vendor")

        cli.run([__file__, "dest:list"])
        captured = capsys.readouterr()

        assert "vendor" in captured.out
        assert "test_repo" in captured.out
        assert not repo.is_corrupted()

    def test_add_package(self):
        remote_repo = self._git.create_repository("remote_repo")
        remote_repo.new_file("yolo.txt")

        repo = self._git.create_repository("test_repo")
        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        cli = CLI()
        cli.run([__file__, "add", str(remote_repo.path().absolute())])

        toml_path = vendor_dir / ".." / ".gitpkg.toml"

        assert toml_path.exists()

        assert_toml_dest_exists(toml_path, "libs")
        assert_toml_pkg_exists(toml_path, "libs", "remote_repo")

        assert (vendor_dir / "remote_repo").exists()

        # must be relative path, regression  test for #8
        remote_repo_install_link = Path(os.readlink(vendor_dir / "remote_repo"))
        assert not remote_repo_install_link.is_absolute()
        assert (vendor_dir / remote_repo_install_link).exists()

        assert not repo.is_corrupted()

    def test_add_package_multiple_destinations(self):
        remote_repo = self._git.create_repository("remote_repo")
        remote_repo.new_file("yolo.txt")

        repo = self._git.create_repository("test_repo")
        os.chdir(repo.path())

        cli = CLI()

        libs_dir = repo.path() / "libs"
        libs_dir.mkdir(parents=True, exist_ok=True)
        cli.run([__file__, "dest:register", "libs"])

        vendor_dir = repo.path() / "vendor"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        cli.run([__file__, "dest:register", "vendor"])

        toml_path = repo.path() / ".gitpkg.toml"

        assert_toml_dest_exists(toml_path, "libs")
        assert_toml_dest_exists(toml_path, "vendor")

        # test with no dest should raise error
        with pytest.raises(SystemExit) as err:
            cli.run([__file__, "add", str(remote_repo.path().absolute())])
        assert err.type == SystemExit
        assert err.value.code == 1

        # installing at both places should work
        cli.run(
            [__file__, "add", str(remote_repo.path().absolute()), "--dest-name", "libs"]
        )
        # repo should be there
        assert (libs_dir / "remote_repo").exists()

        cli.run(
            [
                __file__,
                "add",
                str(remote_repo.path().absolute()),
                "--dest-name",
                "vendor",
            ]
        )
        # repo should be there
        assert (vendor_dir / "remote_repo").exists()

        # other repo  should also still be there
        assert (libs_dir / "remote_repo").exists()

        assert_toml_pkg_exists(toml_path, "libs", "remote_repo")
        assert_toml_pkg_exists(toml_path, "vendor", "remote_repo")

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
        assert not repo.is_corrupted()

    def test_add_package_with_one_destination(self):
        remote_repo = self._git.create_repository("remote_repo")
        remote_repo.new_file("404.txt")
        remote_repo.new_file("subdir/yolo.txt")

        repo = self._git.create_repository("test_repo")
        os.chdir(repo.path())

        cli = CLI()

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        cli.run([__file__, "dest:register", "libs"])

        toml_path = repo.path() / ".gitpkg.toml"

        cli.run([__file__, "add", str(remote_repo.path().absolute()), "-r", "subdir"])

        assert_toml_dest_exists(toml_path, "libs")
        assert_toml_pkg_exists(toml_path, "libs", "remote_repo")

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
        assert not repo.is_corrupted()

    def test_add_with_non_existent_package_root(self):
        remote_repo = self._git.create_repository("remote_repo")
        remote_repo.new_file("yolo.txt")

        repo = self._git.create_repository("test_repo")
        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        cli = CLI()

        with pytest.raises(SystemExit) as err:
            cli.run(
                [__file__, "add", str(remote_repo.path().absolute()), "-rn", "subdir"]
            )
        assert err.type == SystemExit
        assert err.value.code == 1

        dep_path = vendor_dir / "subdir"

        assert not dep_path.exists()

    def test_add_non_existant_repo(self):
        repo = self._git.create_repository("test_repo")
        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        remote_repo = repo.path().parent / "fake_remote_repo"

        cli = CLI()

        with pytest.raises(Exception) as err:
            cli.run([__file__, "add", str(remote_repo.absolute()), "-rn", "subdir"])

        dep_path = vendor_dir / "subdir"

        assert not dep_path.exists()

    def test_list_packages(self, capsys: CaptureFixture[str]):
        deps = []

        for i in range(10):
            dep = self._git.create_repository(f"dep_{str(i).zfill(3)}")
            dep.new_file(f"{str(i).zfill(3)}.txt")

            deps.append(dep)

        repo = self._git.create_repository("test_repo")

        os.chdir(repo.path())

        cli = CLI()
        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        cli.run([__file__, "dest:register", "libs"])

        cli.run([__file__, "list"])
        captured = capsys.readouterr()

        assert "No packages" in captured.out

        for dep in deps:
            cli.run([__file__, "add", str(dep.path().absolute())])

        cli.run([__file__, "list"])

        captured = capsys.readouterr()

        for dep in deps:
            assert dep.path().name in captured.out
        assert not repo.is_corrupted()

    def test_remove(self):
        dep_a = self._git.create_repository("depA")
        dep_b = self._git.create_repository("depB")

        repo = self._git.create_repository("test_repo")
        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        cli = CLI()
        cli.run([__file__, "add", str(dep_a.path().absolute())])
        cli.run([__file__, "add", str(dep_b.path().absolute())])

        toml_path = repo.path() / ".gitpkg.toml"

        assert_toml_dest_exists(toml_path, "libs")
        assert_toml_pkg_exists(toml_path, "libs", "depA")
        assert_toml_pkg_exists(toml_path, "libs", "depB")

        cli.run([__file__, "remove", "depA"])

        assert_toml_pkg_exists(toml_path, "libs", "depB")

        data = tomllib.loads(toml_path.read_text())
        packages = data.get("packages", {}).get("libs", [])

        assert len(list(filter(lambda pkg: pkg["name"] == "depA", packages))) == 0
        assert not repo.is_corrupted()

    def test_remove_with_multiple_dests(self):
        dep_a = self._git.create_repository("depA")
        dep_b = self._git.create_repository("depB")

        repo = self._git.create_repository("test_repo")
        os.chdir(repo.path())

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        vendor_dir2 = repo.path() / "lib2"
        vendor_dir2.mkdir(parents=True, exist_ok=True)

        cli = CLI()

        cli.run([__file__, "dest:register", "libs"])
        cli.run([__file__, "dest:register", "libs2"])

        cli.run([__file__, "add", str(dep_a.path().absolute()), "--dest-name", "libs"])
        cli.run([__file__, "add", str(dep_b.path().absolute()), "--dest-name", "libs2"])

        toml_path = repo.path() / ".gitpkg.toml"

        assert_toml_dest_exists(toml_path, "libs")
        assert_toml_dest_exists(toml_path, "libs2")

        assert_toml_pkg_exists(toml_path, "libs", "depA")
        assert_toml_pkg_exists(toml_path, "libs2", "depB")

        cli.run([__file__, "remove", "depA"])

        assert_toml_pkg_exists(toml_path, "libs2", "depB")

        data = tomllib.loads(toml_path.read_text())

        assert (
            len(
                list(
                    filter(
                        lambda pkg: pkg["name"] == "depA",
                        data.get("packages", {}).get("libs", []),
                    )
                )
            )
            == 0
        )
        assert (
            len(
                list(
                    filter(
                        lambda pkg: pkg["name"] == "depA",
                        data.get("packages", {}).get("libs2", []),
                    )
                )
            )
            == 0
        )
        assert not repo.is_corrupted()

    def test_remote_with_one_dependency_in_multiple_destinations(self):
        the_one = self._git.create_repository("the_one")

        repo = self._git.create_repository("test_repo")
        os.chdir(repo.path())

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        vendor_dir2 = repo.path() / "lib2"
        vendor_dir2.mkdir(parents=True, exist_ok=True)

        cli = CLI()

        cli.run([__file__, "dest:register", "libs"])
        cli.run([__file__, "dest:register", "libs2"])

        cli.run(
            [__file__, "add", str(the_one.path().absolute()), "--dest-name", "libs"]
        )
        cli.run(
            [__file__, "add", str(the_one.path().absolute()), "--dest-name", "libs2"]
        )

        toml_path = repo.path() / ".gitpkg.toml"

        assert_toml_dest_exists(toml_path, "libs")
        assert_toml_dest_exists(toml_path, "libs2")

        assert_toml_pkg_exists(toml_path, "libs", "the_one")
        assert_toml_pkg_exists(toml_path, "libs2", "the_one")

        with pytest.raises(SystemExit) as err:
            cli.run([__file__, "remove", "the_one"])
        assert err.type == SystemExit
        assert err.value.code == 1

        cli.run([__file__, "remove", "libs2/the_one"])

        assert_toml_pkg_exists(toml_path, "libs", "the_one")

        data = tomllib.loads(toml_path.read_text())

        assert (
            len(
                list(
                    filter(
                        lambda pkg: pkg["name"] == "the_one",
                        data.get("packages", {}).get("libs2", []),
                    )
                )
            )
            == 0
        )
        assert not repo.is_corrupted()

    def test_install_with_config_changes(self):
        dep_a = self._git.create_repository("depA")
        dep_a.new_file("a/b/c/swag.txt")
        dep_b = self._git.create_repository("depB")
        dep_b.new_file("d/e/f/42.txt")

        repo = self._git.create_repository("test_repo")

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        cli = CLI()

        cli.run([__file__, "add", str(dep_a.path().absolute())])
        cli.run([__file__, "add", str(dep_b.path().absolute())])

        os.chdir(repo.path())

        toml_file = repo.path() / ".gitpkg.toml"

        config = Config.from_path(toml_file)

        packages = []

        for pkg in config.packages.get("libs", []):
            if pkg.name == "depA":
                pkg.package_root = "a/b/c"
                packages.append(pkg)
                continue
            if pkg.name == "depB":
                pkg.package_root = "d/e/f"
                packages.append(pkg)
                continue

        config.packages["libs"] = packages

        toml_file.write_text(config.to_toml_string())

        cli.run([__file__, "install"])

        assert not (repo.path() / "libs" / "depA" / "test.txt").exists()
        assert (repo.path() / "libs" / "depA" / "swag.txt").exists()
        assert not (repo.path() / "libs" / "depB" / "test.txt").exists()
        assert (repo.path() / "libs" / "depB" / "42.txt").exists()
        assert not repo.is_corrupted()

    def test_install_with_everything_deleted(self):
        dep_a = self._git.create_repository("depA")
        dep_b = self._git.create_repository("depB")

        repo = self._git.create_repository("test_repo")

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        cli = CLI()

        cli.run([__file__, "add", str(dep_a.path().absolute())])
        cli.run([__file__, "add", str(dep_b.path().absolute())])

        os.chdir(repo.path())

        gitmodules = repo.path() / ".gitmodules"
        gitpkgs = repo.path() / ".gitpkgs"
        internal_dir = repo.path() / ".git" / "modules"

        shutil.rmtree(internal_dir)
        internal_dir.mkdir()
        shutil.rmtree(gitpkgs)
        gitmodules.unlink()

        cli.run([__file__, "install"])

        assert gitmodules.exists()
        assert gitpkgs.exists()
        assert (vendor_dir / "depA").exists()
        assert (vendor_dir / "depB").exists()
        assert not repo.is_corrupted()

    def test_install_with_only_internal_dir_deleted(self):
        dep_a = self._git.create_repository("depA")
        dep_b = self._git.create_repository("depB")

        repo = self._git.create_repository("test_repo")

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        cli = CLI()

        cli.run([__file__, "add", str(dep_a.path().absolute())])
        cli.run([__file__, "add", str(dep_b.path().absolute())])

        os.chdir(repo.path())

        gitmodules = repo.path() / ".gitmodules"
        gitpkgs = repo.path() / ".gitpkgs"
        internal_dir = repo.path() / ".git" / "modules"

        shutil.rmtree(internal_dir)
        internal_dir.mkdir()

        cli.run([__file__, "install"])

        assert gitmodules.exists()
        assert gitpkgs.exists()
        assert (vendor_dir / "depA").exists()
        assert (vendor_dir / "depB").exists()
        assert not repo.is_corrupted()

    def test_install_with_only_gitmodules_deleted(self):
        dep_a = self._git.create_repository("depA")
        dep_b = self._git.create_repository("depB")

        repo = self._git.create_repository("test_repo")

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        cli = CLI()

        cli.run([__file__, "add", str(dep_a.path().absolute())])
        cli.run([__file__, "add", str(dep_b.path().absolute())])

        os.chdir(repo.path())

        gitmodules = repo.path() / ".gitmodules"
        gitpkgs = repo.path() / ".gitpkgs"
        internal_dir = repo.path() / ".git" / "modules"

        gitmodules.unlink()

        cli.run([__file__, "install"])

        assert gitmodules.exists()
        assert gitpkgs.exists()
        assert (vendor_dir / "depA").exists()
        assert (vendor_dir / "depB").exists()
        assert not repo.is_corrupted()

    def test_install_with_only_gitpkgs_deleted(self):
        dep_a = self._git.create_repository("depA")
        dep_b = self._git.create_repository("depB")

        repo = self._git.create_repository("test_repo")

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        cli = CLI()

        cli.run([__file__, "add", str(dep_a.path().absolute())])
        cli.run([__file__, "add", str(dep_b.path().absolute())])

        os.chdir(repo.path())

        gitmodules = repo.path() / ".gitmodules"
        gitpkgs = repo.path() / ".gitpkgs"

        shutil.rmtree(gitpkgs)

        cli.run([__file__, "install"])

        assert gitmodules.exists()
        assert gitpkgs.exists()
        assert (vendor_dir / "depA").exists()
        assert (vendor_dir / "depB").exists()
        assert not repo.is_corrupted()

    def test_update(self):
        dep_a = self._git.create_repository("depA")
        dep_b = self._git.create_repository("depB")

        repo = self._git.create_repository("test_repo")

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        cli = CLI()

        cli.run([__file__, "add", str(dep_a.path().absolute())])
        cli.run([__file__, "add", str(dep_b.path().absolute())])

        os.chdir(repo.path())

        dep_a.new_file("updated.txt")

        updated_file = vendor_dir / "depA" / "updated.txt"

        assert not updated_file.exists()

        cli.run([__file__, "update"])

        assert updated_file.exists()

    def test_update_with_changes(self):
        dep_a = self._git.create_repository("depA")
        dep_a.new_file("new_file.txt")
        dep_b = self._git.create_repository("depB")

        repo = self._git.create_repository("test_repo")

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        cli = CLI()

        cli.run([__file__, "add", str(dep_a.path().absolute())])
        cli.run([__file__, "add", str(dep_b.path().absolute())])

        os.chdir(repo.path())

        dep_a.new_file("updated.txt")

        new_file = vendor_dir / "depA" / "new_file.txt"

        new_file_before_change = checksum(new_file)
        new_file.write_text("CHANGED!")
        new_file_after_change = checksum(new_file)

        untracked_file = vendor_dir / "depB" / "untracked.txt"
        untracked_file.write_text("UNTRACKED")

        assert checksum(new_file) == new_file_after_change

        cli.run([__file__, "update", "depA"])

        assert checksum(new_file) == new_file_after_change

        cli.run([__file__, "update", "depA", "--force"])

        assert checksum(new_file) == new_file_before_change

        assert untracked_file.exists()

        cli.run([__file__, "update", "--force"])

        assert not untracked_file.exists()

    def test_update_with_disabled_updates(self):
        dep_a = self._git.create_repository("depA")
        dep_b = self._git.create_repository("depB")

        repo = self._git.create_repository("test_repo")

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        cli = CLI()

        cli.run([__file__, "add", str(dep_a.path().absolute()), "--disable-updates"])
        cli.run([__file__, "add", str(dep_b.path().absolute())])

        os.chdir(repo.path())

        dep_a.new_file("updated.txt")
        dep_a.change_file("updated.txt")
        dep_a.change_file("updated.txt")

        dep_b.new_file("updated.txt")
        dep_b.change_file("updated.txt")

        dep_a_updated_file = vendor_dir / "depA" / "updated.txt"
        dep_b_updated_file = vendor_dir / "depB" / "updated.txt"

        assert not dep_a_updated_file.exists()
        assert not dep_b_updated_file.exists()

        cli.run([__file__, "update"])

        assert not dep_a_updated_file.exists()
        assert dep_b_updated_file.exists()


# TODO: test cmd: update, with commited changes locally but not on upstream
