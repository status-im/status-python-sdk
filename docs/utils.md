# Utils

![Utils header image](./images/overview-utils.png)

Helper functions for setting up the Status Backend environment.

## Methods

### `launch_docker_container(commit=None, wait_seconds=5)`

Launch Status Backend Docker container in the background using `docker-compose.yaml`. If `docker` is not installed, or if the container fails to start, an **exception will be raised** with the error message from Docker. The container is built from [`status-im/status-go`](https://github.com/status-im/status-go) at the git ref you choose:

```yaml
context: https://github.com/status-im/status-go.git#${STATUS_GO_REF:-develop}
```

The image is always rebuilt (`docker compose up --build`) so a newly chosen `commit` is picked up instead of reusing a previously built image.

| Name | Type | Required | Description |
|-----|-----|-----|-------------|
| `commit` | `str` | No | The `status-im/status-go` git ref to build from - a commit SHA, branch, or tag. When omitted, the latest `develop` branch is built. |
| `wait_seconds` | `int` | No | Number of seconds to pause after the `docker compose up` command returns, giving Status Backend enough time to finish booting before subsequent code runs. Defaults to `5`. This matters mainly when the container already exists and is being restarted, because `docker compose up` returns immediately while the backend is still warming up - instantiating [`Account`](./account.md#accountdomainlocalhost-port8080-is_securefalse-backup_foldernone) too quickly will fail to connect. |

```python
from bot import launch_docker_container

# Build from the latest develop branch
launch_docker_container(wait_seconds=10)

# Pin a specific status-go commit
# https://github.com/status-im/status-go/commit/2bee8b6a38cdc8f92d74e2dbb8c4e77fbbeea149
launch_docker_container(commit="2bee8b6a38cdc8f92d74e2dbb8c4e77fbbeea149")
```

**Windows Note**: In Docker go to `Settings > Resources > WSL integration` and make sure `Enable integration with my default WSL distro` and `Ubuntu` are **turned on**.

![Image of Note](./images/wsl-docker.png)
