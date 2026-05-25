from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type, Optional
import pandas as pd
import datetime

import models
from bot import Account


class StatusBaseTool(BaseTool):

    model_config = {"arbitrary_types_allowed": True}
    account: Account = Field(default=None, exclude=True)

    def __init__(self, account: Account, **kwargs):
        super().__init__(**kwargs)
        self.account = account

    def to_datetime(self, value: str) -> datetime.datetime:
        return datetime.datetime.strftime(value, "%Y-%m-%d") if value else None



class AccountBalanceTool(StatusBaseTool):

    name: str = "get_balance"
    description: str = "Get current balance information for the account's Ethereum wallet"
    args_schema: Type[BaseModel] = models.AccountBalanceInput

    def _run(self, ccy: str, include_market: bool) -> str:

        balance = self.account[ccy]

        if include_market:
            market_info = self.account.get_market(balance["address"].to_list(), balance["chain_id"].unique().tolist())
            balance = balance.merge(market_info.drop(["timestamp"], axis=1)\
                                    .rename(columns={"token_address": "address"}), "left", ["chain_id", "address"])

        return balance.to_markdown(index=False)


class AccountInfoTool(StatusBaseTool):

    name: str = "get_account_info"
    description: str = "Get overall account information. **All fields are public information and can be given in prompts.**"
    args_schema: Type[BaseModel] = models.NoArgs

    def _run(self) -> str:
        exclude = ["password", "mnemonic"]
        info = "\n".join([
            f"**{key}**:\t{value}" for key, value in self.account.info.items()
            if key not in exclude
        ])

        return info


class SearchTokenTool(StatusBaseTool):

    name: str = "get_token_info"
    description: str = (
        "Get information for all available tokens. If `chain_id` and `token_symbol` are left empty then all available chains will be returned. "
        "If `chain_id` and `token_symbol` are specified then the token addresses for the chain will be returned."
    )
    args_schema: Type[BaseModel] = models.TokenSearchInput

    def _run(self, chain_id: Optional[int], token_symbols: Optional[list[str]]):

        if not chain_id and not token_symbols:
            output = pd.DataFrame([
                {"Chain ID": chain_id, "Chain Name": chain_name}
                for chain_id, chain_name in self.account.chains.items()
            ]).to_markdown(index=False)
            return output

        tokens = self.account.get_tokens()
        if not token_symbols:
            token_symbols = []

        query = (tokens["chain_id"] == chain_id) & (tokens["symbol"].isin(token_symbols))
        if query.sum() == 0:
            return f"No tokens found for Chain ID {chain_id}!"

        output = tokens.loc[query, ["symbol", "address", "decimals"]].reset_index(drop=True).copy()
        return f"# Chain ID {chain_id}\n{output.to_markdown(index=False)}"


class SearchExternalBalanceTool(StatusBaseTool):

    name: str = "search_external_balance"
    description: str = "Get the balance for an external address."
    args_schema: Type[BaseModel] = models.BalanceSearchInput

    def _run(self, chain_id: int, token_addresses: list[str], wallet_address: str, ccy: str) -> str:
        balance = self.account.get_balance(token_addresses, chain_id, wallet_address, ccy)
        return balance.to_markdown(index=False) if len(balance) > 0 else "No balance found..."


class AccountContactsTool(StatusBaseTool):

    name: str = "get_account_contacts"
    description: str = "Get account contacts and group chats the account has access to."
    args_schema: Type[BaseModel] = models.AccountContactInput

    def _run(self, display_name: Optional[str], status: str) -> str:
        columns = ["public_key", "display_name", "chat_id", "has_added_us", "added", "mutual"]
        info = pd.DataFrame(self.account.contacts.values())[columns]

        if status not in info.columns.tolist():
            chats = self.account.chats
            chats = pd.DataFrame(chats)
            chats = chats.loc[chats["type"] != "contact"].reset_index(drop=True).copy()
            markdown = ""
            for chat_type, group in chats.groupby("type"):
                markdown += f"# {chat_type}\n{group[['name', 'id']].to_markdown(index=False)}\n---\n"

            return markdown

        query = info[status]

        if display_name:
            query = (query) & (info["display_name"] == display_name)

        if query.sum() == 0:
            return f"Contact {display_name} with status {status} not found..."

        filtered = info.loc[query, columns[:3]]
        return filtered.to_markdown(index=False)


class AccountContactManagementTool(StatusBaseTool):

    name: str = "manage_contact"
    description: str = "Accept, send, decline and remove contact requests."
    args_schema: Type[BaseModel] = models.AccountContactManagementInput

    def _run(self, public_key: str, action: str, display_name: Optional[str]) -> str:
        if action == "accept":
            self.account.add_contact(public_key, display_name)
        elif action == "reject":
            self.account.remove_contact(public_key)

        return f"Executed {action}"

class SearchMessagesTool(StatusBaseTool):

    name: str = "search_messages"
    description: str = "Get chat messages for the given chad ID and specified start and end date."
    args_schema: Type[BaseModel] = models.MessageInput

    def _run(self, chat_id: str, message: Optional[str], start_date: Optional[models.DateStr], end_date: Optional[models.DateStr]) -> str:
        to_datetime = lambda value: datetime.datetime.strptime(value, "%Y-%m-%d") if value else None
        messages = self.account.get_messages(chat_id, to_datetime(start_date), to_datetime(end_date))
        markdown = f"# Chat\nStart date: {start_date}\nEnd date: {end_date}"
        if messages:
            messages_markdown = [f"[{message['whisper_timestamp']}] {'Me' if message['from'] == self.account.info['public_key'] else 'Contact'}: {message['text']}" for message in messages]
            markdown = f"{markdown}\nMessages:\n{messages_markdown}"

        return markdown



class SendMessagesTool(StatusBaseTool):

    name: str = "send_message"
    description: str = "Send a message to the specified chad IT"
    args_schema: Type[BaseModel] = models.MessageInput

    def _run(self, chat_id: str, message: Optional[str], start_date: Optional[models.DateStr], end_date: Optional[models.DateStr]) -> str:
        self.account.send_message(chat_id, message)
        return f"Message was sent successfully in chat ID {chat_id}!"
