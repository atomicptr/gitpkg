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
    PackageRootDirNotFoundError,
    PackageUrlChangedError,
    PkgHasAlreadyBeenAddedError,
    UnknownPackageError,
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
        return self.find_package(destination, pkg.name) is not None

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
            self.package_install_location(destination, pkg).exists()
            and self.package_vendor_location(destination, pkg).exists()
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

        return (
            ref_pkg.package_root != pkg.package_root
            or ref_pkg.updates_disabled != pkg.updates_disabled
            or ref_pkg.branch != pkg.branch
            or ref_pkg.install_method != pkg.install_method
        )

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

        internal_dir = self._internal_dir(destination, pkg)
        if internal_dir.exists():
            shutil.rmtree(internal_dir)

        vendor_dir = self.package_vendor_location(destination, pkg)
        install_dir = self.package_install_location(destination, pkg)
        package_root_dir = vendor_dir / pkg.package_root

        # create parent directories
        vendor_dir.parent.mkdir(parents=True, exist_ok=True)
        install_dir.parent.mkdir(parents=True, exist_ok=True)

        if not vendor_dir.exists():
            self._repo.create_submodule(
                name=self._package_ident(destination, pkg),
                path=vendor_dir,
                url=pkg.url,
                branch=pkg.branch,
            )

        if not package_root_dir.exists():
            raise PackageRootDirNotFoundError(pkg, package_root_dir)

        if install_dir.exists():
            install_dir.unlink()

        install_dir.symlink_to(package_root_dir)

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
