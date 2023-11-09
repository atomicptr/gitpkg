def extract_repository_name_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", maxsplit=1)[-1].removesuffix(".git")
