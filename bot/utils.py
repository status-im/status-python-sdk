import shutil, os, subprocess, sys, time
from pathlib import Path
from typing import Optional
from .logger import Logger
from . import exceptions

def launch_docker_container(commit: Optional[str] = None, wait_seconds: int = 5):
    """
    Launch the Status Backend Docker container using `docker-compose.yaml`

    Parameters:
        - `commit` - the commit SHA. If no commit is provided, the latest version is pulled
        - `wait_seconds` - nunmber of seconds to wait before the code resumes. Sleep prevents calling `class Account` faster than launching the docker container. This only happens when the container already exists and it is must be turned on.
    """
    logger = Logger()
    platform = sys.platform
    is_windows = platform == "win32"
    if not shutil.which("docker"):
        raise exceptions.DockerError("Please install Docker.")

    logger.info(f"Running Docker on {platform}")
    ref = commit if commit else "develop"
    DOCKER_COMPOSE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docker-compose.yaml")
    docker_path = DOCKER_COMPOSE_PATH
    if is_windows:
        p = Path(DOCKER_COMPOSE_PATH)
        drive = p.drive.rstrip(":").lower()
        docker_path = f"/mnt/{drive}/" + "/".join(p.parts[1:])

    cmd = ["env", f"STATUS_GO_REF={ref}", "docker", "compose", "-f", docker_path, "up", "-d", "--build"]

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
