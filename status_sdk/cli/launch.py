import click, os, time, requests
from .. import exceptions
from ..utils import launch_docker_container, download_build_and_launch

def __is_running(address: str) -> bool:
    """
    Check if Status Backend is running
    """
    try:
        return requests.get(f"http://{address}/health", timeout=1).ok
    except requests.exceptions.RequestException:
        return False

@click.group()
def launch():
    """
    Launch Status Backend in Docker or from a prebuilt release
    """

@launch.command()
@click.option("--commit", default=None, help="status-im/status-go commit SHA. Defaults to the newest commit.")
@click.option("--platform", default="linux/amd64", show_default=True, help="Platform the image is built for. See `docker buildx ls`.")
@click.option("--wait-seconds", default=5, show_default=True, type=int, help="Seconds to wait for the backend to boot after the container starts.")
@click.option("--data-folder", default=None, type=click.Path(file_okay=False), help="Local folder holding account data. Needed for Community Control Nodes.")
def docker(commit: str, platform: str, wait_seconds: int, data_folder: str):
    """
    Build and run Status Backend in a Docker container
    """
    try:
        launch_docker_container(commit, wait_seconds, platform, data_folder)
    except exceptions.DockerError as error:
        raise click.ClickException(str(error))

    click.echo("Status Backend is running in Docker. Stop it with `docker stop status-backend`.", err=True)

@launch.command()
@click.option("--tag", default=None, help="Release tag. Defaults to the latest release.")
@click.option("--token", default=None, help="GitHub token. Required for private repositories.")
@click.option("--launcher", default=None, type=click.Path(exists=True, dir_okay=False, resolve_path=True), help="A status-backend binary already on disk. Nothing is downloaded.")
@click.option("--host", default="localhost", show_default=True, help="Host to run Status Backend on.")
@click.option("--port", default=8080, show_default=True, help="Port to run Status Backend on.")
@click.option("--wait-seconds", default=30, show_default=True, type=int, help="Seconds to wait for the backend to answer after it starts.")
@click.option("--folder", default=click.get_app_dir("status-sdk"), show_default=True, type=click.Path(file_okay=False, resolve_path=True), help="Where the bundle is downloaded and the backend runs from.")
def download(tag: str, token: str, launcher: str, host: str, port: int, wait_seconds: int, folder: str):
    """
    Download a prebuilt Status Backend release and run it until Ctrl+C
    """
    address = f"{host}:{port}"
    if __is_running(address):
        click.echo(f"Status Backend is already running on {address}.", err=True)
        return

    # `download_build_and_launch` downloads the bundle into the current directory
    os.makedirs(folder, exist_ok=True)
    os.chdir(folder)
    params = {
        "launcher": launcher,
        "tag": tag,
        "token": token,
        "address": address,
        "wait_seconds": wait_seconds
    }
    try:
        launcher = download_build_and_launch(**params)
    except (exceptions.BuildError, requests.exceptions.HTTPError) as error:
        raise click.ClickException(str(error))

    click.echo(f"Status Backend is running on {address} from {launcher}. Press Ctrl+C to stop.", err=True)
    # The backend shares this terminal, so Ctrl+C stops both
    try:
        while __is_running(address):
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    click.echo("Status Backend stopped.", err=True)
