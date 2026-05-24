# Utils

![Utils header image](./images/overview-utils.png)

Helper functions for setting up the Status Backend environment.

## Methods

### `launch_docker_container()`

Launch Status Backend Docker container in the background using `docker-compose.yaml`. If `docker` is not installed, or if the container fails to start, an **exception will be raised** with the error message from Docker.

```python
from bot import launch_docker_container

launch_docker_container()
```
