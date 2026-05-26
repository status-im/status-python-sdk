import shutil, os, subprocess, sys
from pathlib import Path

def launch_docker_container():
    """
    Launch the Status Backend Docker container using `docker-compose.yaml`
    """
    is_windows = sys.platform == "win32"
    if not shutil.which("docker"):
        raise Exception("Please install Docker.")

    DOCKER_COMPOSE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docker-compose.yaml")
    docker_path = DOCKER_COMPOSE_PATH
    if is_windows:
        p = Path(DOCKER_COMPOSE_PATH)
        drive = p.drive.rstrip(":").lower()
        docker_path = f"/mnt/{drive}/" + "/".join(p.parts[1:])

    cmd = ["docker", "compose", "-f", docker_path, "up", "-d"]
    if is_windows:
        if not shutil.which("wsl"):
            raise Exception("Please install wsl - https://learn.microsoft.com/en-us/windows/wsl/install.")
        cmd.insert(0, "wsl")

    result = subprocess.run(
        cmd,
        cwd=os.path.dirname(DOCKER_COMPOSE_PATH),
        stderr=subprocess.PIPE,
        text=True,
    )
    if "running" in result.stderr.lower():
        return

    if result.returncode != 0:
        raise Exception(result.stderr.strip())
