import rich_click as click
from rich.tree import Tree

from gitpkg.cli.console import console
from gitpkg.cli.helpers import render_package_name
from gitpkg.cli.root import Context
from gitpkg.errors import PackageAlreadyInstalledError


@click.command(
    "install",
    help="Install packages added to the config and apply config changes",
)
@click.pass_obj
def cmd_install(ctx: Context) -> None:
    pm = ctx.package_manager()

    tree = Tree("Installed packages:")

    found_any = False

    with console.status("[bold green]Installing packages...") as status:
        for dest in pm.destinations():
            for pkg in pm.find_packages_by_destination(dest):
                pkg_name = render_package_name(pm, dest, pkg)
                status.update(f"[bold green]Installing {pkg_name}...")

                found_any = True

                try:
                    pm.install_package(dest, pkg)
                except PackageAlreadyInstalledError:
                    pkg_name = render_package_name(pm, dest, pkg)
                    tree.add(
                        f"{pkg_name} is already installed.",
                        style="dim",
                        guide_style="dim",
                    )
                    continue

                pkg_name = render_package_name(pm, dest, pkg)
                tree.add(f"{pkg_name} has been installed.")

        if found_any:
            console.print(tree)
            return

        console.print("No packages were installed.")
