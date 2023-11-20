import os

from tests.git_composer import GitComposer


def teardown_module():
    if os.environ.get("GITPKG_DEBUG") is not None:
        return
    GitComposer.cleanup()
