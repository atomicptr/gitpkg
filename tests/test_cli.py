import os

import tomllib

from gitpkg.cli import CLI
from tests.git_composer import GitComposer

git = GitComposer()


def setup_function():
    git.setup()


def teardown_function():
    git.teardown()


def test_register_destination():
    repo = git.create_repository("test_repo")
    os.chdir(repo.abs())
    vendor_dir = repo.abs() / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)

    cli = CLI()
    cli.run([__file__, "dest:register", vendor_dir.name])

    toml_path = vendor_dir / ".." / ".gitpkg.toml"

    assert toml_path.exists()

    tomldata = tomllib.loads(toml_path.read_text())

    print(tomldata)

    assert "destinations" in tomldata
    assert len(tomldata["destinations"]) > 0
    assert tomldata["destinations"][0]["name"] == "vendor"
