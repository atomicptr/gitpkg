from pathlib import Path

from gitpkg.config import Destination, PkgConfig


class GitPkgError(Exception):
    raw_message: str = None

    def __init__(self, message: str | None = None):
        if message is None:
            message = self.raw_message
        self.raw_message = message
        super().__init__(f"ERROR: git pkg: {message}")


class DestinationWithNameAlreadyExistsError(GitPkgError):
    def __init__(self, name: str):
        super().__init__(f"destination with name '{name}' already exists.")


class DestinationWithPathAlreadyExistsError(GitPkgError):
    def __init__(self, path: Path):
        super().__init__(
            f"destination with path '{path.absolute()}' already exists.",
        )


class CouldNotFindDestinationError(GitPkgError):
    def __init__(self, name: str):
        super().__init__(
            f"destination '{name}' could not be found.",
        )


class AmbiguousDestinationError(GitPkgError):
    raw_message = "no destination could be determined."


class PkgHasAlreadyBeenAddedError(GitPkgError):
    def __init__(self, destination: Destination, pkg: PkgConfig):
        super().__init__(
            f"package '{pkg.name}' has already been added to "
            f"destination '{destination.name}'.",
        )


class PackageAlreadyInstalledError(GitPkgError):
    def __init__(self, destination: Destination, pkg: PkgConfig):
        super().__init__(
            f"package '{pkg.name}' has already been installed to "
            f"destination '{destination.name}'.",
        )


class UnknownPackageError(GitPkgError):
    def __init__(self, destination: Destination, pkg: PkgConfig | str):
        if isinstance(pkg, PkgConfig):
            pkg = pkg.name
        super().__init__(
            f"package '{pkg}' is unknown (dest: '{destination.name}')",
        )


class PackageUrlChangedError(GitPkgError):
    def __init__(self, destination: Destination, ref_pkg: PkgConfig, pkg: PkgConfig):
        super().__init__(
            f"package '{pkg.name}' (dest: '{destination.name}') changed url "
            f"from '{ref_pkg.url}' to '{pkg.url}', please uninstall the "
            f"package first.",
        )


class PackageRootDirNotFoundError(GitPkgError):
    def __init__(self, pkg: PkgConfig, pkg_root_dir: Path):
        super().__init__(
            f"package '{pkg.name}' has unknown package root set to "
            f"'{pkg.package_root}' which is '{pkg_root_dir.absolute()}')",
        )


class NameInvalidError(GitPkgError):
    def __init__(self, name: str):
        super().__init__(f"Name '{name}' is not valid!")
