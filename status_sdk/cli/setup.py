from .. import constants
from dotenv import load_dotenv, set_key, unset_key
from typing import Optional, Union
import click, secrets, string, os, sys

def __generate_password(length: int = 24) -> str:
    """
    Generate a cryptographically secure password.

    Parameters:
        - `length` - number of characters. Must be at least 4 to fit one of each character group

    Output:
        - a password with at least one lowercase, uppercase, digit and symbol
    """
    # Symbols that do not need escaping in a shell, so the password can be exported as an env variable
    symbols = "!#%*+-.:=?@^_~"
    groups = [string.ascii_lowercase, string.ascii_uppercase, string.digits, symbols]
    if length < len(groups):
        raise ValueError(f"Password length must be at least {len(groups)}...")

    alphabet = "".join(groups)
    # One character from each group, the rest from the whole alphabet
    characters = [secrets.choice(group) for group in groups]
    characters += [secrets.choice(alphabet) for _ in range(length - len(groups))]
    # Shuffle so the guaranteed characters are not always at the start
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)

@click.command()
@click.option("--name", envvar="LOGIN_NAME", show_envvar=True, help="Display name or ENS. For initial logins.")
@click.option("--password", envvar="LOGIN_PASSWORD", show_envvar=True, help="Account password. Use the env variable to stay out of shell history.")
@click.option("--generate-password", is_flag=True, help="Generate a new password, replacing the saved one.")
@click.option("--mnemonic", envvar="LOGIN_MNEMONIC", show_envvar=True, help="Mnemonic to recover an account.")
@click.option("--infura-token", envvar="LOGIN_INFURA_TOKEN", show_envvar=True, help="Infura token for wallet access.")
@click.option("--alchemy-token", envvar="LOGIN_ALCHEMY_TOKEN", show_envvar=True, help="Alchemy token for wallet access.")
@click.option("--coingecko-api-key", envvar="LOGIN_COINGECKO_API_KEY", show_envvar=True, help="CoinGecko API key for wallet access.")
@click.option("--domain", envvar="ACCOUNT_DOMAIN", show_envvar=True, help="Domain where Status Backend is reachable. Use the container name inside the same Docker network.")
@click.option("--backend-port", envvar="ACCOUNT_BACKEND_PORT", show_envvar=True, help="Port exposed by Status Backend.")
@click.option("--media-port", envvar="ACCOUNT_MEDIA_PORT", show_envvar=True, help="Media port exposed by the Status media server to work with images.")
@click.option("--is-secure", envvar="ACCOUNT_IS_SECURE", show_envvar=True, type=bool, help="Use https instead of http.")
@click.option("--backup-folder", envvar="ACCOUNT_BACKUP_FOLDER", show_envvar=True, type=click.Path(file_okay=False), help="Folder where backups are created and loaded from.")
@click.option("--volume-folder", envvar="ACCOUNT_VOLUME_FOLDER", show_envvar=True, type=click.Path(file_okay=False), help="Folder holding the docker-compose.yaml used to launch Status Backend.")
@click.option("--no-input", is_flag=True, help="If passed, then the user is not prompted to enter the fields. Omit this flag if you want to set up your account with OPTIONS only. Values not given keep their saved value or default.")
def setup(generate_password: bool, no_input: bool, **options: Optional[Union[str, int, bool]]):
    """
    Save the login details used by other commands.

    Values given as options replace the saved ones. Pass an empty value to remove one.
    """
    if generate_password and options["password"] is not None:
        raise click.UsageError("--password (or LOGIN_PASSWORD) and --generate-password cannot be used together.")

    if generate_password:
        # A blank password is generated below
        options["password"] = ""

    wallet_text = "Leave blank if you do not need wallet access"
    prompts = {
        "name": {
            "text": "Your Display Name or ENS. For initial logins",
            "default": "status-bot-67"
        },
        "password": {
            "text": "Password. Leave blank to generate one",
            "default": "",
            "hide_input": True,
            "show_default": False
        },
        "mnemonic": {
            "text": "Mnemonic. Leave blank unless recovering an account",
            "default": "",
            "show_default": False
        },
        "infura_token": {
            "text": f"Infura token. {wallet_text}",
            "default": "",
            "show_default": False
        },
        "alchemy_token": {
            "text": f"Alchemy token. {wallet_text}",
            "default": "",
            "show_default": False
        },
        "coingecko_api_key": {
            "text": f"CoinGecko API key. {wallet_text}",
            "default": "",
            "show_default": False
        },
        # Parameters of `Account`
        "domain": {
            "text": "Domain where Status Backend is reachable",
            "default": "localhost"
        },
        "backend_port": {
            "text": "Status Backend port",
            "default": 8080,
            "type": click.IntRange(1, 65535)
        },
        "media_port": {
            "text": "Status media server port",
            "default": 9000,
            "type": click.IntRange(1, 65535)
        },
        "is_secure": {
            "text": "Use https",
            "default": False,
            "type": bool
        },
        "backup_folder": {
            "text": "Backup folder. Leave blank to use the SDK's own",
            "default": "",
            "show_default": False
        },
        "volume_folder": {
            "text": "Folder holding the docker-compose.yaml used to launch Status Backend. Leave blank to use the SDK's own",
            "default": "",
            "show_default": False
        }
    }
    # Secrets are not shown back when asking to overwrite them
    secret_keys = ["password", "mnemonic", "infura_token", "alchemy_token", "coingecko_api_key"]
    folder_keys = ["backup_folder", "volume_folder"]
    # Each value is saved under its option's env variable
    env_keys = {param.name: param.envvar for param in click.get_current_context().command.params}
    env_path = os.path.join(constants.CLI_APP_FOLDER, ".env")
    os.makedirs(constants.CLI_APP_FOLDER, exist_ok=True)
    # Only the current user can read or write the file, as it holds the password
    os.close(os.open(env_path, os.O_WRONLY | os.O_CREAT, 0o600))
    load_dotenv(env_path, override=True)

    # Only prompt when a person is at the terminal - agents and scripts pipe stdin instead
    interactive = not no_input and sys.stdin.isatty()
    values = {}
    for key, prompt in prompts.items():
        env_key = env_keys[key]
        value = options[key]
        # Not given as an option, but already saved
        if value is None and env_key in os.environ:
            current = "" if key in secret_keys else f" ({os.environ[env_key]})"
            if not interactive or not click.confirm(f"{env_key}{current} is already set. Overwrite it?", default=False):
                values[env_key] = os.environ[env_key]
                continue

        if value is None and interactive:
            value = click.prompt(**prompt)
            # A mistyped password locks the account, so ask for it twice
            if key == "password" and len(value) > 0 and click.prompt("Repeat password", hide_input=True) != value:
                raise click.ClickException("Passwords do not match...")
        # Same as pressing Enter on the prompt
        elif value is None:
            value = prompt["default"]

        # .env only holds strings - booleans are saved as `true` / `false`
        value = str(value).lower() if isinstance(value, bool) else str(value).strip()
        if key == "password" and len(value) == 0:
            value = __generate_password()
            click.echo("Generated a password", err=True)

        if key in folder_keys and len(value) > 0:
            # Status Backend needs absolute paths
            value = os.path.abspath(os.path.expanduser(value))
            if not os.path.isdir(value):
                raise click.ClickException(f"{value} is not an existing folder...")

        values[env_key] = value

    # `Account.login` only enables the wallet when all three are given
    wallet_keys = ["LOGIN_INFURA_TOKEN", "LOGIN_ALCHEMY_TOKEN", "LOGIN_COINGECKO_API_KEY"]
    given_wallet_keys = [key for key in wallet_keys if values.get(key)]
    if 0 < len(given_wallet_keys) < len(wallet_keys):
        raise click.ClickException("Wallet access needs all of Infura token, Alchemy token and CoinGecko API key...")

    # Written only after every check passes, so a failed setup leaves the file untouched
    for env_key, value in values.items():
        if len(value) > 0:
            set_key(env_path, env_key, value)
        # Overwriting with a blank value removes it
        elif env_key in os.environ:
            unset_key(env_path, env_key)

    os.chmod(env_path, 0o600)
    click.echo(f"Saved to {env_path}", err=True)
