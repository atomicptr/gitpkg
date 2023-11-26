from gitpkg.cli.add import cmd_add
from gitpkg.cli.dest import cmd_dest
from gitpkg.cli.install import cmd_install
from gitpkg.cli.list import cmd_list
from gitpkg.cli.remove import cmd_remove
from gitpkg.cli.root import root
from gitpkg.cli.update import cmd_update
from gitpkg.cli.version import cmd_version

run_cli = root

root.add_command(cmd_dest)
root.add_command(cmd_version)
root.add_command(cmd_add)
root.add_command(cmd_list)
root.add_command(cmd_remove)
root.add_command(cmd_install)
root.add_command(cmd_update)
