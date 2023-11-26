import logging
import re
import shutil
import stat
import sys
from collections.abc import Callable
from pathlib import Path

_REPOSITORY_PARSE_REGEX = [
    r"ssh://(?P<domain>.+)/(?P<owner>.+)/(?P<repo>.+).git",
    r"git://(?P<domain>.+)/(?P<owner>.+)/(?P<repo>.+).git",
    r"git@(?P<domain>.+):(?P<owner>.+)/(?P<repo>.+).git",
    r"https?://(?P<domain>.+)/(?P<owner>.+)/(?P<repo>.+).git",
    r"https?://(?P<domain>.+)/(?P<owner>.+)/(?P<repo>.+)",
]


def parse_repository_url(url: str) -> tuple[str, str] | None:
    for regex in _REPOSITORY_PARSE_REGEX:
        res = re.findall(regex, url)
        if res:
            _, _, name = res[0]
            return url, name
    p = Path(url)
    if p.exists():
        return str(p.as_posix()), p.name.removesuffix(".git")
    return None


def extract_repository_name_from_url(url: str) -> str:
    _, name = parse_repository_url(url)
    return name


def does_actually_exist(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def is_symlink(path: Path) -> bool:
    return does_actually_exist(path) and path.is_symlink()


def safe_dir_delete(path: Path) -> None:
    if not does_actually_exist(path):
        return

    if is_symlink(path):
        path.unlink()
        return

    shutil.rmtree(path, onerror=fix_permissions)


def fix_permissions(
    redo_func: Callable[[str], None], path: str, err: any
) -> None:
    """This function aims to make readonly files deletable on windows using
    the shutil.rmtree onerror functions"""
    if sys.platform != "win32":
        return
    p = Path(path)
    logging.debug(f"Something went wrong with {p.absolute()}: {err}")
    p.chmod(stat.S_IWRITE)
    redo_func(path)
