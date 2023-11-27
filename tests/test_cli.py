import os
import sys
from pathlib import Path

import pytest

from gitpkg.errors import (
    AmbiguousDestinationError,
    PackageAlreadyInstalledError,
    PackageRootDirNotFoundError,
)
from gitpkg.utils import safe_dir_delete

if sys.version_info < (3, 11):
    import tomli as tomllib  # pragma: no cover
else:
    import tomllib  # pragma: no cover

from _pytest.capture import CaptureFixture

from gitpkg.cli import run_cli as run_cli_raw
from gitpkg.config import Config
from tests.git_composer import GitComposer, checksum


def assert_toml_dest_exists(toml: Path | dict, name: str) -> None:
    if isinstance(toml, Path):
        assert toml.exists()
        toml = tomllib.loads(toml.read_text())

    assert "destinations" in toml
    assert len(toml["destinations"]) > 0
    assert (
        len(list(filter(lambda d: d["name"] == name, toml["destinations"]))) > 0
    )


def assert_toml_pkg_exists(toml: Path | dict, dest: str, pkg: str) -> None:
    if isinstance(toml, Path):
        assert toml.exists()
        toml = tomllib.loads(toml.read_text())

    assert "packages" in toml
    assert dest in toml["packages"]
    assert (
        len(list(filter(lambda p: p["name"] == pkg, toml["packages"][dest])))
        > 0
    )


def run_cli(args: list[str]):
    args = list(map(str, args))
    with pytest.raises(SystemExit) as err:
        run_cli_raw(args)
    if err.value.code != 0:
        raise err


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

        run_cli(["dest", "list"])

        captured = capsys.readouterr()
        assert "No destinations" in captured.out

        run_cli(["dest", "add", vendor_dir])

        toml_path = vendor_dir / ".." / ".gitpkg.toml"

        assert toml_path.exists()

        assert_toml_dest_exists(toml_path, "vendor")

        run_cli(["dest", "list"])
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
        run_cli(["add", str(remote_repo.path().absolute())])

        assert (vendor_dir / "remote_repo").exists()

        toml_path = vendor_dir / ".." / ".gitpkg.toml"

        assert toml_path.exists()
        data = tomllib.loads(toml_path.read_text())

        assert_toml_dest_exists(data, "libs")
        assert_toml_pkg_exists(data, "libs", "remote_repo")

        pkg = data.get("packages", {}).get("libs", [])[0]

        assert pkg is not None
        assert isinstance(pkg, dict)

        # on windows for instance copy is automatically selected so this test
        # would fail
        if pkg.get("install-method") != "copy":
            # must be relative path, regression  test for #8
            remote_repo_install_link = Path(
                vendor_dir / "remote_repo"
            ).readlink()
            assert not remote_repo_install_link.is_absolute()
            assert (vendor_dir / remote_repo_install_link).exists()

        assert not repo.is_corrupted()

    def test_add_package_multiple_destinations(self):
        remote_repo = self._git.create_repository("remote_repo")
        remote_repo.new_file("yolo.txt")

        repo = self._git.create_repository("test_repo")
        os.chdir(repo.path())

        libs_dir = repo.path() / "libs"
        libs_dir.mkdir(parents=True, exist_ok=True)
        run_cli(["dest", "add", "libs"])

        vendor_dir = repo.path() / "vendor"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        run_cli(["dest", "add", "vendor"])

        toml_path = repo.path() / ".gitpkg.toml"

        assert_toml_dest_exists(toml_path, "libs")
        assert_toml_dest_exists(toml_path, "vendor")

        # test with no dest should raise error
        with pytest.raises(AmbiguousDestinationError) as err:
            run_cli(["add", str(remote_repo.path().absolute())])

        # installing at both places should work
        run_cli(
            ["add", str(remote_repo.path().absolute()), "--dest-name", "libs"]
        )
        # repo should be there
        assert (libs_dir / "remote_repo").exists()

        run_cli(
            [
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
        with pytest.raises(PackageAlreadyInstalledError):
            run_cli(
                [
                    "add",
                    str(remote_repo.path().absolute()),
                    "--dest-name",
                    "libs",
                ]
            )

        with pytest.raises(PackageAlreadyInstalledError):
            run_cli(
                [
                    "add",
                    str(remote_repo.path().absolute()),
                    "--dest-name",
                    "vendor",
                ]
            )
        assert not repo.is_corrupted()

    def test_add_package_with_one_destination(self):
        remote_repo = self._git.create_repository("remote_repo")
        remote_repo.new_file("404.txt")
        remote_repo.new_file("subdir/yolo.txt")

        repo = self._git.create_repository("test_repo")
        os.chdir(repo.path())

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        run_cli(["dest", "add", "libs"])

        toml_path = repo.path() / ".gitpkg.toml"

        run_cli(["add", str(remote_repo.path().absolute()), "-r", "subdir"])

        assert_toml_dest_exists(toml_path, "libs")
        assert_toml_pkg_exists(toml_path, "libs", "remote_repo")

        # test if subdir works
        assert (repo.path() / "libs" / "remote_repo" / "yolo.txt").exists()
        assert not (repo.path() / "libs" / "remote_repo" / "404.txt").exists()

        # try to install from unknown dest
        with pytest.raises(AmbiguousDestinationError):
            run_cli(
                [
                    "add",
                    str(remote_repo.path().absolute()),
                    "--dest-name",
                    "unknown",
                ]
            )
        assert not repo.is_corrupted()

    def test_add_with_non_existent_package_root(self):
        remote_repo = self._git.create_repository("remote_repo")
        remote_repo.new_file("yolo.txt")

        repo = self._git.create_repository("test_repo")
        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        with pytest.raises(PackageRootDirNotFoundError):
            run_cli(
                ["add", str(remote_repo.path().absolute()), "-rn", "subdir"]
            )

        dep_path = vendor_dir / "subdir"

        assert not dep_path.exists()
        assert not repo.is_corrupted()

    def test_add_non_existant_repo(self):
        repo = self._git.create_repository("test_repo")
        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        remote_repo = repo.path().parent / "fake_remote_repo"

        with pytest.raises(Exception) as err:
            run_cli(["add", str(remote_repo.absolute()), "-rn", "subdir"])

        dep_path = vendor_dir / "subdir"

        assert not dep_path.exists()
        assert not repo.is_corrupted()

    def test_add_one_repo_multiple_project_roots(self):
        remote_repo = self._git.create_repository("remote_repo")
        remote_repo.new_file("root_a/a.c")
        remote_repo.new_file("root_b/b.c")
        remote_repo.new_file("root_c/c.c")
        remote_repo.new_file("root_d/d.c")
        remote_repo.new_file("root_e/e.c")

        repo = self._git.create_repository("test_repo")
        libs_dir = repo.path() / "libs"
        libs_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(libs_dir)
        run_cli(["add", str(remote_repo.path().absolute()), "-rn", "root_a"])
        run_cli(["add", str(remote_repo.path().absolute()), "-rn", "root_b"])
        run_cli(["add", str(remote_repo.path().absolute()), "-rn", "root_c"])
        run_cli(["add", str(remote_repo.path().absolute()), "-rn", "root_d"])
        run_cli(["add", str(remote_repo.path().absolute()), "-rn", "root_e"])

        toml_path = libs_dir / ".." / ".gitpkg.toml"

        assert toml_path.exists()

        assert_toml_dest_exists(toml_path, "libs")
        assert_toml_pkg_exists(toml_path, "libs", "root_a")
        assert_toml_pkg_exists(toml_path, "libs", "root_b")
        assert_toml_pkg_exists(toml_path, "libs", "root_c")
        assert_toml_pkg_exists(toml_path, "libs", "root_d")
        assert_toml_pkg_exists(toml_path, "libs", "root_e")

        assert (libs_dir / "root_a" / "a.c").exists()
        assert (libs_dir / "root_b" / "b.c").exists()
        assert (libs_dir / "root_c" / "c.c").exists()
        assert (libs_dir / "root_d" / "d.c").exists()
        assert (libs_dir / "root_e" / "e.c").exists()

        assert not repo.is_corrupted()

    def test_add_with_install_method_copy(self):
        remote_repo = self._git.create_repository("remote_repo")
        repo = self._git.create_repository("test_repo")
        os.chdir(repo.path())

        run_cli(["dest", "add", "libs"])
        libs_dir = repo.path() / "libs"

        run_cli(
            ["add", remote_repo.path().absolute(), "--install-method", "copy"]
        )

        dep = libs_dir / "remote_repo"

        assert dep.exists()
        assert (dep / "test.txt").exists()
        assert not dep.is_symlink()

    def test_list_packages(self, capsys: CaptureFixture[str]):
        deps = []

        for i in range(10):
            dep = self._git.create_repository(f"dep_{str(i).zfill(3)}")
            dep.new_file(f"{str(i).zfill(3)}.txt")

            deps.append(dep)

        repo = self._git.create_repository("test_repo")

        os.chdir(repo.path())
        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        run_cli(["dest", "add", "libs"])

        run_cli(["list"])
        captured = capsys.readouterr()

        assert "No packages" in captured.out

        for dep in deps:
            run_cli(["add", str(dep.path().absolute())])

        run_cli(["list"])

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
        run_cli(["add", str(dep_a.path().absolute())])
        run_cli(["add", str(dep_b.path().absolute())])

        toml_path = repo.path() / ".gitpkg.toml"

        assert_toml_dest_exists(toml_path, "libs")
        assert_toml_pkg_exists(toml_path, "libs", "depA")
        assert_toml_pkg_exists(toml_path, "libs", "depB")

        run_cli(["remove", "depA"])

        assert_toml_pkg_exists(toml_path, "libs", "depB")

        data = tomllib.loads(toml_path.read_text())
        packages = data.get("packages", {}).get("libs", [])

        assert (
            len(list(filter(lambda pkg: pkg["name"] == "depA", packages))) == 0
        )
        assert not repo.is_corrupted()

    def test_remove_install_method_copy(self):
        dep_a = self._git.create_repository("depA")
        dep_b = self._git.create_repository("depB")

        repo = self._git.create_repository("test_repo")
        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)
        run_cli(
            ["add", str(dep_a.path().absolute()), "--install-method", "copy"]
        )
        run_cli(
            ["add", str(dep_b.path().absolute()), "--install-method", "copy"]
        )

        toml_path = repo.path() / ".gitpkg.toml"

        assert_toml_dest_exists(toml_path, "libs")
        assert_toml_pkg_exists(toml_path, "libs", "depA")
        assert_toml_pkg_exists(toml_path, "libs", "depB")

        run_cli(["remove", "depA"])

        assert_toml_pkg_exists(toml_path, "libs", "depB")

        data = tomllib.loads(toml_path.read_text())
        packages = data.get("packages", {}).get("libs", [])

        assert (
            len(list(filter(lambda pkg: pkg["name"] == "depA", packages))) == 0
        )
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

        run_cli(["dest", "add", "libs"])
        run_cli(["dest", "add", "libs2"])

        run_cli(["add", str(dep_a.path().absolute()), "--dest-name", "libs"])
        run_cli(["add", str(dep_b.path().absolute()), "--dest-name", "libs2"])

        toml_path = repo.path() / ".gitpkg.toml"

        assert_toml_dest_exists(toml_path, "libs")
        assert_toml_dest_exists(toml_path, "libs2")

        assert_toml_pkg_exists(toml_path, "libs", "depA")
        assert_toml_pkg_exists(toml_path, "libs2", "depB")

        run_cli(["remove", "depA"])

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

        run_cli(["dest", "add", "libs"])
        run_cli(["dest", "add", "libs2"])

        run_cli(["add", str(the_one.path().absolute()), "--dest-name", "libs"])
        run_cli(["add", str(the_one.path().absolute()), "--dest-name", "libs2"])

        toml_path = repo.path() / ".gitpkg.toml"

        assert_toml_dest_exists(toml_path, "libs")
        assert_toml_dest_exists(toml_path, "libs2")

        assert_toml_pkg_exists(toml_path, "libs", "the_one")
        assert_toml_pkg_exists(toml_path, "libs2", "the_one")

        with pytest.raises(AmbiguousDestinationError):
            run_cli(["remove", "the_one"])

        run_cli(["remove", "libs2/the_one"])

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

        run_cli(["add", str(dep_a.path().absolute())])
        run_cli(["add", str(dep_b.path().absolute())])

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

        run_cli(["install"])

        assert not (repo.path() / "libs" / "depA" / "test.txt").exists()
        assert (repo.path() / "libs" / "depA" / "swag.txt").exists()
        assert not (repo.path() / "libs" / "depB" / "test.txt").exists()
        assert (repo.path() / "libs" / "depB" / "42.txt").exists()
        assert not repo.is_corrupted()

    def test_install_with_config_changes_install_method_copy(self):
        dep_a = self._git.create_repository("depA")
        dep_a.new_file("a/b/c/swag.txt")
        dep_b = self._git.create_repository("depB")
        dep_b.new_file("d/e/f/42.txt")

        repo = self._git.create_repository("test_repo")

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        run_cli(
            ["add", str(dep_a.path().absolute()), "--install-method", "copy"]
        )
        run_cli(
            ["add", str(dep_b.path().absolute()), "--install-method", "copy"]
        )

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

        run_cli(["install"])

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

        run_cli(["add", str(dep_a.path().absolute())])
        run_cli(["add", str(dep_b.path().absolute())])

        os.chdir(repo.path())

        gitmodules = repo.path() / ".gitmodules"
        gitpkgs = repo.path() / ".gitpkgs"
        internal_dir = repo.path() / ".git" / "modules"

        safe_dir_delete(internal_dir)
        safe_dir_delete(internal_dir)
        internal_dir.mkdir()
        safe_dir_delete(gitpkgs)
        gitmodules.unlink()

        run_cli(["install"])

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

        run_cli(["add", str(dep_a.path().absolute())])
        run_cli(["add", str(dep_b.path().absolute())])

        os.chdir(repo.path())

        gitmodules = repo.path() / ".gitmodules"
        gitpkgs = repo.path() / ".gitpkgs"
        internal_dir = repo.path() / ".git" / "modules"

        safe_dir_delete(internal_dir)
        internal_dir.mkdir()

        run_cli(["install"])

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

        run_cli(["add", str(dep_a.path().absolute())])
        run_cli(["add", str(dep_b.path().absolute())])

        os.chdir(repo.path())

        gitmodules = repo.path() / ".gitmodules"
        gitpkgs = repo.path() / ".gitpkgs"
        internal_dir = repo.path() / ".git" / "modules"

        gitmodules.unlink()

        run_cli(["install"])

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

        run_cli(["add", str(dep_a.path().absolute())])
        run_cli(["add", str(dep_b.path().absolute())])

        os.chdir(repo.path())

        gitmodules = repo.path() / ".gitmodules"
        gitpkgs = repo.path() / ".gitpkgs"

        safe_dir_delete(gitpkgs)

        run_cli(["install"])

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

        run_cli(["add", str(dep_a.path().absolute())])
        run_cli(["add", str(dep_b.path().absolute())])

        os.chdir(repo.path())

        dep_a.new_file("updated.txt")

        updated_file = vendor_dir / "depA" / "updated.txt"

        assert not updated_file.exists()

        run_cli(["update"])

        assert updated_file.exists()

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="thiis relies on install method link which does not work on win",
    )
    def test_update_with_changes(self):
        dep_a = self._git.create_repository("depA")
        dep_a.new_file("new_file.txt")
        dep_b = self._git.create_repository("depB")

        repo = self._git.create_repository("test_repo")

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        run_cli(["add", str(dep_a.path().absolute())])
        run_cli(["add", str(dep_b.path().absolute())])

        os.chdir(repo.path())

        dep_a.new_file("updated.txt")

        new_file = vendor_dir / "depA" / "new_file.txt"

        new_file_before_change = checksum(new_file)
        new_file.write_text("CHANGED!")
        new_file_after_change = checksum(new_file)

        untracked_file = vendor_dir / "depB" / "untracked.txt"
        untracked_file.write_text("UNTRACKED")

        assert checksum(new_file) == new_file_after_change

        run_cli(["update", "depA"])

        assert checksum(new_file) == new_file_after_change

        run_cli(["update", "depA", "--force"])

        assert checksum(new_file) == new_file_before_change

        assert untracked_file.exists()

        run_cli(["update", "--force"])

        assert not untracked_file.exists()

    def test_update_with_disabled_updates(self):
        dep_a = self._git.create_repository("depA")
        dep_b = self._git.create_repository("depB")

        repo = self._git.create_repository("test_repo")

        vendor_dir = repo.path() / "libs"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(vendor_dir)

        run_cli(["add", str(dep_a.path().absolute()), "--disable-updates"])
        run_cli(["add", str(dep_b.path().absolute())])

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

        run_cli(["update"])

        assert not dep_a_updated_file.exists()
        assert dep_b_updated_file.exists()


# TODO: test cmd: update, with commited changes locally but not on upstream
# TODO: test cmd: add/install changing install method
