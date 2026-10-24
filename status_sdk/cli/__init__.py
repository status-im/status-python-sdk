import click, logging
from . import launch, setup, wallet

@click.group()
def cli():
    """
    Work with Status App from the terminal
    """
    # SDK logs go to stderr so stdout stays clean for command output
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
    logger = logging.getLogger("status_sdk")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

cli.add_command(launch.launch)
# cli.add_command(login.login)
cli.add_command(setup.setup)
cli.add_command(wallet.wallet)
