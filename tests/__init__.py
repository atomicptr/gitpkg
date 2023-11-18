from tests.git_composer import GitComposer


def teardown_module():
    GitComposer.cleanup()
