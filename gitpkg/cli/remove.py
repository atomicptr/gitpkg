import rich_click as click

from gitpkg.cli.console import fatal, success
from gitpkg.cli.helpers import (
    determine_package_destination,
    parse_package_name,
    render_package_name,
)
from gitpkg.cli.root import Context, root


@root.command("remove", help="Remove a package")
@click.argument("package_name")
@click.pass_obj
def cmd_remove(ctx: Context, package_name: str) -> None:
    pm = ctx.package_manager()

    dest_name, pkg_name = parse_package_name(package_name)
    dest = determine_package_destination(pm, dest_name, pkg_name)

    pkg = pm.find_package(dest, pkg_name)

    if not pkg:
        fatal(f"Could not find package '{pkg_name}' in any dest.")

    pkg_name = render_package_name(pm, dest, pkg)
    pm.uninstall_package(dest, pkg)
    success(f"Successfully uninstalled package {pkg_name}")
