from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha3_256
from pathlib import Path

from git import GitConfigParser, Repo

from gitpkg.config import Config, Destination, PkgConfig
from gitpkg.errors import (
    DestinationWithNameAlreadyExistsError,
    DestinationWithPathAlreadyExistsError,
    PackageAlreadyInstalledError,
    PackageRootDirNotFoundError,
    PackageUrlChangedError,
    PkgHasAlreadyBeenAddedError,
    UnknownPackageError,
)

_GITPKGS_DIR = ".gitpkgs"
_CONFIG_FILE = ".gitpkg.toml"


class PkgManager:
    _repo: Repo
    _config: Config

    def __init__(self, repo: Repo, config: Config):
        self._repo = repo
        self._config = config

    def destinations(self) -> list[Destination]:
        return [*self._config.destinations]

    def destination_by_name(self, name: str) -> Destination | None:
        for dest in self.destinations():
            if dest.name == name:
                return dest
        return None

    def packages_by_destination(self, destination: Destination) -> list[PkgConfig]:
        if destination.name not in self._config.packages:
            return []
        return [*self._config.packages[destination.name]]

    def add_destination(self, name: str, path: Path) -> Destination:
        for dest in self._config.destinations:
            if dest.name == name:
                raise DestinationWithNameAlreadyExistsError(name)

            if path.absolute() == Path(dest.path).absolute():
                raise DestinationWithPathAlreadyExistsError(path)

        dest = Destination(
            name,
            str(path.relative_to(self.project_root_directory())),
        )

        logging.debug(f"Added new destination: {dest}")

        self._config.destinations.append(dest)
        self._write_config()

        return dest

    def has_package_been_added(self, destination: Destination, pkg: PkgConfig):
        return self.find_package(destination, pkg.name) is not None

    def package_stats(
        self, destination: Destination, pkg: PkgConfig
    ) -> PackageStats | None:
        package_dir = self._get_pkg_gitpkgs_location(destination, pkg)

        if not package_dir.exists():
            return None

        try:
            pkg_repo = Repo(package_dir)

            return PackageStats(
                pkg_repo.head.commit.hexsha,
                pkg_repo.head.commit.committed_datetime,
            )
        except ValueError:
            return None

    def add_package(self, destination: Destination, pkg: PkgConfig) -> None:
        if self.has_package_been_added(destination, pkg):
            raise PkgHasAlreadyBeenAddedError(destination, pkg)

        logging.debug(f"adding package {pkg} to dest: {destination}")

        if destination.name not in self._config.packages:
            self._config.packages[destination.name] = []

        self._config.packages[destination.name].append(pkg)
        self._write_config()

    def remove_package(self, destination: Destination, pkg: PkgConfig) -> None:
        if not self.has_package_been_added(destination, pkg):
            raise UnknownPackageError(destination, pkg)

        logging.debug(f"removing package {pkg} from dest: {destination}")

        index = -1

        for idx, p in enumerate(self._config.packages[destination.name]):
            if pkg.name == p.name:
                index = idx
                break

        if index == -1:
            raise UnknownPackageError(destination, pkg)

        del self._config.packages[destination.name][index]
        self._write_config()

    def is_package_installed(
        self,
        destination: Destination,
        pkg: PkgConfig,
    ) -> bool:
        if not self.has_package_been_added(destination, pkg):
            return False

        return (
            (self.project_root_directory() / ".gitmodules").exists()
            and self.package_install_location(destination, pkg).exists()
            and self._get_pkg_gitpkgs_location(destination, pkg).exists()
            and self._gitmodules_internal_location(destination, pkg).exists()
        )

    def find_package(self, destination: Destination, pkg_name: str) -> PkgConfig | None:
        if destination.name not in self._config.packages:
            return None
        for pkg in self._config.packages[destination.name]:
            if pkg.name == pkg_name:
                return pkg
        return None

    def has_pkg_been_changed(self, destination: Destination, pkg: PkgConfig) -> bool:
        ref_pkg = self.find_package(destination, pkg.name)
        if ref_pkg is None:
            raise UnknownPackageError(destination, pkg)

        if ref_pkg.url != pkg.url:
            raise PackageUrlChangedError(destination, ref_pkg, pkg)

        config_changed = (
            ref_pkg.package_root != pkg.package_root
            or ref_pkg.updates_disabled != pkg.updates_disabled
            or ref_pkg.branch != pkg.branch
            or ref_pkg.install_method != pkg.install_method
        )

        if config_changed:
            return True

        return self._has_repo_changed(destination, pkg)

    def _has_repo_changed(self, destination: Destination, pkg: PkgConfig) -> bool:
        # no changes in config found, next test against the actual repo...
        if pkg.branch:
            ref_repo = Repo(self._get_pkg_gitpkgs_location(destination, pkg))
            if pkg.branch != ref_repo.active_branch.name:
                logging.debug(
                    f"package has changed! repo branch is: "
                    f"{ref_repo.active_branch.name}, but package "
                    f"wanted: {pkg.branch}"
                )
                return False

        pkg_path = self.package_install_location(destination, pkg)

        # install method is not defined (link) or is link but the pkg is not a
        # symlink
        if (
            not pkg.install_method or pkg.install_method == "link"
        ) and not pkg_path.is_symlink():
            return True

        if pkg.package_root and pkg_path.is_symlink():
            source_path = (
                self._get_pkg_gitpkgs_location(destination, pkg) / pkg.package_root
            )
            target_path = Path(os.readlink(pkg_path))
            logging.debug(
                f"package root: Source is {source_path}, " f"Target is: {target_path}"
            )
            return str(source_path.absolute()) != str(target_path.absolute())

        return False

    def install_package(self, destination: Destination, pkg: PkgConfig) -> None:
        if not self.has_package_been_added(destination, pkg):
            self.add_package(destination, pkg)

        has_pkg_changed = self.has_pkg_been_changed(destination, pkg)

        if has_pkg_changed:
            logging.debug(f"replace package with new settings {pkg}")
            self.remove_package(destination, pkg)
            self.add_package(destination, pkg)

        if not has_pkg_changed and self.is_package_installed(destination, pkg):
            raise PackageAlreadyInstalledError(destination, pkg)

        pkg_gitpkgs_dir = self._get_pkg_gitpkgs_location(destination, pkg)
        install_dir = self.package_install_location(destination, pkg)
        pkg_package_root_dir = pkg_gitpkgs_dir / pkg.package_root

        # create parent directories
        pkg_gitpkgs_dir.parent.mkdir(parents=True, exist_ok=True)
        install_dir.parent.mkdir(parents=True, exist_ok=True)

        if install_dir.exists():
            install_dir.unlink()

        if pkg_gitpkgs_dir.exists():
            shutil.rmtree(pkg_gitpkgs_dir)

        gitmodules_file = self.project_root_directory() / ".gitmodules"

        internal_dir = self._gitmodules_internal_location(destination, pkg)
        if internal_dir.exists() and not gitmodules_file.exists():
            shutil.rmtree(internal_dir)

        if internal_dir.exists():
            Repo.clone_from(internal_dir, pkg_gitpkgs_dir)

            gitdir = pkg_gitpkgs_dir / ".git"

            if gitdir.exists():
                shutil.rmtree(gitdir)

            rel_path = os.path.relpath(internal_dir, pkg_gitpkgs_dir)
            gitdir.write_text(f"gitdir: {rel_path}")
        else:
            self._remove_pkg_from_gitmodules(destination, pkg)
            self._repo.create_submodule(
                name=self._package_ident(destination, pkg),
                path=pkg_gitpkgs_dir,
                url=pkg.url,
                branch=pkg.branch,
            )

        if not pkg_package_root_dir.exists():
            raise PackageRootDirNotFoundError(pkg, pkg_package_root_dir)

        if install_dir.exists():
            install_dir.unlink()

        install_dir.symlink_to(pkg_package_root_dir)

        logging.debug(f"installed package '{pkg.name}' to {install_dir}")

    def uninstall_package(self, destination: Destination, pkg: PkgConfig) -> None:
        internal_dir = self._gitmodules_internal_location(destination, pkg)
        if internal_dir.exists():
            shutil.rmtree(internal_dir)

        install_dir = self.package_install_location(destination, pkg)
        if install_dir.exists():
            install_dir.unlink()

        package_dir = self._get_pkg_gitpkgs_location(destination, pkg)
        if package_dir.exists():
            shutil.rmtree(package_dir)

        self._remove_pkg_from_gitmodules(destination, pkg)

        if self.has_package_been_added(destination, pkg):
            self.remove_package(destination, pkg)

        logging.debug(
            f"uninstalled package '{pkg.name}' from dest: " f"'{destination.name}'"
        )

    def _remove_pkg_from_gitmodules(
        self, destination: Destination, pkg: PkgConfig
    ) -> None:
        pkg_ident = self._package_ident(destination, pkg)
        gitmodules_file = self.project_root_directory() / ".gitmodules"

        if gitmodules_file.exists():
            with GitConfigParser(gitmodules_file, read_only=False) as cp:
                cp.read()
                cp.remove_section(f'submodule "{pkg_ident}"')
                cp.write()

            # remove .gitmodules file if empy
            text = gitmodules_file.read_text()
            if len(text.strip()) == 0:
                gitmodules_file.unlink()

    def _write_config(self) -> None:
        logging.debug(f"Written to config file: {self.config_file()}")
        self.config_file().write_text(self._config.to_toml_string())

    def project_root_directory(self) -> Path:
        return PkgManager._project_root_directory(self._repo)

    def config_file(self) -> Path:
        return self.project_root_directory() / _CONFIG_FILE

    def _gitpkgs_location(self) -> Path:
        return self.project_root_directory() / _GITPKGS_DIR

    def package_install_location(
        self,
        destination: Destination,
        pkg: PkgConfig,
    ) -> Path:
        return self.project_root_directory() / destination.path / pkg.name

    def _get_pkg_gitpkgs_location(
        self,
        destination: Destination,
        pkg: PkgConfig,
    ) -> Path:
        return self._gitpkgs_location() / self._package_ident(destination, pkg)

    def _package_ident(self, destination: Destination, pkg: PkgConfig) -> str:
        hasher = sha3_256()
        hasher.update(
            str(self.package_install_location(destination, pkg)).encode("utf8"),
        )
        res = hasher.hexdigest()
        return res[0:32]

    def _gitmodules_internal_location(
        self, destination: Destination, pkg: PkgConfig
    ) -> Path:
        return (
            self.project_root_directory()
            / ".git"
            / "modules"
            / self._package_ident(destination, pkg)
        )

    @staticmethod
    def from_environment():
        repo = Repo(Path.cwd(), search_parent_directories=True)
        config = Config()

        config_file = PkgManager._project_root_directory(repo) / _CONFIG_FILE

        if config_file.exists():
            config = Config.from_path(config_file)

        return PkgManager(repo, config)

    @staticmethod
    def _project_root_directory(repo: Repo) -> Path:
        return Path(repo.git_dir).parent


@dataclass
class PackageStats:
    commit_hash: str
    commit_date: datetime
