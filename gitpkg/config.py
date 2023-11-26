from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from dataclass_binder import Binder


class InstallMethod(Enum):
    LINK = "link"
    COPY = "copy"

    @staticmethod
    def from_string(install_method: str | None) -> InstallMethod:
        if not install_method:
            return InstallMethod.LINK

        try:
            return InstallMethod(install_method)
        except ValueError:
            logging.exception("could not determine install method")

        return InstallMethod.LINK


@dataclass
class PkgConfig:
    name: str
    url: str
    package_root: str
    updates_disabled: bool = False
    branch: str | None = None
    install_method: str | None = None

    def get_install_method(self) -> InstallMethod:
        return InstallMethod.from_string(self.install_method)


@dataclass
class Destination:
    name: str
    path: str


@dataclass
class Config:
    packages: dict[str, list[PkgConfig]] = field(default_factory=dict)
    destinations: list[Destination] = field(default_factory=list)

    @staticmethod
    def from_path(path: Path) -> Config:
        return Binder(Config).parse_toml(path)

    def to_toml_string(self) -> str:
        lines = []

        for dest_name in self.packages:
            for pkg in self.packages[dest_name]:
                lines.append(f"[[packages.{dest_name}]]")
                lines.append(f'name = "{pkg.name}"')
                lines.append(f'url = "{pkg.url}"')
                if pkg.package_root:
                    lines.append(f'package-root = "{pkg.package_root}"')
                if pkg.updates_disabled:
                    lines.append("updates-disabled = true")
                if pkg.branch:
                    lines.append(f'branch = "{pkg.branch}"')
                if pkg.get_install_method() != InstallMethod.LINK:
                    lines.append(f'install-method = "{pkg.install_method}"')
                lines.append("")

        for dest in self.destinations:
            lines.append("[[destinations]]")
            lines.append(f'name = "{dest.name}"')
            lines.append(f'path = "{dest.path}"')
            lines.append("")

        return "\n".join(lines)
