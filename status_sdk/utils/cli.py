from ..account import Account
from .. import constants, exceptions
from dotenv import load_dotenv, dotenv_values, set_key
from typing import Optional
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


def check_chains(account: Account, chain_ids: list[Optional[int]], param_hint: str = "--chain"):
    """
    Raise a usage error if any of `chain_ids` is not currently active in the wallet

    Parameters:
        - `account` - a logged in `Account` with wallet access
        - `chain_ids` - the chain IDs passed to the command. `None` (an option that was not given) is ignored
        - `param_hint` - the option named in the error message
    """
    try:
        current_chains = account.wallet.selected_chains
    except exceptions.WalletNotConfiguredError as error:
        raise click.ClickException(str(error))

    # An empty DataFrame has no `id` column when no chain is active
    active_chains: dict[int, str] = {} if current_chains.empty else current_chains.set_index("id")["name"].to_dict()
    # Repeated chain IDs (e.g. `--chain 1 --chain 1`) are only checked once
    inactive = sorted({chain_id for chain_id in chain_ids if chain_id and chain_id not in active_chains})
    if not inactive:
        return

    options = ", ".join(f"{chain_id} ({name})" for chain_id, name in active_chains.items()) or "none"
    word = "Chain" + ("s" if len(inactive) > 1 else "")
    raise click.BadParameter(
        f"{word} {', '.join(map(str, inactive))} not active. Active chains: {options}",
        param_hint=f"'{param_hint}'"
    )
