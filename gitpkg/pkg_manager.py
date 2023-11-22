from __future__ import annotations

import enum
import hashlib
import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from git import FetchInfo, GitConfigParser, Repo

from gitpkg.config import Config, Destination, PkgConfig
from gitpkg.errors import (
    DestinationWithNameAlreadyExistsError,
    DestinationWithPathAlreadyExistsError,
    NameInvalidError,
    PackageAlreadyInstalledError,
    PackageRootDirNotFoundError,
    PackageUrlChangedError,
    PkgHasAlreadyBeenAddedError,
    UnknownPackageError,
)
from gitpkg.utils import extract_repository_name_from_url, symlink_exists

_GITPKGS_DIR = ".gitpkgs"
_CONFIG_FILE = ".gitpkg.toml"
_NAME_REGEX = r"^[\w\-.\s]+$"


class PkgManager:
    _repo: Repo
    _config: Config

    def __init__(self, repo: Repo, config: Config):
        self._repo = repo
        self._config = config

    def destinations(self) -> list[Destination]:
        """Returns all registered destinations"""
        return [*self._config.destinations]

    def find_destination(self, destination_name: str) -> Destination | None:
        """Find destination by name"""
        for dest in self.destinations():
            if dest.name == destination_name:
                return dest
        return None

    def find_packages_by_destination(self, destination: Destination) -> list[PkgConfig]:
        """Find all packages associated with given destination"""
        if destination.name not in self._config.packages:
            return []
        return [*self._config.packages[destination.name]]

    def add_destination(self, name: str, path: Path) -> Destination:
        """Register a new destination"""

        if re.match(_NAME_REGEX, name) is None:
            raise NameInvalidError(name)

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

    def is_package_registered(
        self, destination: Destination, pkg: PkgConfig | str
    ) -> bool:
        """Is the given package registered at destination?"""
        if isinstance(pkg, PkgConfig):
            pkg = pkg.name
        return self.find_package(destination, pkg) is not None

    def package_stats(
        self, destination: Destination, pkg: PkgConfig
    ) -> PkgStats | None:
        """Get package related statistics"""
        submodule_location = self._get_pkg_submodule_location(destination, pkg)

        if not submodule_location.exists():
            return None

        try:
            pkg_repo = Repo(submodule_location)

            return PkgStats(
                pkg_repo.head.commit.hexsha,
                pkg_repo.head.commit.committed_datetime,
            )
        except ValueError:
            return None

    def add_package(self, destination: Destination, pkg: PkgConfig) -> None:
        """Add package to destination in config (does not install package)"""

        if re.match(_NAME_REGEX, pkg.name) is None:
            raise NameInvalidError(pkg.name)

        if self.is_package_registered(destination, pkg):
            raise PkgHasAlreadyBeenAddedError(destination, pkg)

        logging.debug(f"adding package {pkg} to dest: {destination}")

        if destination.name not in self._config.packages:
            self._config.packages[destination.name] = []

        self._config.packages[destination.name].append(pkg)
        self._write_config()

    def remove_package(self, destination: Destination, pkg: PkgConfig) -> None:
        """Remove package from destination in config (does not uninstall package)"""

        if not self.is_package_registered(destination, pkg):
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
        """Is the given package physicially installed on disk?"""

        if not self.is_package_registered(destination, pkg):
            return False

        return (
            (self.project_root_directory() / ".gitmodules").exists()
            and symlink_exists(self.package_install_location(destination, pkg))
            and self._get_pkg_submodule_location(destination, pkg).exists()
            and self._gitmodules_internal_location(destination, pkg).exists()
        )

    def find_package(self, destination: Destination, pkg_name: str) -> PkgConfig | None:
        """Find a package in a destination by name"""
        if destination.name not in self._config.packages:
            return None
        for pkg in self._config.packages[destination.name]:
            if pkg.name == pkg_name:
                return pkg
        return None

    def has_package_config_been_changed(
        self, destination: Destination, pkg: PkgConfig
    ) -> bool:
        """Is the given package configuration different from what's installed?"""
        ref_pkg = self.find_package(destination, pkg.name)
        if ref_pkg is None:
            raise UnknownPackageError(destination, pkg)

        if ref_pkg.url != pkg.url:
            raise PackageUrlChangedError(destination, ref_pkg, pkg)

        config_changed = (
            ref_pkg.package_root != pkg.package_root
            or ref_pkg.updates_disabled != pkg.updates_disabled
            or ref_pkg.branch != pkg.branch
        )

        if config_changed:
            return True

        return self._has_repo_changed(destination, pkg)

    def _has_repo_changed(self, destination: Destination, pkg: PkgConfig) -> bool:
        """Has the physical repository changed?"""
        # no changes in config found, next test against the actual repo...
        if pkg.branch:
            ref_repo = Repo(self._get_pkg_submodule_location(destination, pkg))
            if pkg.branch != ref_repo.active_branch.name:
                logging.debug(
                    f"package has changed! repo branch is: "
                    f"{ref_repo.active_branch.name}, but package "
                    f"wanted: {pkg.branch}"
                )
                return False

        pkg_path = self.package_install_location(destination, pkg)

        if pkg.package_root and symlink_exists(pkg_path) and pkg_path.is_symlink():
            source_path = (
                self._get_pkg_submodule_location(destination, pkg) / pkg.package_root
            )
            target_path = Path(os.readlink(pkg_path))

            # this path should be relative, so we apply it on top of the install
            # location
            if not target_path.is_absolute():
                vendor_dir = self.package_install_location(destination, pkg).parent
                target_path = vendor_dir / target_path

            # link target does not exist? Something changed!
            if not source_path.exists() or not target_path.exists():
                return True

            logging.debug(
                f"package root: Source is {source_path}, " f"Target is: {target_path}"
            )
            return not source_path.samefile(target_path)

        return False

    def install_package(self, destination: Destination, pkg: PkgConfig) -> None:
        """Install the package to the disk"""
        self._cleanup_install()

        if not self.is_package_registered(destination, pkg):
            self.add_package(destination, pkg)

        has_pkg_changed = self.has_package_config_been_changed(destination, pkg)

        if has_pkg_changed:
            logging.debug(f"replace package with new settings {pkg}")
            self.remove_package(destination, pkg)
            self.add_package(destination, pkg)

        if not has_pkg_changed and self.is_package_installed(destination, pkg):
            raise PackageAlreadyInstalledError(destination, pkg)

        repo_used_by_other_pkg = self._repo_used_by_other_pkg(destination, pkg)

        submodule_location = self._get_pkg_submodule_location(destination, pkg)
        install_dir = self.package_install_location(destination, pkg)
        pkg_package_root_dir = submodule_location / pkg.package_root

        # create parent directories
        submodule_location.parent.mkdir(parents=True, exist_ok=True)
        install_dir.parent.mkdir(parents=True, exist_ok=True)

        # delete if install dir is there (missing links are exists = False)
        install_dir.unlink(missing_ok=True)

        if not repo_used_by_other_pkg and submodule_location.exists():
            shutil.rmtree(submodule_location)

        gitmodules_file = self.project_root_directory() / ".gitmodules"

        internal_dir = self._gitmodules_internal_location(destination, pkg)
        if internal_dir.exists() and not gitmodules_file.exists():
            shutil.rmtree(internal_dir)

        if not submodule_location.exists():
            if internal_dir.exists():
                Repo.clone_from(internal_dir, submodule_location)

                gitdir = submodule_location / ".git"

                if gitdir.exists():
                    shutil.rmtree(gitdir)

                rel_path = os.path.relpath(internal_dir, submodule_location)
                gitdir.write_text(f"gitdir: {rel_path}")
            else:
                self._remove_pkg_from_gitmodules(destination, pkg)
                self._repo.create_submodule(
                    name=self.package_identifier(destination, pkg),
                    path=submodule_location,
                    url=pkg.url,
                    branch=pkg.branch,
                    depth=1,
                )
                self._update_gitmodules_file(destination, pkg)

        if not pkg_package_root_dir.exists():
            raise PackageRootDirNotFoundError(pkg, pkg_package_root_dir)

        if symlink_exists(install_dir):
            install_dir.unlink()

        install_dir.symlink_to(
            os.path.relpath(pkg_package_root_dir, install_dir.parent)
        )

        logging.debug(f"installed package '{pkg.name}' to {install_dir}")

    def uninstall_package(self, destination: Destination, pkg: PkgConfig) -> None:
        """Uninstalls the package from disk"""

        repo_used_by_other_pkg = self._repo_used_by_other_pkg(destination, pkg)

        internal_dir = self._gitmodules_internal_location(destination, pkg)
        if not repo_used_by_other_pkg and internal_dir.exists():
            shutil.rmtree(internal_dir)

        install_dir = self.package_install_location(destination, pkg)
        if symlink_exists(install_dir):
            install_dir.unlink()

        submodule_location = self._get_pkg_submodule_location(destination, pkg)
        if not repo_used_by_other_pkg and submodule_location.exists():
            shutil.rmtree(submodule_location)

        if not repo_used_by_other_pkg:
            self._remove_pkg_from_gitmodules(destination, pkg)

        if self.is_package_registered(destination, pkg):
            self.remove_package(destination, pkg)

        logging.debug(
            f"uninstalled package '{pkg.name}' from dest: " f"'{destination.name}'"
        )

    def update_package(
        self,
        destination: Destination,
        pkg: PkgConfig,
        discard_untracked_changes: bool = False,
        check_only: bool = False,
    ) -> PkgUpdateResult:
        if pkg.updates_disabled:
            return PkgUpdateResult.UPDATES_DISABLED

        submodule_location = self._get_pkg_submodule_location(destination, pkg)
        submodule_repo = Repo(submodule_location)

        has_untracked_changes = (
            len(submodule_repo.untracked_files) > 0
            or len(submodule_repo.index.diff(None)) > 0
        )

        if not discard_untracked_changes and has_untracked_changes:
            return PkgUpdateResult.UNTRACKED_CHANGES

        if discard_untracked_changes and has_untracked_changes:
            for file in submodule_repo.untracked_files:
                (submodule_location / file).unlink()
            submodule_repo.head.reset(index=True, working_tree=True)

        # TODO: if origin does not exist
        remote = submodule_repo.remotes.origin

        res = remote.pull() if not check_only else remote.fetch()

        if len(res) == 0:
            return PkgUpdateResult.NO_UPDATE_AVAILABLE

        fetch_info: FetchInfo = res[0]

        if fetch_info.old_commit is None:
            return PkgUpdateResult.NO_UPDATE_AVAILABLE

        if fetch_info.commit != fetch_info.old_commit:
            return (
                PkgUpdateResult.UPDATED
                if not check_only
                else PkgUpdateResult.UPDATE_AVAILABLE
            )

        return PkgUpdateResult.NO_UPDATE_AVAILABLE

    def _cleanup_install(self) -> None:
        gitmodules_file = self.project_root_directory() / ".gitmodules"
        section_regex = r"submodule \"(.+)\""

        packages = []

        for dest_name in self._config.packages:
            for pkg in self._config.packages[dest_name]:
                dest = self.find_destination(dest_name)
                ident = self.package_identifier(dest, pkg)

                if ident not in packages:
                    packages.append(ident)

        # remove unused .gitpkgs dirs
        for dir in self._gitpkgs_location().glob("*"):
            if dir.name in packages:
                continue
            logging.debug(f"CLEAN: remove unused gitpkg {dir}")
            shutil.rmtree(dir)

        # remove links that point nowhere from dest dirs
        for dest in self.destinations():
            dest_path = self.project_root_directory() / dest.path

            for dest_dir in dest_path.glob("*"):
                if not dest_dir.is_symlink():
                    continue
                target_dir = (dest_dir.parent / os.readlink(dest_dir)).resolve()
                if not symlink_exists(target_dir):
                    logging.debug(f"CLEAN: remove symlink {dest_dir}")
                    dest_dir.unlink()

        if not gitmodules_file.exists():
            return

        with GitConfigParser(gitmodules_file, read_only=False) as cp:
            cp.read()

            outdated_sections = []

            for section in cp.sections():
                path = cp.get(section, "path")

                # skip submodules that are unrelated to us
                if not path.startswith(_GITPKGS_DIR):
                    continue

                found = False

                for pkg_ident in packages:
                    pkg_section = f'submodule "{pkg_ident}"'

                    if section == pkg_section:
                        found = True
                        break

                if found:
                    continue

                outdated_sections.append(section)

            for section in outdated_sections:
                matches = re.findall(section_regex, section)

                if len(matches) == 0:
                    continue

                pkg_ident = matches[0]

                internal_dir = (
                    self.project_root_directory() / ".git" / "modules" / pkg_ident
                )

                if internal_dir.exists():
                    logging.debug(f"CLEAN: remove internal dir {internal_dir}")
                    shutil.rmtree(internal_dir)

                cp.remove_section(section)
            cp.write()

    def _repo_used_by_other_pkg(self, dest: Destination, pkg: PkgConfig) -> bool:
        package_ident = self.package_identifier(dest, pkg)

        for ref_dest in self.destinations():
            for ref_pkg in self.find_packages_by_destination(ref_dest):
                # ignore current package
                if dest.name == ref_dest.name and pkg.name == ref_pkg.name:
                    continue

                ref_ident = self.package_identifier(ref_dest, ref_pkg)

                if package_ident == ref_ident:
                    return True
        return False

    def _remove_pkg_from_gitmodules(
        self, destination: Destination, pkg: PkgConfig
    ) -> None:
        """Remove package entry from the .gitmodules file"""
        pkg_ident = self.package_identifier(destination, pkg)
        gitmodules_file = self.project_root_directory() / ".gitmodules"
        section = f'submodule "{pkg_ident}"'

        if gitmodules_file.exists():
            with GitConfigParser(gitmodules_file, read_only=False) as cp:
                cp.read()
                cp.remove_section(section)
                cp.write()

            # remove .gitmodules file if empy
            text = gitmodules_file.read_text()
            if len(text.strip()) == 0:
                gitmodules_file.unlink()

    def _update_gitmodules_file(self, destination: Destination, pkg: PkgConfig) -> None:
        pkg_ident = self.package_identifier(destination, pkg)
        gitmodules_file = self.project_root_directory() / ".gitmodules"
        section = f'submodule "{pkg_ident}"'

        if gitmodules_file.exists():
            with GitConfigParser(gitmodules_file, read_only=False) as cp:
                cp.read()
                cp.set(section, "update", "none")
                cp.write()

    def _write_config(self) -> None:
        """Persist config file to disk"""
        logging.debug(f"Written to config file: {self.config_file()}")
        self.config_file().write_text(self._config.to_toml_string())

    def project_root_directory(self) -> Path:
        """Root directory of the project repository"""
        return PkgManager._project_root_directory(self._repo)

    def config_file(self) -> Path:
        """Location of the git pkg config file"""
        return self.project_root_directory() / _CONFIG_FILE

    def _gitpkgs_location(self) -> Path:
        """Location of the directory where the submodules are stored"""
        return self.project_root_directory() / _GITPKGS_DIR

    def package_install_location(
        self,
        destination: Destination,
        pkg: PkgConfig,
    ) -> Path:
        """Location where the package will be installed"""
        return self.project_root_directory() / destination.path / pkg.name

    def _get_pkg_submodule_location(
        self,
        destination: Destination,
        pkg: PkgConfig,
    ) -> Path:
        """Submodule location of package"""
        return self._gitpkgs_location() / self.package_identifier(destination, pkg)

    def package_identifier(self, _dest: Destination, pkg: PkgConfig) -> str:
        """Unique package identifier"""
        hasher = hashlib.sha3_256()
        hasher.update(
            "::".join(
                filter(
                    lambda elem: elem is not None,
                    [
                        "gitpkg",
                        pkg.url,
                        pkg.branch,
                    ],
                )
            ).encode("utf8")
        )
        # TODO: properly parse ident
        reponame = extract_repository_name_from_url(pkg.url)
        return f"{reponame}_{hasher.hexdigest()[0:7]}"

    def _gitmodules_internal_location(
        self, destination: Destination, pkg: PkgConfig
    ) -> Path:
        """Git internal location for the submodule"""
        return (
            self.project_root_directory()
            / ".git"
            / "modules"
            / self.package_identifier(destination, pkg)
        )

    @staticmethod
    def from_environment():
        """Create a package manager for the nearest git project"""
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
class PkgStats:
    commit_hash: str
    commit_date: datetime


class PkgUpdateResult(enum.Enum):
    NO_UPDATE_AVAILABLE = 0
    UPDATES_DISABLED = 1
    UPDATED = 2
    UPDATE_AVAILABLE = 3
    UNTRACKED_CHANGES = 4
