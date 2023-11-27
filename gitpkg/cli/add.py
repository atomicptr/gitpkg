import logging
from pathlib import Path

import rich_click as click

from gitpkg.cli.console import console, success
from gitpkg.cli.helpers import (
    determine_package_destination,
    render_package_name,
)
from gitpkg.cli.root import Context, root
from gitpkg.config import InstallMethod, PkgConfig
from gitpkg.errors import (
    AmbiguousDestinationError,
    GitPkgError,
    PackageRootDirNotFoundError,
)
from gitpkg.utils import (
    extract_repository_name_from_url,
    is_windows,
    parse_repository_url,
)


@root.command("add", help="Add and install a package to a destination")
@click.argument("repository_url")
@click.option("--name", help="Overwrite the name of the package")
@click.option("--dest-name", help="Target destination name")
@click.option(
    "-r",
    "--package-root",
    help="Define the root directory of the repository (directory inside the "
    "repository to be used as the repository)",
    type=click.Path(exists=False),
)
@click.option(
    "-rn",
    "--package-root-with-name",
    help="Combines --package-root and --name into one command, name is "
    "determined by package roots filename",
)
@click.option(
    "-b",
    "--branch",
    help="Define the branch to be used, defaults to the repository default",
)
@click.option(
    "--disable-updates",
    help="Disable updates for this repository",
    is_flag=True,
)
@click.option(
    "--install-method",
    help="Set how the package is to be installed",
)
@click.pass_obj
def cmd_add(
    ctx: Context,
    repository_url: str,
    name: str | None,
    dest_name: str | None,
    package_root: str | None,
    package_root_with_name: str | None,
    branch: str | None,
    disable_updates: bool,
    install_method: str | None,
) -> None:
    pm = ctx.package_manager()

    parse_url_result = parse_repository_url(repository_url)

    if not parse_url_result:
        msg = f"URL: {repository_url} does not seem to be a valid git url"
        raise GitPkgError(msg)

    repository_url, _ = parse_url_result

    package_root_value = "."

    if package_root:
        package_root_value = package_root

    if package_root_with_name:
        package_root_value = package_root_with_name
        name = package_root_with_name.split("/")[-1]

    if not name:
        name = extract_repository_name_from_url(repository_url)

    dest = determine_package_destination(pm, dest_name, return_none=True)

    # if no destinations are known add current location as dest
    if not dest and len(pm.destinations()) == 0:
        cwd = Path.cwd()

        logging.debug(f"register cwd as destination {cwd.absolute()}")
        dest = pm.add_destination(cwd.name, cwd)

    if not dest:
        raise AmbiguousDestinationError

    install_method_enum = InstallMethod.from_string(install_method)

    if (
        install_method_enum != InstallMethod.COPY or install_method is None
    ) and is_windows():
        logging.warning(
            f"Install method {install_method} is not supported on "
            f"Windows, changing it to 'copy'"
        )
        install_method_enum = InstallMethod.COPY

    pkg = PkgConfig(
        name=name,
        url=repository_url,
        package_root=package_root_value,
        updates_disabled=disable_updates,
        branch=branch,
        install_method=install_method_enum.value,
    )

    if not pm.is_package_registered(dest, pkg):
        pm.add_package(dest, pkg)

    pkg_name = render_package_name(pm, dest, pkg)

    try:
        with console.status(f"[bold green]Installing {pkg_name}..."):
            pm.install_package(dest, pkg)
            location = pm.package_install_location(dest, pkg).relative_to(
                pm.project_root_directory()
            )
            pkg_name = render_package_name(pm, dest, pkg)
            success(
                f"Successfully installed package {pkg_name} at '{location}'",
            )
    except PackageRootDirNotFoundError as err:
        pm.remove_package(dest, pkg)
        raise err
