import argparse
import inspect
import logging
import sys
from pathlib import Path

from git import InvalidGitRepositoryError
from rich.logging import RichHandler
from rich.table import Table
from rich.tree import Tree

from gitpkg._version import __version__
from gitpkg.config import Destination, PkgConfig
from gitpkg.console import console, fatal, success
from gitpkg.errors import (
    AmbiguousDestinationError,
    CouldNotFindDestinationError,
    GitPkgError,
    PackageAlreadyInstalledError,
    PackageRootDirNotFoundError,
    UnknownPackageError,
)
from gitpkg.pkg_manager import PkgManager, PkgUpdateResult
from gitpkg.utils import extract_repository_name_from_url

_COMMAND_PREFIX = "command_"


class CLI:
    _pkg_manager: PkgManager | None = None
    _args: list[str] = None
    _debug_mode: bool = False

    def __init__(self, enable_debug_mode: bool = False):
        self._debug_mode = enable_debug_mode

    def run(self, args: list[str] | None = None):
        if args is None:
            args = sys.argv

        self._args = args

        if self._debug_mode:
            logging.basicConfig(
                level=logging.DEBUG,
                handlers=[RichHandler()],
            )

        parser = argparse.ArgumentParser(
            description="A git powered package manager built on top of submodules.",
            usage=f"""git pkg <command> [<args>]

Commands:
{self._create_commands_list_str()}
        """,
        )

        parser.add_argument("command", help="Subcommand to run")
        parser.add_help = False

        args = parser.parse_args(self._args[1:2])
        logging.debug(args)

        cmd = args.command.replace(":", "_")

        command_func = f"{_COMMAND_PREFIX}{cmd}"

        if not hasattr(self, command_func):
            parser.print_help()
            fatal(f"Unrecognized command: {args.command}")

        # reset package manager for every run
        self._pkg_manager = None

        try:
            getattr(self, command_func)()
        except GitPkgError as err:
            fatal(err.raw_message)

    def _create_commands_list_str(self) -> str:
        # TODO: improve column rendering
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

    @property
    def _pm(self):
        """Initializes package manager only when needed"""
        if self._pkg_manager:
            return self._pkg_manager

        try:
            self._pkg_manager = PkgManager.from_environment()
            return self._pkg_manager
        except InvalidGitRepositoryError:
            fatal("could not find a git repository")

    def _render_package_name(
        self,
        dest: Destination,
        pkg: PkgConfig,
        hide_dest: bool = False,
        hide_stats: bool = False,
    ) -> str:
        prefix = ""
        pkg_name = f"[bold]{pkg.name}[/bold]"
        suffix = ""

        if not hide_stats and self._pm.is_package_installed(dest, pkg):
            stats = self._pm.package_stats(dest, pkg)
            if stats:
                suffix = f" ({stats.commit_hash[0:7]})"

        if not hide_dest and len(self._pm.destinations()) > 1:
            count = 0
            for d in self._pm.destinations():
                if self._pm.is_package_registered(d, pkg):
                    count += 1
            if count > 1:
                prefix = f"{dest.name}/"
        return prefix + pkg_name + suffix

    def _package_param(self, package_name: str) -> tuple[str | None, str | None]:
        if "/" in package_name:
            dest_name, pkg_name = package_name.split("/")
            return dest_name, pkg_name
        return None, package_name

    def _determine_package_dest(
        self,
        dest_name: str | None = None,
        pkg_name: str | None = None,
        return_none: bool = False,
    ) -> Destination | None:
        if dest_name:
            return self._pm.find_destination(dest_name)

        if len(self._pm.destinations()) == 1:
            return self._pm.destinations()[0]

        if pkg_name is not None:
            found_num = 0
            found_dest = None

            for dest in self._pm.destinations():
                for pkg in self._pm.find_packages_by_destination(dest):
                    if pkg.name == pkg_name:
                        found_num += 1
                        found_dest = dest

            if found_dest and found_num == 1:
                return found_dest

        if return_none:
            return None

        raise AmbiguousDestinationError

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

        table.add_column("Name", overflow="fold")
        table.add_column("Path", overflow="fold")

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

        args = parser.parse_args(self._args[2:])
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
            "-rn",
            "--package-root-with-name",
            help="combines --package-root and --name into one command, name is"
            "determined by package roots filename",
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

        args = parser.parse_args(self._args[2:])
        logging.debug(args)

        name = args.name

        if args.package_root_with_name:
            args.package_root = args.package_root_with_name
            name = args.package_root_with_name.split("/")[-1]

        if not name:
            name = extract_repository_name_from_url(args.repository_url)

        dest = self._determine_package_dest(args.dest_name, return_none=True)

        # if no destinations are known add current location as dest
        if not dest and len(self._pm.destinations()) == 0:
            cwd = Path.cwd()

            logging.debug(f"register cwd as destination {cwd.absolute()}")
            dest = self._pm.add_destination(cwd.name, cwd)

        if not dest:
            raise AmbiguousDestinationError

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
        )

        if not self._pm.is_package_registered(dest, pkg):
            self._pm.add_package(dest, pkg)

        pkg_name = self._render_package_name(dest, pkg)

        try:
            with console.status(f"[bold green]Installing {pkg_name}..."):
                self._pm.install_package(dest, pkg)
                location = self._pm.package_install_location(dest, pkg).relative_to(
                    self._pm.project_root_directory()
                )
                pkg_name = self._render_package_name(dest, pkg)
                success(
                    f"Successfully installed package {pkg_name} at '{location}'",
                )
        except PackageRootDirNotFoundError as err:
            self._pm.remove_package(dest, pkg)
            raise err

    def command_list(self):
        """List installed packages"""

        if len(self._pm.destinations()) == 0:
            console.print(
                "No destinations registered yet, please do so via dest:register",
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

        for dest in self._pm.destinations():
            for pkg in self._pm.find_packages_by_destination(dest):
                found_one = True

                install_dir = self._pm.package_install_location(dest, pkg).relative_to(
                    self._pm.project_root_directory()
                )

                stats = self._pm.package_stats(dest, pkg)

                table.add_row(
                    self._render_package_name(
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
            console.print("No packages have been installed yet, add one via 'add URL'")
            return

        console.print(table)

    def command_remove(self):
        """Add and install a new repository to a destination"""

        parser = argparse.ArgumentParser(
            description=inspect.stack()[0][3].__doc__,
        )

        parser.add_argument(
            "package",
            help="Name of the repository",
            type=str,
        )

        args = parser.parse_args(self._args[2:])
        logging.debug(args)

        dest_name, pkg_name = self._package_param(args.package)
        dest = self._determine_package_dest(dest_name, pkg_name)

        pkg = self._pm.find_package(dest, pkg_name)

        if not pkg:
            fatal(f"Could not find package '{pkg_name}' in any dest.")

        pkg_name = self._render_package_name(dest, pkg)
        self._pm.uninstall_package(dest, pkg)
        success(f"Successfully uninstalled package {pkg_name}")

    def command_install(self):
        """Install packages added to the config and apply config changes"""
        tree = Tree("Installed packages:")

        found_any = False

        with console.status("[bold green]Installing packages...") as status:
            for dest in self._pm.destinations():
                for pkg in self._pm.find_packages_by_destination(dest):
                    pkg_name = self._render_package_name(dest, pkg)
                    status.update(f"[bold green]Installing {pkg_name}...")

                    found_any = True

                    try:
                        self._pm.install_package(dest, pkg)
                    except PackageAlreadyInstalledError:
                        pkg_name = self._render_package_name(dest, pkg)
                        tree.add(
                            f"{pkg_name} is already installed.",
                            style="dim",
                            guide_style="dim",
                        )
                        continue

                    pkg_name = self._render_package_name(dest, pkg)
                    tree.add(f"{pkg_name} has been installed.")

            if found_any:
                console.print(tree)
                return

            console.print("No packages were installed.")

    def command_update(self):
        """Update all (or one of the specified) packages."""

        parser = argparse.ArgumentParser(
            description=inspect.stack()[0][3].__doc__,
        )

        parser.add_argument(
            "packages",
            help="Name of the repositories",
            action="extend",
            nargs="*",
        )

        parser.add_argument(
            "--force",
            help="Discoards untracked changes in repositories to update them",
            action="store_true",
        )

        parser.add_argument(
            "--check",
            help="Only check if updates are available, do not actually update",
            action="store_true",
        )

        args = parser.parse_args(self._args[2:])
        logging.debug(args)

        to_install: list[tuple[Destination, PkgConfig]] = []

        for pkg_param in args.packages:
            dest_name, pkg_name = self._package_param(pkg_param)

            dest = self._determine_package_dest(dest_name, pkg_name)

            if not dest:
                # TODO: add better error
                msg = "..."
                raise CouldNotFindDestinationError(msg)

            pkg = self._pm.find_package(dest, pkg_name)

            if pkg is None:
                # TODO: add better error, this error is shit
                raise UnknownPackageError(dest, pkg_name)

            to_install.append((dest, pkg))

        # Nothing added means add them all
        if len(args.packages) == 0:
            for dest in self._pm.destinations():
                for pkg in self._pm.find_packages_by_destination(dest):
                    to_install.append((dest, pkg))

        tree = Tree("Package update results:")

        updated_packages: dict[str, PkgUpdateResult] = {}

        with console.status("[bold green]Updating packages...") as status:
            for dest, pkg in to_install:
                pkg_ident = self._pm.package_identifier(dest, pkg)

                # there is no need to update a repo again if two
                # packages share it
                if pkg_ident not in updated_packages:
                    pkg_name = self._render_package_name(dest, pkg)
                    status.update(f"[bold green]Updating {pkg_name}...")

                    stats_before_update = self._pm.package_stats(dest, pkg)
                    updated_packages[pkg_ident] = self._pm.update_package(
                        dest,
                        pkg,
                        discard_untracked_changes=args.force,
                        check_only=args.check,
                    )

                update_result = updated_packages[pkg_ident]

                pkg_name = self._render_package_name(dest, pkg)

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

    def command_version(self):
        console.print(__version__)
