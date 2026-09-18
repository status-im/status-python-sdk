"""
Used outside of `status_sdk`
"""
import shutil, os, subprocess, sys, time, yaml, logging, requests, stat, tarfile
from pathlib import Path
from platform import machine
from typing import Optional
from .. import exceptions
from . import builds

def launch_docker_container(commit: Optional[str] = None, wait_seconds: int = 5, platform: str = "linux/amd64", data_folder: Optional[str] = None):
    """
    Launch the Status Backend Docker container using `docker-compose.yaml`

    NOTE: On Windows, Docker Desktop caches the Docker volume bind mounts in the WSL
    virtual machine. When the mounts go stale the container cannot start. WSL is
    restarted to clear the cache and the container is launched again until it is up.

    Parameters:
        - `commit` - the commit SHA. If no commit is provided, the latest version is pulled
        - `wait_seconds` - number of seconds to wait before the code resumes. Sleep prevents calling `class Account` faster than launching the docker container. This only happens when the container already exists and it is must be turned on. On Windows the same value is used to wait between retries after WSL has been restarted.
        - `platform` - the platform the image is built for. Defaults to `linux/amd64`. Run `docker buildx ls` to see the platforms your Docker installation supports.
        - `data_folder` - the local folder holding the accounts created in Status Backend. Necessary for Community nodes
    """
    logger = logging.getLogger(__name__)
    system = sys.platform
    is_windows = system == "win32"
    if not shutil.which("docker"):
        raise exceptions.DockerError("Please install Docker.")

    if is_windows and not shutil.which("wsl"):
        raise exceptions.DockerError("Please install wsl - https://learn.microsoft.com/en-us/windows/wsl/install.")

    logger.info(f"Running Docker on {system}")
    ref = commit if commit else "develop"
    DOCKER_COMPOSE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docker-compose.yaml")
    # Docker is reached through WSL on Windows, so local paths are passed as `/mnt/<drive>/...`
    to_docker_path = lambda path: f"/mnt/{Path(path).drive.rstrip(':').lower()}/" + "/".join(Path(path).parts[1:]) if is_windows else path
    docker_path = to_docker_path(DOCKER_COMPOSE_PATH)

    with open(DOCKER_COMPOSE_PATH, "r") as f:
        docker_yaml_data: dict = yaml.load(f, Loader=yaml.SafeLoader)

    if not commit:
        url, _, _ = docker_yaml_data["services"]["backend"]["build"]["context"].partition("#")
        org, repo = url.split("/")[-2:]
        repo = repo.replace(".git", "")
        response = requests.get(
            f"https://api.github.com/repos/{org}/{repo}/commits",
            headers={"Accept": "application/vnd.github.sha"},
            timeout=30
        )
        commit = response.json()[0]["sha"]

    logger.info(f"status-im/status-go SHA: {commit}")
    env_params = {
        "STATUS_GO_COMMIT": commit,
        "PLATFORM": platform
    }
    data_volume = '${DATA_DIR:-./data}:/data'
    current_volumes: list[str] = docker_yaml_data["services"]["backend"]["volumes"]
    if data_folder:
        # NOTE: A bare relative path is read as a named Docker volume rather than a bind mount
        data_folder = os.path.join(os.path.abspath(data_folder), "data")
        os.makedirs(data_folder, exist_ok=True)
        data_folder = to_docker_path(data_folder)
        env_params["DATA_DIR"] = data_folder

    is_updated = False
    if data_folder and data_volume not in current_volumes:
        current_volumes.append(data_volume)
        is_updated = True

    if not data_folder and data_volume in current_volumes:
        current_volumes.remove(data_volume)
        is_updated = True

    if is_updated:
        compose_yaml = yaml.dump(docker_yaml_data, Dumper=yaml.SafeDumper, sort_keys=False, default_flow_style=False, indent=4)
        with open(DOCKER_COMPOSE_PATH, "w") as f:
            f.write(compose_yaml)

    cmd = ["env"] + [f"{key}={value}" for key, value in env_params.items()] + ["docker", "compose", "-f", docker_path, "up", "-d", "--build"]

    if is_windows:
        cmd.insert(0, "wsl")

    logger.info(f"Running:\n{' '.join(cmd)}")
    docker_compose_up = lambda: subprocess.run(cmd, cwd=os.path.dirname(DOCKER_COMPOSE_PATH), stderr=subprocess.PIPE, text=True)
    result = docker_compose_up()

    if result.returncode != 0 and is_windows:
        logger.warning("Command failed! Restarting wsl...")
        subprocess.run(["wsl", "--shutdown"])
        attempt = 1
        while result.returncode != 0:
            result = docker_compose_up()
            if result.returncode == 0:
                logger.info(f"Container started on attempt {attempt}!")
                break

            logger.warning(f"Attempt {attempt} failed... Sleeping for {wait_seconds}s")
            time.sleep(wait_seconds)
            attempt += 1

    if result.returncode != 0:
        raise exceptions.DockerError(result.stderr.strip())

    logger.info(f"Docker Container successfully launched! Sleeping for {wait_seconds}s")
    time.sleep(wait_seconds)

def build_and_launch(commit: Optional[str] = None, repo_dir: Optional[str] = None, address: str = "localhost:8080", wait_seconds: int = 30, install_deps: bool = True):
    """
    This is an alternative to `launch_docker_container` for setups that do not use Docker or
    would like to use `status-im/status-go` outside of a Docker container. This will build a
    native clone of `status-im/status-go` inside its Nix dev shell and launch it.

    If `status-backend` already exists at `repo_dir/build/bin/status-backend`, the build is
    skipped entirely (including cloning/fetching `repo_dir` and installing Nix/git) and the
    existing binary is launched directly. Remove the binary, or pass a different `repo_dir`, to
    force a rebuild.

    NOTE: Requires the Nix package manager (https://nixos.org/download) and `git` to be installed.

    Parameters:
        - `commit` - the `status-go` commit SHA, branch or tag to build. If no commit is provided, the latest `develop` branch is built.
        - `repo_dir` - local folder to clone `status-go` into (and reuse on subsequent calls). Defaults to a `status-go` folder next to this package's installation. If the repo is not found then it will be fetched from GitHub
        - `address` - the `host:port` to launch `status-backend` on. Defaults to `localhost:8080`.
        - `wait_seconds` - number of seconds to wait, polling the health endpoint, before giving up on the backend starting. Building itself is not subject to this timeout.
        - `install_deps` - whether to run `make status-go-deps` before building. This also runs `go clean -cache` / `go clean -modcache`, so it is skipped by default - only needed on the first build, or after a Go toolchain upgrade.
    """
    logger = logging.getLogger(__name__)

    def run(cmd: list[str], cwd: Optional[str] = None) -> subprocess.CompletedProcess:
        logger.info(f"Running:\n{' '.join(cmd)}")
        return subprocess.run(cmd, cwd=cwd, stderr=subprocess.PIPE, text=True)

    system = sys.platform

    if system == "win32":
        raise exceptions.BuildError("build_and_launch requires Nix and is not supported on Windows. Use launch_docker_container instead, or run this from within WSL.")

    repo_dir = repo_dir or os.path.join(os.path.dirname(os.path.dirname(__file__)), "status-go")
    binary_path = os.path.join(repo_dir, "build", "bin", "status-backend")

    if os.path.isfile(binary_path):
        logger.info(f"{binary_path} already exists. Skipping build.")
        if system == "darwin":
            builds.fix_nix_build_paths(binary_path)
        builds.launch_build(binary_path, repo_dir, address, wait_seconds)
        return

    if not shutil.which("nix"):
        raise exceptions.BuildError("Please install Nix - https://nixos.org/download.")

    if not shutil.which("git"):
        raise exceptions.BuildError("Please install git.")

    ref = commit if commit else "develop"

    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        result = run(["git", "clone", "https://github.com/status-im/status-go.git", repo_dir])
    else:
        result = run(["git", "fetch", "origin"], cwd=repo_dir)

    if result.returncode != 0:
        raise exceptions.BuildError(result.stderr.strip())

    result = run(["git", "checkout", ref], cwd=repo_dir)
    if result.returncode != 0:
        result = run(["git", "checkout", "-B", ref, f"origin/{ref}"], cwd=repo_dir)
        if result.returncode != 0:
            raise exceptions.BuildError(result.stderr.strip())
    elif ref == "develop":
        result = run(["git", "merge", "--ff-only", "origin/develop"], cwd=repo_dir)
        if result.returncode != 0:
            raise exceptions.BuildError(result.stderr.strip())

    commands = [
        "make status-go-deps",
        "make generate",
        "make status-backend"
    ]
    if not install_deps:
        commands = commands[1:]

    make_targets = " && ".join(commands)
    logger.info("Building status-backend inside the Nix dev shell - this can take a while...")
    result = run(["nix", "--extra-experimental-features", "nix-command flakes", "develop", "--command", "bash", "-c", make_targets], cwd=repo_dir)
    if result.returncode != 0:
        raise exceptions.BuildError(result.stderr.strip())

    if not os.path.isfile(binary_path):
        raise exceptions.BuildError(f"Build finished but {binary_path} was not found.")

    if system == "darwin":
        builds.fix_nix_build_paths(binary_path)

    builds.launch_build(binary_path, repo_dir, address, wait_seconds)

def download_build_and_launch(file_name: Optional[str] = None, repo_name: str = "status-im/status-go", tag: Optional[str] = None, token: Optional[str] = None, address: str = "localhost:8080", wait_seconds: int = 30):
    """
    Download a prebuilt `status-backend` bundle from a GitHub release, extract it and launch it.
    This is an alternative to `build_and_launch` for setups that do not want to build
    `status-im/status-go` from source - no Nix or Go toolchain is needed.

    Parameters:
        - `file_name` - the release asset to download, exactly as it appears on the release page. If not provided, the asset matching this machine is picked
        - `repo_name` - the `owner/name` of the repository
        - `tag` - a release tag. If not provided, the latest release is used
        - `token` - a GitHub token. Required for private repositories
        - `address` - the `host:port` to launch `status-backend` on. Defaults to `localhost:8080`.
        - `wait_seconds` - number of seconds to wait, polling the health endpoint, before giving up on the backend starting. Downloading itself is not subject to this timeout.
    """
    logger = logging.getLogger(__name__)
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    endpoint = f"tags/{tag}" if tag else "latest"
    url = f"https://api.github.com/repos/{repo_name}/releases/{endpoint}"
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    release: dict = response.json()

    name = f"status-backend_{sys.platform}_{machine()}_{release['tag_name'][1:]}".lower()
    assets: list[dict] = [asset for asset in release["assets"] if name in asset["name"]]
    if not assets:
        available_assets = [asset["name"] for asset in release["assets"]]
        raise exceptions.BuildError(f"'{name}' is not in release '{release['tag_name']}'. Available: {', '.join(available_assets) or 'none'}")

    selected = assets[0]
    file_name = selected["name"]
    destination = os.getcwd()
    archive_path = os.path.join(destination, file_name)
    bundle_dir = os.path.join(destination, "status-backend-bundle")
    if not os.path.exists(bundle_dir):
        logger.info(f"Downloading '{file_name}' from release '{release['tag_name']}'...")
        with requests.get(selected["url"], headers={**headers, "Accept": "application/octet-stream"}, stream=True, timeout=300) as download:
            download.raise_for_status()
            with open(archive_path, "wb") as f:
                for chunk in download.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)

        with tarfile.open(archive_path) as archive:
            # Archives created on macOS carry a `._*` metadata file next to every real file
            members = [
                member
                for member in archive.getmembers()
                if not os.path.basename(member.name).startswith("._")
            ]

            # A bundle from a previous release must not mix with the new one
            shutil.rmtree(bundle_dir, ignore_errors=True)
            logger.info(f"Extracting '{file_name}' into {bundle_dir}...")
            # The `data` filter blocks paths escaping `destination`. Only available from Python 3.11.4
            extract_options = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
            archive.extractall(destination, members=members, **extract_options)

        os.remove(archive_path)
    else:
        logger.info("Bundle already exists. Skipping download.")
    # Linux bundles start through `run.sh` so the bundled loader is used, macOS bundles start the binary directly
    launcher = os.path.join(bundle_dir, "run.sh")
    if not os.path.isfile(launcher):
        launcher = os.path.join(bundle_dir, "status-backend")

    if not os.path.isfile(launcher):
        raise exceptions.BuildError(f"'{file_name}' has neither run.sh nor status-backend in {bundle_dir}.")

    if not os.access(launcher, os.X_OK):
        mode = os.stat(launcher).st_mode
        os.chmod(launcher, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    if sys.platform == "darwin" and shutil.which("xattr"):
        # Downloaded files are tagged with `com.apple.quarantine`, which makes Gatekeeper
        result = subprocess.run(["xattr", "-dr", "com.apple.quarantine", bundle_dir], stderr=subprocess.PIPE, text=True)
        if result.returncode != 0 and "No such xattr" not in result.stderr:
            logger.warning(f"Failed to clear quarantine attribute on {bundle_dir}: {result.stderr.strip()}")

    builds.launch_build(launcher, destination, address, wait_seconds)

