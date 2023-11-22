from pathlib import Path


def extract_repository_name_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", maxsplit=1)[-1].removesuffix(".git")


def symlink_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True
