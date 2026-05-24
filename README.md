# Status Python SDK

![Status Python SDK header image](./docs/images/overview-header.png)

The initial Python Status Backend was built with testing in mind, instead of easy developer access. The objective of this repository is to make a SDK that is:

- **light** - as less external packages when it comes to working with Status App
- **fast** - quick to get started with Status Python
- **documented** - clear explanations of what was done and **why it was done in a specific way**.

Currently this repository is not on [PyPi](https://pypi.org/) but will be added when core functionality has been devleoped and tested.

## How it works

```mermaid
graph TB
    subgraph backend[status-im/status-go]
        subgraph Endpoints[Network: status-bridge]
           RPC[RPC]
           HTTP[REST]
           SOCKET[Web Socket]
       end
       Vol1[(Backup)]
       Vol2[(Assets)]
   end


   subgraph bot[Python SDK]
        REQUIREMENTS[requirements.txt]
        SDK[class Account]
        SIGNAL[class Signal]
    end

    subgraph external[External Services]
        COINGECKO[CoinGecko]
        EVM
    end

    SDK --> SIGNAL
    SDK --> |Port 8080| RPC
    SDK --> |Port 8080| HTTP
    SIGNAL --> |Port 8080| SOCKET
    SDK --> Vol1
    SDK --> Vol2
    RPC --> |coingecko_api_key| COINGECKO
    RPC --> |infura_token| EVM
```

## Setup

To access Python funcitonality you will have to set up [Status Backend](https://github.com/status-im/status-go/). Easiest and fastest way to get it running would be with [Docker](https://www.docker.com/products/docker-desktop/).

```mermaid
sequenceDiagram
    actor User
    participant Docker
    participant Python@{"alias": "status-im/status-bot"}
    participant Github@{"alias": "status-im/status-go" }
    
    User ->> Docker: docker-compose up
    Docker ->> Github: Fetch Image
    Docker ->> Docker: Build
    User ->> Docker: Run container
    User ->> Python: initialize module
    Note over User,Python: from bot import Account<br>account = Account()
```

### Python

1. Setup environment. [Conda](https://www.anaconda.com/) example:
```bash
conda create -n status-sdk python=3.12
```

**Note**: Code has been tested with **Python 3.12**.

2. Install requirements

```bash
pip install -r ./requirements.txt
```

### Docker

Setup [`status-im/status-go`](https://github.com/status-im/status-go/) with the provided `docker-compose.yaml` file.

```
docker compose up -d
```

If you would like to initialize and start the container with Python:

```python
from bot import launch_docker_container
launch_docker_container()
```

**Note**: To run on Windows, please make sure you clone `status-im/status-go` and change the context to the folder. If you do not want to clone the repository, make sure you have set up [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) and started it.
