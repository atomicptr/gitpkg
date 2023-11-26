import logging
from pathlib import Path

import rich_click as click

from gitpkg.cli.console import console, success
from gitpkg.cli.helpers import (
    determine_package_destination,
    render_package_name,
)
from gitpkg.cli.root import Context, root
from gitpkg.config import PkgConfig
from gitpkg.errors import AmbiguousDestinationError, PackageRootDirNotFoundError
from gitpkg.utils import extract_repository_name_from_url


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
) -> None:
    pm = ctx.package_manager()

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

    pkg = PkgConfig(
        name=name,
        url=repository_url,
        package_root=package_root_value,
        updates_disabled=disable_updates,
        branch=branch,
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