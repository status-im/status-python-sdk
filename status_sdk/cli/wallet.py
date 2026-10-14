from ..utils import cli as utils
from .. import exceptions
from typing import Optional
import click, re

def __validate_address(ctx: click.Context, param: click.Parameter, value: str) -> str:
    """
    Check that `value` is a wallet address before anything is sent
    """
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        raise click.BadParameter(f"'{value}' is not a wallet address (0x followed by 40 hex characters).")
    return value

@click.group(invoke_without_command=True)
@click.pass_context
def wallet(ctx: click.Context):
    """
    Execute Status Backend wallet functionality
    """
    if ctx.invoked_subcommand:
        return

    account = utils.load_account()
    click.echo(account.info["wallet_address"])

@wallet.command()
@click.option("--ccy", default="USD", help="ISO 4217 alpha code to represent the fiat currency")
def balance(ccy: str):
    """
    Get the account's current balance
    """
    account = utils.load_account()
    balance = account.wallet[ccy]

    if len(balance) == 0:
        chains = list(map(str, chains))
        word = "chain" + ("s" if len(chains) > 1 else "")
        click.echo(f"No balance for {word} " + ', '.join(chains) + "...")
        return

    market_info = account.wallet.get_current_market_info(
        balance["address"].to_list(),
        balance["chain_id"].unique().tolist()
    )
    balance = balance.merge(market_info.drop(["timestamp"], axis=1)\
                    .rename(columns={"token_address": "address"}), "left", ["chain_id", "address"])

    click.echo(balance.to_markdown(index=False))

@wallet.group(invoke_without_command=True)
@click.pass_context
def chains(ctx: click.Context):
    """
    Show the currently active chains, or activate and deactivate them
    """
    if ctx.invoked_subcommand:
        return

    account = utils.load_account()
    click.echo(account.wallet.selected_chains.to_markdown(index=False))

def __toggle_chains(chain_ids: tuple[int], activate: bool):
    """
    Activate or deactivate `chain_ids` one by one, stopping at the first error
    """
    account = utils.load_account()
    try:
        wallet = account.wallet
    except exceptions.WalletNotConfiguredError as error:
        raise click.ClickException(str(error))

    # Check every ID before changing anything, so a typo does not leave the chains half updated
    available_chains: dict[int, str] = wallet.available_chains.set_index("id")["name"].to_dict()
    unknown = [str(chain_id) for chain_id in dict.fromkeys(chain_ids) if chain_id not in available_chains]
    if unknown:
        options = ", ".join(f"{chain_id} ({name})" for chain_id, name in available_chains.items())
        raise click.BadParameter(f"{', '.join(unknown)} not available. Available chains: {options}", param_hint="'CHAIN_IDS'")

    action = "Activated" if activate else "Deactivated"
    done = []
    for chain_id in dict.fromkeys(chain_ids):
        try:
            wallet.activate_chain(chain_id) if activate else wallet.deactivate_chain(chain_id)
        except (exceptions.ActiveChainLimitError, exceptions.ChainDeactivationError) as error:
            changed = f" {action}: {', '.join(done)}." if done else " Nothing was changed."
            raise click.ClickException(f"{chain_id} ({available_chains[chain_id]}): {error}{changed}")

        done.append(f"{chain_id} ({available_chains[chain_id]})")
        click.echo(f"{action} {chain_id} ({available_chains[chain_id]})")

@chains.command()
@click.argument("chain_ids", nargs=-1, required=True, type=int, help="One or more chain IDs to activate. Up to 5 Mainnet and 5 Testnet chains can be active at once.")
def activate(chain_ids: tuple[int]):
    """
    Activate CHAIN_IDS so the wallet can use them
    """
    __toggle_chains(chain_ids, activate=True)

@chains.command()
@click.argument("chain_ids", nargs=-1, required=True, type=int, help="One or more active chain IDs to deactivate.")
def deactivate(chain_ids: tuple[int]):
    """
    Deactivate CHAIN_IDS so the wallet stops using them
    """
    __toggle_chains(chain_ids, activate=False)


@wallet.command("search")
@click.argument("wallet_address", callback=__validate_address, help="Wallet address to look up. Does not need to belong to your account.")
@click.argument("tokens", nargs=-1, required=True, help="One or more token symbols such as ETH or USDC, or the tokens' contract addresses.")
@click.option("--chain", "chain_id", default=1, show_default=True, type=int, help="Active chain ID where the tokens exist.")
@click.option("--ccy", default="USD", show_default=True, help="ISO 4217 alpha code to represent the fiat currency")
def search(wallet_address: str, tokens: tuple[str], chain_id: int, ccy: str):
    """
    Get the balance of TOKENS for any WALLET_ADDRESS.
    """
    account = utils.load_account()
    utils.check_chains(account, [chain_id], "--chain")
    df = account.wallet.available_tokens
    tokens = (token if token.startswith("0x") else token.upper() for token in tokens)
    query = (df["chain_id"] == chain_id) & ((df["symbol"].isin(tokens) | df["address"].isin(tokens)))
    tokens = df.loc[query, "address"].drop_duplicates().to_list()

    try:
        balance = account.wallet.search(tokens, chain_id, wallet_address, ccy)
    except exceptions.WalletNotConfiguredError as error:
        raise click.ClickException(str(error))

    if len(balance) == 0:
        click.echo(f"No balance found for {wallet_address} on chain {chain_id}...")
        return

    balance["total"] = balance["amount"] * balance["price"]
    outputs = {
        "Search Results": "\n" + balance.to_markdown(index=False),
        "Total": f"{round(balance['total'].sum(), 2)} {ccy}",
        "Chain Total": "\n" + balance.groupby("chain_id")["total"].sum().to_markdown()
    }
    for title, value in outputs.items():
        click.echo(f"{title}:\n{value}\n\n" + "=" * 100 + "\n\n")

@wallet.command()
@click.option("--address", "addresses", multiple=True, callback=lambda ctx, param, values: tuple(__validate_address(ctx, param, value) for value in values), help="Wallet address to get the history for. Repeat it for several wallets. Defaults to your own wallet.")
@click.option("--chain", "chains", multiple=True, type=int, help="Active Mainnet chain ID to get the history for. Repeat it for several chains. Defaults to every active Mainnet chain.")
def transactions(addresses: tuple[str], chains: tuple[int]):
    """
    Get the transaction history of your wallet, or of any other wallet addresses
    """
    account = utils.load_account()
    utils.check_chains(account, list(chains), "--chain")
    transactions = account.wallet.get_transactions(list(addresses), list(chains))
    if len(transactions) > 0:
        click.echo(transactions.to_markdown(index=True))
    else:
        addresses = list(addresses) or [account.info["wallet_address"]]
        click.echo(f"No transactions found for {', '.join(addresses)}")

@wallet.command()
@click.argument("address", callback=__validate_address, help="Wallet address of the receiver.")
@click.argument("amount", type=click.FloatRange(min=0, min_open=True), help="Amount of SYMBOL to send.")
@click.argument("symbol", help="Token symbol such as ETH or USDC, or the token's contract address.")
@click.option("--chain", "chain_id", default=1, show_default=True, type=int, help="Active chain ID to send on.")
def send(address: str, amount: float, symbol: str, chain_id: int):
    """
    Send AMOUNT of SYMBOL to the wallet ADDRESS.
    """
    account = utils.load_account()
    utils.check_chains(account, [chain_id], "--chain")
    try:
        transaction_hash = account.wallet.send_transaction(address, symbol, amount, chain_id)
    except (exceptions.InvalidTokenError, exceptions.WalletNotConfiguredError) as error:
        raise click.ClickException(str(error))

    if not transaction_hash:
        raise click.ClickException("Status Backend did not return a transaction hash. The transaction was not sent...")

    click.echo(transaction_hash)

@wallet.command()
@click.argument("from_token", help="Token to swap from. A symbol such as ETH or USDC, or the token's contract address.")
@click.argument("to_token", help="Token to swap to. A symbol such as ETH or USDC, or the token's contract address.")
@click.argument("amount", type=click.FloatRange(min=0, min_open=True), help="Amount of FROM_TOKEN to swap.")
@click.option("--from-chain", "from_chain_id", default=1, show_default=True, type=int, help="Active chain ID where FROM_TOKEN is.")
@click.option("--to-chain", "to_chain_id", default=None, type=int, help="Active chain ID where TO_TOKEN arrives. Defaults to --from-chain, so the swap stays on one chain.")
def swap(from_token: str, to_token: str, amount: float, from_chain_id: int, to_chain_id: Optional[int]):
    """
    Swap AMOUNT of FROM_TOKEN to TO_TOKEN, on one chain or across two.
    """
    # The same token can only be swapped when it moves to another chain
    if from_token.upper() == to_token.upper() and to_chain_id in [None, from_chain_id]:
        raise click.BadParameter("FROM_TOKEN and TO_TOKEN must be different on the same chain.", param_hint="'TO_TOKEN'")

    account = utils.load_account()
    utils.check_chains(account, [from_chain_id], "--from-chain")
    utils.check_chains(account, [to_chain_id], "--to-chain")
    try:
        transaction_hash = account.wallet.swap_tokens(from_token, to_token, amount, from_chain_id, to_chain_id)
    except (exceptions.InvalidTokenError, exceptions.WalletNotConfiguredError, exceptions.BackendError) as error:
        raise click.ClickException(str(error))

    if not transaction_hash:
        raise click.ClickException("Status Backend did not return a transaction hash. The swap was not sent...")

    click.echo(transaction_hash)

@wallet.group(invoke_without_command=True)
@click.pass_context
def address(ctx: click.Context):
    """
    Get currently saved wallet addresses
    """
    if ctx.invoked_subcommand:
        return
    account = utils.load_account()
    saved_addresses = list(account.wallet.saved_addresses.values())
    if not saved_addresses:
        click.echo("No saved addresses found.")
        return

    for current in saved_addresses:
        message = "\n" + str(current) + "\n\n" + "=" * 100
        click.echo(message)


@address.command()
@click.argument("address", callback=__validate_address, help="Wallet address to save.")
@click.argument("name", help="Name to save the address under. Letters, numbers, _ and - with single spaces between words, up to 24 characters.")
@click.option("--ens", default=None, help="ENS name of the address.")
def save(address: str, name: str, ens: Optional[str]):
    """
    Save a wallet address
    """
    account = utils.load_account()
    try:
        account.wallet.add_address(address, name, ens)
        click.echo(f"Added {address}")
    except:
        click.echo(f"Address {address} already exists...")


@address.command()
@click.argument("address", callback=__validate_address, help="Saved wallet address to edit.")
@click.option("--name", default=None, help="New name for the address. Letters, numbers, _ and - with single spaces between words, up to 24 characters.")
@click.option("--ens", default=None, help="New ENS name of the address. Pass an empty value to remove it.")
def edit(address: str, name: Optional[str], ens: Optional[str]):
    """
    Change the name or ENS name of a saved wallet address
    """
    if not name and not ens:
        raise click.UsageError("Pass --name, --ens or both.")

    account = utils.load_account()
    current = account.wallet.saved_addresses.get(address.lower())
    if not current:
        raise click.ClickException(f"Address {address} is not saved...")

    try:
        if name:
            current.name = name

        if ens:
            current.ens = ens
    except (exceptions.InvalidSavedAddressNameError, exceptions.SavedAddressError) as error:
        raise click.ClickException(str(error))

    click.echo(f"Edited {address}")


@address.command()
@click.argument("address", nargs=-1, required=True, type=str, help="One or more saved addresses.")
def delete(address: tuple[str]):
    """
    Delete saved wallet addresses
    """
    account = utils.load_account()
    saved_addresses = account.wallet.saved_addresses

    for address in set(address):
        current = saved_addresses.get(address.lower())
        if not current:
            continue

        current.delete()
        click.echo(f"Deleted {address}")
