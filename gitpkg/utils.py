import logging
import re
import shutil
import stat
import sys
import time
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

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
    redo_func: Callable[[str], None], path: str, err: tuple[Exception, any, any]
) -> None:
    """This function aims to make readonly files deletable on windows using
    the shutil.rmtree onerror functions"""
    p = Path(path)
    exception = err[1]
    logging.warning(f"Something went wrong with {p.absolute()}: {exception}")

    if sys.platform != "win32":
        return

    if isinstance(exception, PermissionError):
        logging.debug(f"Something went wrong with {p.absolute()}: {exception}")

        match exception.errno:
            # permission denied due to read-only file, add write permission
            case 13:
                p.chmod(stat.S_IWRITE)
                redo_func(path)
            # ...due to file being in use, rename it and sleep some
            case 5, 32:
                time.sleep(1)

                new_path = p.parent / str(uuid4())
                p.rename(new_path)

                redo_func(str(new_path))
