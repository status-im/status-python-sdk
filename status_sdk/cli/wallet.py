from ..utils import cli as utils
from .. import constants, exceptions
import click, re

def __validate_address(ctx: click.Context, param: click.Parameter, value: str) -> str:
    """
    Check that `value` is a wallet address before anything is sent
    """
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        raise click.BadParameter(f"'{value}' is not a wallet address (0x followed by 40 hex characters).")
    return value

@click.group()
def wallet():
    """
    Execute Status Backend wallet functionality
    """

@wallet.command()
@click.option("--ccy", default="USD", help="ISO 4217 alpha code to represent the fiat currency")
@click.option("--chain", "chains", multiple=True, type=click.Choice(list(constants.ALCHEMY_CHAIN_IDS.values())), help="Chain ID to get the wallet's balance")
def balance(ccy: str, chains: tuple[int]):
    account = utils.load_account()
    balance = account[ccy]

    if chains:
        query = balance["chain_id"].isin(list(chains))
        balance = balance.loc[query].reset_index(drop=True)

    if len(balance) == 0:
        chains = list(map(str, chains))
        word = "chain" + ("s" if len(chains) > 1 else "")
        click.echo(f"No balance for {word} " + ', '.join(chains) + "...")
        return

    market_info = account.get_market(balance["address"].to_list(), balance["chain_id"].unique().tolist())
    balance = balance.merge(market_info.drop(["timestamp"], axis=1)\
                    .rename(columns={"token_address": "address"}), "left", ["chain_id", "address"])

    click.echo(balance.to_markdown(index=False))

@wallet.command()
def transactions():
    account = utils.load_account()
    transactions = account.get_transactions()
    if len(transactions) > 0:
        click.echo(transactions.to_markdown(index=True))
    else:
        address = account.info["wallet_address"]
        click.echo(f"No transactions found for {address}")

@wallet.command()
@click.argument("address", callback=__validate_address, help="Wallet address of the receiver.")
@click.argument("amount", type=click.FloatRange(min=0, min_open=True), help="Amount of SYMBOL to send.")
@click.argument("symbol", help="Token symbol such as ETH or USDC, or the token's contract address.")
@click.option("--chain", "chain_id", default=1, show_default=True, type=click.Choice(list(constants.ALCHEMY_CHAIN_IDS.values())), help="Chain ID to send on.")
def send(address: str, amount: float, symbol: str, chain_id: int):
    """
    Send AMOUNT of SYMBOL to the wallet ADDRESS.
    """
    account = utils.load_account()
    try:
        transaction_hash = account.send_transaction(address, symbol, amount, chain_id)
    except (exceptions.InvalidTokenError, exceptions.WalletNotConfiguredError) as error:
        raise click.ClickException(str(error))

    if not transaction_hash:
        raise click.ClickException("Status Backend did not return a transaction hash. The transaction was not sent...")

    click.echo(transaction_hash)


@wallet.command()
@click.argument("from_token", help="Token to swap from. A symbol such as ETH or USDC, or the token's contract address.")
@click.argument("to_token", help="Token to swap to. A symbol such as ETH or USDC, or the token's contract address.")
@click.argument("amount", type=click.FloatRange(min=0, min_open=True), help="Amount of FROM_TOKEN to swap.")
@click.option("--chain", "chain_id", default=1, show_default=True, type=click.Choice(list(constants.ALCHEMY_CHAIN_IDS.values())), help="Chain ID to swap on. Both tokens must be on it.")
def swap(from_token: str, to_token: str, amount: float, chain_id: int):
    """
    Swap AMOUNT of FROM_TOKEN to TO_TOKEN.
    """
    if from_token.upper() == to_token.upper():
        raise click.BadParameter("FROM_TOKEN and TO_TOKEN must be different.", param_hint="'TO_TOKEN'")

    account = utils.load_account()
    try:
        transaction_hash = account.swap_tokens(from_token, to_token, amount, chain_id)
    except (exceptions.InvalidTokenError, exceptions.WalletNotConfiguredError, exceptions.BackendError) as error:
        raise click.ClickException(str(error))

    if not transaction_hash:
        raise click.ClickException("Status Backend did not return a transaction hash. The swap was not sent...")

    click.echo(transaction_hash)
