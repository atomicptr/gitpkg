from gitpkg.utils import parse_repository_url
from tests import GitComposer


def test_parse_repository_url():
    git = GitComposer()
    git.setup("test_parse_repository_url")

    repo_path = git.create_repository("test_repo")

    for input_url, expected_name in [
        ("https://github.com/atomicptr/gitpkg", "gitpkg"),
        ("https://github.com/atomicptr/gitpkg.git", "gitpkg"),
        ("ssh://git@github.com:atomicptr/gitpkg.git", "gitpkg"),
        ("git://git@github.com:atomicptr/gitpkg.git", "gitpkg"),
        ("git@github.com:atomicptr/gitpkg.git", "gitpkg"),
        ("https://gitlab.com/gitlab-org/gitlab-core-team/general", "general"),
        ("git@gitlab.com:gitlab-org/gitlab-core-team/general.git", "general"),
        ("ssh://root@8.8.8.8:443/path/to/repo.git", "repo"),
        (str(repo_path.path().absolute()), "test_repo"),
    ]:
        res = parse_repository_url(input_url)

        if expected_name is None:
            assert res is None
            continue

        assert res is not None, f"Could not parse {input_url}"

        _, name = res

        assert name == expected_name
