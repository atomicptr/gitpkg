import rich_click as click
from rich.table import Table

from gitpkg.cli.console import console
from gitpkg.cli.helpers import render_package_name
from gitpkg.cli.root import Context, root


@root.command("list", help="List packages")
@click.pass_obj
def cmd_list(ctx: Context) -> None:
    pm = ctx.package_manager()

    """List installed packages"""

    if len(pm.destinations()) == 0:
        console.print(
            "No destinations registered yet",
        )
        return

    table = Table(
        title="Packages",
        show_header=True,
        header_style="bold magenta",
        box=None,
    )

    table.add_column("Name", overflow="fold")
    table.add_column("Install Dir", overflow="fold")
    table.add_column("Hash", overflow="fold")
    table.add_column("Last Update", overflow="fold")

    found_one = False

    for dest in pm.destinations():
        for pkg in pm.find_packages_by_destination(dest):
            found_one = True

            install_dir = pm.package_install_location(dest, pkg).relative_to(
                pm.project_root_directory()
            )

            stats = pm.package_stats(dest, pkg)

            table.add_row(
                render_package_name(
                    pm,
                    dest,
                    pkg,
                    hide_dest=True,
                    hide_stats=True,
                ),
                str(install_dir),
                stats.commit_hash[0:7] if stats else None,
                stats.commit_date.isoformat() if stats else None,
            )

    if not found_one:
        console.print(
            "No packages have been installed yet, add one via 'add URL'"
        )
        return

    console.print(table)
