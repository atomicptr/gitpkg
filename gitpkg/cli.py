import argparse
import inspect
import logging
import os
import sys
from pathlib import Path

from git import InvalidGitRepositoryError
from rich.logging import RichHandler
from rich.table import Table

from gitpkg.config import PkgConfig
from gitpkg.console import console, fatal, success
from gitpkg.errors import CouldNotFindDestinationError, GitPkgError
from gitpkg.pkg_manager import PkgManager
from gitpkg.utils import extract_repository_name_from_url

_COMMAND_PREFIX = "command_"


class CLI:
    _pm: PkgManager = None

    def run(self):
        if os.getenv("GITPKG_DEBUG") is not None:
            logging.basicConfig(
                level=logging.DEBUG,
                handlers=[RichHandler()],
            )

        try:
            self._pm = PkgManager.from_environment()
        except InvalidGitRepositoryError:
            fatal("could not find a git repository")

        parser = argparse.ArgumentParser(
            description="A git powered package manager built on top of submodules.",
            usage=f"""git pkg <command> [<args>]

Commands:
{self._create_commands_list_str()}
        """,
        )

        parser.add_argument("command", help="Subcommand to run")
        parser.add_help = False

        args = parser.parse_args(sys.argv[1:2])
        logging.debug(args)

        cmd = args.command.replace(":", "_")

        command_func = f"{_COMMAND_PREFIX}{cmd}"

        if not hasattr(self, command_func):
            parser.print_help()
            fatal(f"Unrecognized command: {args.command}")

        try:
            getattr(self, command_func)()
        except GitPkgError as err:
            fatal(err.raw_message)

    def _create_commands_list_str(self) -> str:
        commands: list[tuple[str, str]] = []

        for member in dir(self):
            if not member.startswith(_COMMAND_PREFIX):
                continue
            commands.append(
                (
                    member[len(_COMMAND_PREFIX) :].replace("_", ":"),
                    getattr(self, member).__doc__,
                ),
            )

        commands = sorted(commands, key=lambda cmd: cmd[0])

        command_names = [cmd[0] for cmd in commands]
        max_len = len(max(command_names, key=len))

        commands_list = ""

        for command, desc in commands:
            commands_list += f"\t{command.ljust(max_len)}\t{desc}\n"

        return commands_list

    def command_dest_list(self):
        """List registered destinations"""

        if len(self._pm.destinations()) == 0:
            console.print(
                "No destinations registered yet, please do so via "
                "destinations:register",
            )
            return

        table = Table(
            title="Destinations",
            show_header=True,
            header_style="bold magenta",
            box=None,
        )

        table.add_column("Name")
        table.add_column("Path")

        for dest in self._pm.destinations():
            table.add_row(dest.name, str(Path(dest.path).absolute()))

        console.print(table)

    def command_dest_register(self):
        """Register a new destination"""

        parser = argparse.ArgumentParser(
            description=inspect.stack()[0][3].__doc__,
        )

        parser.add_argument(
            "path",
            help="Path to the destination, if it does not exist it will be "
            "created automatically.",
            type=str,
        )
        parser.add_argument(
            "--name",
            help="Give the destination a name, this name is by default "
            "determined by the target name.",
            type=str,
        )

        args = parser.parse_args(sys.argv[2:])
        logging.debug(args)

        dest_path = Path().absolute() / args.path
        logging.debug(f"New destination path: '{dest_path}'")

        if not dest_path.exists():
            dest_path.mkdir(parents=True)

        name = dest_path.name

        if args.name:
            name = args.name

        logging.debug(f"New destination name: '{name}'")

        dest = self._pm.add_destination(name, dest_path)

        success(f"Successfully registered destination '{dest.name}'")

    def command_add(self):
        """Add and install a new repository to a destination"""

        parser = argparse.ArgumentParser(
            description=inspect.stack()[0][3].__doc__,
        )

        parser.add_argument(
            "repository_url",
            help="Repository to add",
            type=str,
        )

        parser.add_argument(
            "--name",
            help="Overwrite the name of the repository",
            type=str,
        )

        parser.add_argument(
            "--dest-name",
            help="Target destination name",
            type=str,
        )

        parser.add_argument(
            "-r",
            "--package-root",
            help="Define the root directory of the repository (directory "
            "inside the repository to be used as the repository)",
            type=str,
        )

        parser.add_argument(
            "-b",
            "--branch",
            help="Define the branch to be used, defaults to the repository default",
            type=str,
        )

        parser.add_argument(
            "--disable-updates",
            help="Disable auto updates for this repository",
            action="store_true",
        )

        parser.add_argument(
            "--install-method",
            help="",
            choices=["link", "direct"],
            type=str,
        )

        args = parser.parse_args(sys.argv[2:])
        logging.debug(args)

        dest = None

        # no dest specified and only one is available? Auto pick that one
        if not args.dest_name and len(self._pm.destinations()) == 1:
            dest = self._pm.destinations()[0]

        if args.dest_name:
            dest = self._pm.destination_by_name(args.dest_name)

            if not dest:
                raise CouldNotFindDestinationError(args.dest_name)

        if not dest:
            cwd = Path.cwd()

            logging.debug(f"register cwd as destination {cwd.absolute()}")
            dest = self._pm.add_destination(cwd.name, cwd)

        name = args.name

        if not name:
            name = extract_repository_name_from_url(args.repository_url)

        # TODO: validate url

        package_root = "."

        if args.package_root:
            package_root = args.package_root

        pkg = PkgConfig(
            name=name,
            url=args.repository_url,
            package_root=package_root,
            updates_disabled=args.disable_updates,
            branch=args.branch,
            install_method=args.install_method,
        )

        if not self._pm.has_package_been_added(dest, pkg):
            self._pm.add_package(dest, pkg)

        with console.status(f"[bold green]Installing '{pkg.name}'..."):
            self._pm.install_package(dest, pkg)
            location = self._pm.package_install_location(dest, pkg)
            success(
                f"Successfully installed package '{pkg.name}' at '{location}'",
            )

    def command_list(self):
        """List installed packages"""

        if len(self._pm.destinations()) == 0:
            console.print(
                "No destinations registered yet, please do so via "
                "destinations:register",
            )
            return

        table = Table(
            title="Packages",
            show_header=True,
            header_style="bold magenta",
            box=None,
        )

        table.add_column("Name")
        table.add_column("Install Dir")
        table.add_column("Hash")
        table.add_column("Last Update")

        found_one = False

        for dest in self._pm.destinations():
            for pkg in self._pm.packages_by_destination(dest):
                found_one = True

                install_dir = self._pm.package_install_location(dest, pkg).relative_to(
                    self._pm.project_root_directory()
                )

                stats = self._pm.package_stats(dest, pkg)

                table.add_row(
                    pkg.name,
                    str(install_dir),
                    stats.get("commit")[0:7] if "commit" in stats else None,
                    stats.get("date").isoformat() if "date" in stats else None,
                )

        if not found_one:
            console.print("No packages have been installed yet, add one via 'add URL'")
            return

        console.print(table)
