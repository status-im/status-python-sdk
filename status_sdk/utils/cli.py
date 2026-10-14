from ..account import Account
from .. import constants
from dotenv import load_dotenv, dotenv_values, set_key
import click, os

def load_account() -> Account:
    """
    Load the `setup` Status account for CLI usage
    """
    def get_params(raw_values: dict[str, str], prefix: str) -> dict:
        output = {}
        for key, value in raw_values.items():
            if not key.startswith(prefix):
                continue
            if key.lower().endswith("port"):
                value = int(value)
            elif value in ["true", "false"]:
                value = value == "true"
            output[key.replace(prefix, "").lower()] = value
        return output

    env_path = os.path.join(constants.CLI_APP_FOLDER, ".env")
    if not os.path.exists(env_path):
        raise click.ClickException("Before calling this command, please run setup...")

    load_dotenv(env_path, override=True)
    values = dotenv_values(env_path)
    login_params = get_params(values, "LOGIN_")
    account_params = get_params(values, "ACCOUNT_")
    account = Account(**account_params, show_logs=False)
    account.login(**login_params)

    key_uid = account.info["key_uid"]
    if login_params.get("key_uid") != key_uid:
        set_key(env_path, "LOGIN_KEY_UID", key_uid)

    return account
