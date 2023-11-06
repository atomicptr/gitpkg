import argparse
import inspect
import logging
import os
import sys
from pathlib import Path

from git import InvalidGitRepositoryError
from rich.logging import RichHandler

from gitpkg.console import console, fatal, success
from gitpkg.errors import GitPkgError
from gitpkg.pkg_manager import PkgManager

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
            description="A git powered package manager built on top of "
                        "submodules.",
            usage=f"""git pkg <command> [<args>]

Commands:
{self._create_commands_list_str()}
        """)

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
            commands.append((
                member[len(_COMMAND_PREFIX):].replace("_", ":"),
                getattr(self, member).__doc__,
            ))

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

        console.print("Destinations:")

        for dest in self._pm.destinations():
            console.print(f"\t- Name: '{dest.name}'")
            console.print(f"\t  Path: '{Path(dest.path).absolute()}'")

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
