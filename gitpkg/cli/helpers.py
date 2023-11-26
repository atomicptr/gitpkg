from gitpkg.config import Destination, PkgConfig
from gitpkg.errors import AmbiguousDestinationError
from gitpkg.pkg_manager import PkgManager


def render_package_name(
    pm: PkgManager,
    dest: Destination,
    pkg: PkgConfig,
    hide_dest: bool = False,
    hide_stats: bool = False,
) -> str:
    prefix = ""
    pkg_name = f"[bold]{pkg.name}[/bold]"
    suffix = ""

    if not hide_stats and pm.is_package_installed(dest, pkg):
        stats = pm.package_stats(dest, pkg)
        if stats:
            suffix = f" ({stats.commit_hash[0:7]})"

    if not hide_dest and len(pm.destinations()) > 1:
        count = 0
        for d in pm.destinations():
            if pm.is_package_registered(d, pkg):
                count += 1
        if count > 1:
            prefix = f"{dest.name}/"
    return prefix + pkg_name + suffix


def parse_package_name(package_name: str) -> tuple[str | None, str | None]:
    if "/" in package_name:
        dest_name, pkg_name = package_name.split("/")
        return dest_name, pkg_name
    return None, package_name


def determine_package_destination(
    pm: PkgManager,
    dest_name: str | None = None,
    pkg_name: str | None = None,
    return_none: bool = False,
) -> Destination | None:
    if dest_name:
        return pm.find_destination(dest_name)

    if len(pm.destinations()) == 1:
        return pm.destinations()[0]

    if pkg_name is not None:
        found_num = 0
        found_dest = None

        for dest in pm.destinations():
            for pkg in pm.find_packages_by_destination(dest):
                if pkg.name == pkg_name:
                    found_num += 1
                    found_dest = dest

        if found_dest and found_num == 1:
            return found_dest

    if return_none:
        return None

    raise AmbiguousDestinationError
