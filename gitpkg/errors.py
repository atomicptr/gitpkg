from pathlib import Path


class GitPkgError(Exception):
    raw_message: str = None

    def __init__(self, message: str):
        self.raw_message = message
        super().__init__(f"ERROR: git pkg: {message}")


class DestinationWithNameAlreadyExists(GitPkgError):
    def __init__(self, name: str):
        super().__init__(f"destination with name '{name}' already exists.")


class DestinationWithPathAlreadyExists(GitPkgError):
    def __init__(self, path: Path):
        super().__init__(
            f"destination with path '{path.absolute()}' already exists.",
        )
