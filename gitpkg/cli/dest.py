import logging
from pathlib import Path

import rich_click as click
from rich.table import Table

from gitpkg.cli.console import console, success
from gitpkg.cli.root import Context


@click.group("dest", help="Manage package destinations")
def cmd_dest():
    pass


@cmd_dest.command("list", help="List added destinations")
@click.pass_obj
def cmd_dest_list(ctx: Context) -> None:
    pm = ctx.package_manager()

    if len(pm.destinations()) == 0:
        console.print("No destinations registered yet!")
        return

    table = Table(
        title="Destinations",
        show_header=True,
        header_style="bold magenta",
        box=None,
    )

    table.add_column("Name", overflow="fold")
    table.add_column("Path", overflow="fold")

    for dest in pm.destinations():
        table.add_row(dest.name, str(Path(dest.path).absolute()))

    console.print(table)


@cmd_dest.command("add", help="Adds a new destination")
@click.argument(
    "path",
    type=click.Path(exists=False),
)
@click.option(
    "--name",
    help="Give the destination a name, this name is by default determined "
    "by the target name",
)
@click.pass_obj
def cmd_dest_add(ctx: Context, path: str, name: str | None) -> None:
    pm = ctx.package_manager()

    dest_path = Path().absolute() / path
    logging.debug(f"New destination path: '{dest_path}'")

    if not dest_path.exists():
        dest_path.mkdir(parents=True)

    dest_name = dest_path.name

    if name:
        dest_name = name

    logging.debug(f"New destination name: '{name}'")

    dest = pm.add_destination(dest_name, dest_path)

    success(f"Successfully registered destination '{dest.name}'")


# TODO: add remove command
