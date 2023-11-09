import logging
import shutil
from hashlib import sha3_256
from pathlib import Path

from git import Repo

from gitpkg.config import Config, Destination, PkgConfig
from gitpkg.errors import (
    DestinationWithNameAlreadyExistsError,
    DestinationWithPathAlreadyExistsError,
    PackageAlreadyInstalledError,
    PkgHasAlreadyBeenAddedError,
)

_VENDOR_DIR = ".gitpkgs"
_CONFIG_FILE = ".gitpkg.toml"


class PkgManager:
    _repo: Repo
    _config: Config

    def __init__(self, repo: Repo, config: Config):
        self._repo = repo
        self._config = config

    def destinations(self) -> list[Destination]:
        return self._config.destinations

    def destination_by_name(self, name: str) -> Destination | None:
        for dest in self.destinations():
            if dest.name == name:
                return dest
        return None

    def packages_by_destination(self, destination: Destination) -> list[PkgConfig]:
        if destination.name not in self._config.packages:
            return []
        return self._config.packages[destination.name]

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
        for my_pkg in self.packages_by_destination(destination):
            if my_pkg.name == pkg.name:
                return True
        return False

    def add_package(self, destination: Destination, pkg: PkgConfig) -> None:
        if self.has_package_been_added(destination, pkg):
            raise PkgHasAlreadyBeenAddedError(destination, pkg)

        logging.debug(f"adding package {pkg} to dest: {destination}")

        if destination.name not in self._config.packages:
            self._config.packages[destination.name] = []

        self._config.packages[destination.name].append(pkg)
        self._write_config()

    def is_package_installed(
            self,
            destination: Destination,
            pkg: PkgConfig,
    ) -> bool:
        if not self.has_package_been_added(destination, pkg):
            return False

        return self.package_install_location(destination, pkg).exists() and\
            self.package_vendor_location(destination, pkg).exists()

    def install_package(self, destination: Destination, pkg: PkgConfig) -> None:
        if not self.has_package_been_added(destination, pkg):
            self.add_package(destination, pkg)

        if self.is_package_installed(destination, pkg):
            raise PackageAlreadyInstalledError(destination, pkg)

        internal_dir = self._internal_dir(destination, pkg)
        if internal_dir.exists():
            shutil.rmtree(internal_dir)

        vendor_dir = self.package_vendor_location(destination, pkg)
        install_dir = self.package_install_location(destination, pkg)

        vendor_dir.parent.mkdir(parents=True, exist_ok=True)
        install_dir.parent.mkdir(parents=True, exist_ok=True)

        if install_dir.exists():
            shutil.rmtree(install_dir)

        self._repo.create_submodule(
            name=self._package_ident(destination, pkg),
            path=vendor_dir,
            url=pkg.url,
            branch=pkg.branch,
        )

        install_dir.symlink_to(vendor_dir)

        logging.debug(f"installed package '{pkg.name}' to {install_dir}")

    def _write_config(self) -> None:
        logging.debug(f"Written to config file: {self.config_file()}")
        self.config_file().write_text(self._config.to_toml_string())

    def project_root_directory(self) -> Path:
        return PkgManager._project_root_directory(self._repo)

    def config_file(self) -> Path:
        return self.project_root_directory() / _CONFIG_FILE

    def vendor_directory(self) -> Path:
        return self.project_root_directory() / _VENDOR_DIR

    def package_install_location(
            self,
            destination: Destination,
            pkg: PkgConfig,
    ) -> Path:
        return self.project_root_directory() / destination.path / pkg.name

    def package_vendor_location(
            self,
            destination: Destination,
            pkg: PkgConfig,
    ) -> Path:
        return self.vendor_directory() / self._package_ident(destination, pkg)

    def _package_ident(self, destination: Destination, pkg: PkgConfig) -> str:
        hasher = sha3_256()
        hasher.update(
            str(self.package_install_location(destination, pkg)).encode("utf8"),
        )
        res = hasher.hexdigest()
        return res[0:32]

    def _internal_dir(self, destination: Destination, pkg: PkgConfig) -> Path:
        return (self.project_root_directory() / ".git" / "modules" /
                self._package_ident(destination, pkg))

    @staticmethod
    def from_environment():
        repo = Repo(Path.cwd(), search_parent_directories=True)
        config = Config()

        config_file = PkgManager._project_root_directory(repo) / _CONFIG_FILE

        if PkgManager._project_root_directory(repo).exists():
            config = Config.from_path(config_file)

        return PkgManager(repo, config)

    @staticmethod
    def _project_root_directory(repo: Repo) -> Path:
        return Path(repo.git_dir).parent
