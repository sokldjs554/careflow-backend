import tomllib
from pathlib import Path

from app.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def _dependency_names() -> set[str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    names: set[str] = set()
    for requirement in project["dependencies"]:
        name = requirement.split("[", 1)[0].split(">", 1)[0].split("<", 1)[0].split("=", 1)[0]
        names.add(name.strip().lower())
    return names


def test_default_sqlite_runtime_has_its_async_driver() -> None:
    settings = Settings()

    assert settings.database_url.startswith("sqlite+aiosqlite://")
    assert "aiosqlite" in _dependency_names()
