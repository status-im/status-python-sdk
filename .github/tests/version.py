"""
Verify that pyproject.toml version is greater than `main` branch want
"""
import tomllib
import urllib.request
from packaging.version import Version
from pathlib import Path

def read_version(raw: bytes) -> str:
    """
    Extract the `version` from `pyproject.toml`
    """
    return tomllib.loads(raw.decode())["project"]["version"]


def fetch_current_version() -> str:
    """
    Read `pyproject.toml` file from the working tree.
    """
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    return read_version(pyproject.read_bytes())


def fetch_base_version(repo: str = "status-im/status-python-sdk", branch: str = "master") -> str:
    """
    Fetch `pyproject.toml` file from Github.
    """
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/pyproject.toml"

    with urllib.request.urlopen(url, timeout=30) as response:
        return read_version(response.read())



if __name__ == "__main__":
    current_version = Version(fetch_current_version())
    uploaded_version = Version(fetch_base_version())

    if current_version <= uploaded_version:
        raise Exception(f"Branch version ({current_version}) must be greater than GitHub `master` ({uploaded_version}). Please update pyproject.toml")
