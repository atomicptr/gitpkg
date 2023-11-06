from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dataclass_binder import Binder


@dataclass
class PkgManager:
    name: str
    url: str
    package_root: str
    updates_enabled: bool | None = None
    branch: str | None = None
    install_mode: str | None = None


@dataclass
class Destination:
    name: str
    path: str


@dataclass
class Config:
    packages: dict[str, PkgManager] = field(default_factory=dict)
    destinations: list[Destination] = field(default_factory=list)

    @staticmethod
    def from_path(path: Path) -> Config:
        return Binder(Config).parse_toml(path)

    def to_toml_string(self) -> str:
        return "\n".join(
            line for line in Binder(self).format_toml()
        )
