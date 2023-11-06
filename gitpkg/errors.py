class GitPkgError(Exception):
    raw_message: str = None

    def __init__(self, message: str):
        self.raw_message = message
        super().__init__(f"ERROR: git pkg: {message}")
