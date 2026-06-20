import shutil, os, subprocess, sys, time
from pathlib import Path
from .logger import Logger
from . import exceptions

def launch_docker_container(wait_seconds: int = 5):
    """
    Launch the Status Backend Docker container using `docker-compose.yaml`

    Parameters:
        - `wait_seconds` - nunmber of seconds to wait before the code resumes. Sleep prevents calling `class Account` faster than launching the docker container. This only happens when the container already exists and it is must be turned on.
    """
    logger = Logger()
    platform = sys.platform
    is_windows = platform == "win32"
    if not shutil.which("docker"):
        raise exceptions.DockerError("Please install Docker.")

    logger.info(f"Running Docker on {platform}")
    DOCKER_COMPOSE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docker-compose.yaml")
    docker_path = DOCKER_COMPOSE_PATH
    if is_windows:
        p = Path(DOCKER_COMPOSE_PATH)
        drive = p.drive.rstrip(":").lower()
        docker_path = f"/mnt/{drive}/" + "/".join(p.parts[1:])

    cmd = ["docker", "compose", "-f", docker_path, "up", "-d"]
    if is_windows:
        if not shutil.which("wsl"):
            raise exceptions.DockerError("Please install wsl - https://learn.microsoft.com/en-us/windows/wsl/install.")
        cmd.insert(0, "wsl")

    logger.info(f"Running:\n{' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=os.path.dirname(DOCKER_COMPOSE_PATH),
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise exceptions.DockerError(result.stderr.strip())

    logger.info(f"Sleeping for {wait_seconds}s")
    time.sleep(wait_seconds)
