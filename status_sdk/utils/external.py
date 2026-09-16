"""
Used outside of `status_sdk`
"""
import shutil, os, subprocess, sys, time, yaml, logging, requests
from pathlib import Path
from typing import Optional
from .. import exceptions

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

    env_params = {
        "STATUS_GO_COMMIT": ref,
        "PLATFORM": platform
    }

    with open(DOCKER_COMPOSE_PATH, "r") as f:
        docker_yaml_data: dict = yaml.load(f, Loader=yaml.SafeLoader)

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

def build_and_launch(commit: Optional[str] = None, repo_dir: Optional[str] = None, address: str = "localhost:8080", wait_seconds: int = 30, install_deps: bool = True) -> subprocess.Popen:
    """
    This is an alternative to `launch_docker_container` for setups that do not use Docker or
    would like to use `status-im/status-go` outside of a Docker container. This will build a
    native clone of `status-im/status-go` inside its Nix dev shell and launch it.

    NOTE: Requires the Nix package manager (https://nixos.org/download) and `git` to be installed.

    Parameters:
        - `commit` - the `status-go` commit SHA, branch or tag to build. If no commit is provided, the latest `develop` branch is built.
        - `repo_dir` - local folder to clone `status-go` into (and reuse on subsequent calls). Defaults to a `status-go` folder next to this package's installation. If the repo is not found then it will be fetched from GitHub
        - `address` - the `host:port` to launch `status-backend` on. Defaults to `localhost:8080`.
        - `wait_seconds` - number of seconds to wait, polling the health endpoint, before giving up on the backend starting. Building itself is not subject to this timeout.
        - `install_deps` - whether to run `make status-go-deps` before building. This also runs `go clean -cache` / `go clean -modcache`, so it is skipped by default - only needed on the first build, or after a Go toolchain upgrade.

    Output:
        - `subprocess.Popen` handle of the running `status-backend` process, so it can be terminated later.
    """
    logger = logging.getLogger(__name__)

    def run(cmd: list[str], cwd: Optional[str] = None) -> subprocess.CompletedProcess:
        logger.info(f"Running:\n{' '.join(cmd)}")
        return subprocess.run(cmd, cwd=cwd, stderr=subprocess.PIPE, text=True)

    system = sys.platform

    if system == "win32":
        raise exceptions.BuildError("build_and_launch requires Nix and is not supported on Windows. Use launch_docker_container instead, or run this from within WSL.")

    if not shutil.which("nix"):
        raise exceptions.BuildError("Please install Nix - https://nixos.org/download.")

    if not shutil.which("git"):
        raise exceptions.BuildError("Please install git.")

    repo_dir = repo_dir or os.path.join(os.path.dirname(os.path.dirname(__file__)), "status-go")
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

    binary_path = os.path.join(repo_dir, "build", "bin", "status-backend")
    if not os.path.isfile(binary_path):
        raise exceptions.BuildError(f"Build finished but {binary_path} was not found.")

    logger.info(f"Launching status-backend on {address}...")
    log_path = os.path.join(repo_dir, "status-backend.log")
    with open(log_path, "w") as log_file:
        process = subprocess.Popen([binary_path, f"-address={address}"], cwd=repo_dir, stdout=log_file, stderr=subprocess.STDOUT)

    health_url = f"http://{address}/health"
    deadline = time.time() + wait_seconds
    last_error = None
    while time.time() < deadline:
        if process.poll() is not None:
            raise exceptions.BuildError(f"status-backend exited early with code {process.returncode}. See {log_path} for details.")
        try:
            response = requests.get(health_url, timeout=1)
            if response.ok:
                logger.info("status-backend is up!")
                return process
        except requests.exceptions.RequestException as error:
            last_error = error
        time.sleep(0.5)

    process.terminate()
    raise exceptions.BuildError(f"status-backend did not become reachable at {health_url} within {wait_seconds}s ({last_error}).")
