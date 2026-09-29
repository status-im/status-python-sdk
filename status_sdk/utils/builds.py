import shutil, os, subprocess, time, logging, requests
from .. import exceptions

def fix_nix_build_paths(binary_path: str) -> None:
    """
    Nix's `nim-sds` package sometimes bakes the transient build-sandbox path of `libsds.dylib`
    (e.g. `/nix/var/nix/builds/nix-<id>/source/build/libsds.dylib`) into `status-backend` instead
    of the stable `/nix/store/...` path. That sandbox is removed after the build finishes, so the
    binary fails to launch with a `Library not loaded` dyld error. This finds any such dangling
    dependency and repoints it at the matching library actually present in `/nix/store`.
    """
    logger = logging.getLogger(__name__)
    if not shutil.which("install_name_tool") or not shutil.which("otool"):
        return

    result = subprocess.run(["otool", "-L", binary_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        logger.warning(f"Failed to inspect {binary_path} with otool: {result.stderr.strip()}")
        return

    changed = False
    for line in result.stdout.splitlines()[1:]:
        dep_path = line.strip().split(" ", 1)[0]
        if os.path.isfile(dep_path) or "/nix/var/nix/builds/" not in dep_path:
            continue

        lib_name = os.path.basename(dep_path)
        logger.warning(f"{binary_path} references a stale Nix build path for {lib_name}. Searching /nix/store for a replacement...")
        find_result = subprocess.run(["find", "/nix/store", "-iname", lib_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        candidates = [candidate for candidate in find_result.stdout.splitlines() if candidate]
        if not candidates:
            logger.warning(f"No replacement for {lib_name} found in /nix/store. {binary_path} may fail to launch.")
            continue

        replacement = candidates[0]
        subprocess.run(["install_name_tool", "-change", dep_path, replacement, binary_path], stderr=subprocess.PIPE, text=True)
        logger.info(f"Repointed {lib_name} to {replacement}")
        changed = True

    if changed:
        # install_name_tool invalidates the code signature - macOS refuses to run an unsigned/altered binary
        subprocess.run(["codesign", "--sign", "-", "--force", binary_path], stderr=subprocess.PIPE, text=True)

def launch_build(binary_path: str, working_dir: str, address: str = "localhost:8080", wait_seconds: int = 30):
    """
    Launch a `status-backend` binary and wait until it answers on its health endpoint.
    Shared by `build_and_launch` and `download_build_and_launch`.

    Parameters:
        - `binary_path` - the `status-backend` binary to launch
        - `working_dir` - the working directory of the process. The backend resolves its relative `assets` / `backups` folders against it
        - `address` - the `host:port` to launch `status-backend` on. Defaults to `localhost:8080`.
        - `wait_seconds` - number of seconds to wait, polling the health endpoint, before giving up on the backend starting
    """
    logger = logging.getLogger(__name__)
    if not os.path.isfile(binary_path):
        raise exceptions.BuildError(f"{binary_path} was not found.")

    health_url = f"http://{address}/health"
    try:
        response = requests.get(health_url, timeout=1)
        if response.ok:
            logger.info(f"status-backend is already running on {address}. Skipping launch.")
            return None
    except requests.exceptions.RequestException:
        pass

    logger.info(f"Launching status-backend on {address}...")
    # stdout / stderr are inherited, so the backend's logs are printed in the terminal
    process = subprocess.Popen([binary_path, f"-address={address}"], cwd=working_dir)

    deadline = time.time() + wait_seconds
    last_error = None
    while time.time() < deadline:
        if process.poll() is not None:
            raise exceptions.BuildError(f"status-backend exited early with code {process.returncode}. See the status-backend output above for details.")
        try:
            response = requests.get(health_url, timeout=1)
            if response.ok:
                logger.info("status-backend is up!")
                return
        except requests.exceptions.RequestException as error:
            last_error = error
        time.sleep(0.5)

    process.terminate()
    raise exceptions.BuildError(f"status-backend did not become reachable at {health_url} within {wait_seconds}s ({last_error}).")
