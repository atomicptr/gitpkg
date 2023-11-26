from dataclasses import dataclass
from pathlib import Path

import rich_click as click
from rich_click import Context as CLIContext

from gitpkg.pkg_manager import PkgManager


@dataclass
class Context:
    repository_root: str | None
    debug_mode: bool

    def package_manager(self) -> PkgManager:
        if self.repository_root:
            return PkgManager.from_path(Path(self.repository_root))
        return PkgManager.from_environment()


@click.group()
@click.option(
    "--repository-root",
    help="Define the repository root directory, by default git pkg will "
    "search for the nearest git repository by itself.",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    envvar="GITPKG_REPOSITORY_ROOT",
)
@click.option(
    "--debug",
    help="Enable debug setting.",
    is_flag=True,
    envvar="GITPKG_DEBUG",
)
@click.pass_context
def root(ctx: CLIContext, repository_root: str | None, debug: bool):
    ctx.obj = Context(repository_root, debug)
