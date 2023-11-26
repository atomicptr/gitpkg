from typing import TYPE_CHECKING

import rich_click as click
from rich.tree import Tree

from gitpkg.cli.console import console
from gitpkg.cli.helpers import (
    determine_package_destination,
    parse_package_name,
    render_package_name,
)
from gitpkg.cli.root import Context
from gitpkg.errors import CouldNotFindDestinationError, UnknownPackageError
from gitpkg.pkg_manager import PkgUpdateResult

if TYPE_CHECKING:
    from gitpkg.config import Destination, PkgConfig


@click.command("update", help="Update all (or one of the specified) packages")
@click.argument("packages", nargs=-1)
@click.option(
    "--force",
    help="Discards untracked changes in repositories to update them",
    is_flag=True,
)
@click.option(
    "--check",
    help="Only check if updates are available, do not actually update",
    is_flag=True,
)
@click.pass_obj
def cmd_update(
    ctx: Context, packages: list[str], force: bool, check: bool
) -> None:
    pm = ctx.package_manager()

    to_install: list[tuple[Destination, PkgConfig]] = []

    for pkg_param in packages:
        dest_name, pkg_name = parse_package_name(pkg_param)

        dest = determine_package_destination(pm, dest_name, pkg_name)

        if not dest:
            # TODO: add better error
            msg = "..."
            raise CouldNotFindDestinationError(msg)

        pkg = pm.find_package(dest, pkg_name)

        if pkg is None:
            # TODO: add better error, this error is shit
            raise UnknownPackageError(dest, pkg_name)

        to_install.append((dest, pkg))

    # Nothing added means add them all
    if len(packages) == 0:
        for dest in pm.destinations():
            for pkg in pm.find_packages_by_destination(dest):
                to_install.append((dest, pkg))

    tree = Tree("Package update results:")

    updated_packages: dict[str, PkgUpdateResult] = {}

    with console.status("[bold green]Updating packages...") as status:
        for dest, pkg in to_install:
            pkg_ident = pm.package_identifier(dest, pkg)

            # there is no need to update a repo again if two
            # packages share it
            if pkg_ident not in updated_packages:
                pkg_name = render_package_name(pm, dest, pkg)
                status.update(f"[bold green]Updating {pkg_name}...")

                stats_before_update = pm.package_stats(dest, pkg)
                updated_packages[pkg_ident] = pm.update_package(
                    dest,
                    pkg,
                    discard_untracked_changes=force,
                    check_only=check,
                )

            update_result = updated_packages[pkg_ident]

            pkg_name = render_package_name(pm, dest, pkg)

            match update_result:
                case PkgUpdateResult.NO_UPDATE_AVAILABLE:
                    tree.add(
                        f"{pkg_name} is already up to date.",
                        style="dim",
                        guide_style="dim",
                    )
                case PkgUpdateResult.UPDATES_DISABLED:
                    tree.add(f"{pkg_name} has updates disabled.")
                case PkgUpdateResult.UPDATED:
                    old_hash = stats_before_update.commit_hash[0:7]
                    tree.add(
                        f"{pkg_name} was updated from ({old_hash})",
                        style="green",
                        guide_style="green",
                    )
                case PkgUpdateResult.UPDATE_AVAILABLE:
                    tree.add(
                        f"{pkg_name} has updates available!",
                        style="green",
                        guide_style="green",
                    )
                case PkgUpdateResult.UNTRACKED_CHANGES:
                    tree.add(
                        f"{pkg_name} has untracked changes, update aborted!",
                        style="red",
                        guide_style="red",
                    )

        console.print(tree)
