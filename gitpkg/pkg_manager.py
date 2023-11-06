import logging
from pathlib import Path

from git import Repo

from gitpkg.config import Config, Destination
from gitpkg.errors import (
    DestinationWithNameAlreadyExists,
    DestinationWithPathAlreadyExists,
)

_CONFIG_FILE = ".gitpkg.toml"


class PkgManager:
    _repo: Repo
    _config: Config

    def __init__(self, repo: Repo, config: Config):
        self._repo = repo
        self._config = config

    def destinations(self) -> list[Destination]:
        return self._config.destinations

    def _write_config(self) -> None:
        logging.debug(f"Written to config file: {self.config_file()}")
        self.config_file().write_text(self._config.to_toml_string())

    def project_root_directory(self):
        return PkgManager._project_root_directory(self._repo)

    def config_file(self) -> Path:
        return self.project_root_directory() / _CONFIG_FILE

    def add_destination(self, name: str, path: Path) -> Destination:
        for dest in self._config.destinations:
            if dest.name == name:
                raise DestinationWithNameAlreadyExists(name)

            if path.absolute() == Path(dest.path).absolute():
                raise DestinationWithPathAlreadyExists(path)

        dest = Destination(
            name,
            str(path.relative_to(self.project_root_directory())),
        )

        logging.debug(f"Added new destination: {dest}")

        self._config.destinations.append(dest)
        self._write_config()

        return dest

    @staticmethod
    def from_environment():
        repo = Repo(Path.cwd(), search_parent_directories=True)
        config = Config()

        config_file = PkgManager._project_root_directory(repo) / _CONFIG_FILE

        if PkgManager._project_root_directory(repo).exists():
            config = Config.from_path(config_file)

        return PkgManager(repo, config)

    @staticmethod
    def _project_root_directory(repo: Repo) -> Path:
        return Path(repo.git_dir).parent
