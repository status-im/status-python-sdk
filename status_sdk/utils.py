import shutil, os, subprocess, sys, time, yaml
from pathlib import Path
from typing import Optional
from .logger import Logger
from . import exceptions

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
    logger = Logger()
    system = sys.platform
    is_windows = system == "win32"
    if not shutil.which("docker"):
        raise exceptions.DockerError("Please install Docker.")

    if is_windows and not shutil.which("wsl"):
        raise exceptions.DockerError("Please install wsl - https://learn.microsoft.com/en-us/windows/wsl/install.")

    logger.info(f"Running Docker on {system}")
    ref = commit if commit else "develop"
    DOCKER_COMPOSE_PATH = os.path.join(os.path.dirname(__file__), "docker-compose.yaml")
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
