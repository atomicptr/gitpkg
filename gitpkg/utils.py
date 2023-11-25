from pathlib import Path


def extract_repository_name_from_url(url: str) -> str:
    # this seems to also work with urls at least as far as our use case goes...
    return Path(url).name.removesuffix(".git")


def symlink_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def escape_url(url: str) -> str:
    if Path(url).exists():
        return str(Path(url).as_posix())
    return url
