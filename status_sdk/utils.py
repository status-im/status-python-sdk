import shutil, os, subprocess, sys, time
from pathlib import Path
from typing import Optional
from .logger import Logger
from . import exceptions

def launch_docker_container(commit: Optional[str] = None, wait_seconds: int = 5, platform: str = "linux/amd64"):
    """
    Launch the Status Backend Docker container using `docker-compose.yaml`

    NOTE: On Windows, Docker Desktop caches the Docker volume bind mounts in the WSL
    virtual machine. When the mounts go stale the container cannot start. WSL is
    restarted to clear the cache and the container is launched again until it is up.

    Parameters:
        - `commit` - the commit SHA. If no commit is provided, the latest version is pulled
        - `wait_seconds` - number of seconds to wait before the code resumes. Sleep prevents calling `class Account` faster than launching the docker container. This only happens when the container already exists and it is must be turned on. On Windows the same value is used to wait between retries after WSL has been restarted.
        - `platform` - the platform the image is built for. Defaults to `linux/amd64`. Run `docker buildx ls` to see the platforms your Docker installation supports.
    """
    logger = Logger()
    system = sys.platform
    is_windows = system == "win32"
    if not shutil.which("docker"):
        raise exceptions.DockerError("Please install Docker.")

    logger.info(f"Running Docker on {system}")
    ref = commit if commit else "develop"
    DOCKER_COMPOSE_PATH = os.path.join(os.path.dirname(__file__), "docker-compose.yaml")
    docker_path = DOCKER_COMPOSE_PATH
    if is_windows:
        p = Path(DOCKER_COMPOSE_PATH)
        drive = p.drive.rstrip(":").lower()
        docker_path = f"/mnt/{drive}/" + "/".join(p.parts[1:])

    cmd = ["env", f"STATUS_GO_REF={ref}", f"STATUS_GO_PLATFORM={platform}", "docker", "compose", "-f", docker_path, "up", "-d", "--build"]

    if is_windows:
        if not shutil.which("wsl"):
            raise exceptions.DockerError("Please install wsl - https://learn.microsoft.com/en-us/windows/wsl/install.")
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
