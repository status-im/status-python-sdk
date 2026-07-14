from langchain_groq import ChatGroq
from langchain.agents import create_agent
from dotenv import load_dotenv
from typing import Optional
import os
import tools
from status_sdk import Account, launch_docker_container

class StatusToolKit:

    def __init__(self, password: str, display_name: str, mnemonic: str, alchemy_token: str, coingecko_api_key: str, infura_token: str, backup_folder: Optional[str] = None):
        self.account = Account(backup_folder=backup_folder)
        self.account.login(
            password=password,
            name=display_name,
            mnemonic=mnemonic,
            alchemy_token=alchemy_token,
            coingecko_api_key=coingecko_api_key,
            infura_token=infura_token
        )
        self.display_name = self.account.display_name
        self.tools = [
            tools.AccountBalanceTool(account=self.account),
            tools.AccountInfoTool(account=self.account),
            tools.AccountContactsTool(account=self.account),
            tools.AccountContactManagementTool(account=self.account),
            tools.SearchTokenTool(account=self.account),
            tools.SearchExternalBalanceTool(account=self.account),
            tools.SearchMessagesTool(account=self.account),
            tools.SearchTransactionsTool(account=self.account),
            tools.SendMessagesTool(account=self.account),
            tools.SendTransactionTool(account=self.account),
            tools.SwapTokensTool(account=self.account)
        ]


    def get_tools(self) -> list:
        return self.tools

    def normalize_amount(self, amount: str, token_key: str) -> float:
        """
        Convert the WEI amount from Payment requests to a regular amount.

        Parameters:
            - `amount` - the amount in WEI
            - `token_key` - the Chain ID and Token Address

        Output:
            - The regular amount
        """
        chain_id, address = token_key.split("-")
        tokens = self.account.get_tokens()
        query = (tokens["address"].str.lower() == address.lower()) & (tokens["chain_id"] == int(chain_id))
        decimals = tokens.loc[query, "decimals"].iloc[0]
        raw_amount = int(amount) / (10**int(decimals))
        return float(raw_amount)

if __name__ == "__main__":

    launch_docker_container()
    load_dotenv()

    PUBLIC_KEY = os.environ["FROM_PUBLIC_KEY"]

    llm = ChatGroq(
        model=os.environ["GROQ_MODEL"],
        api_key=os.environ["GROQ_API_KEY"],
        temperature=0,
        max_tokens=None,
        reasoning_format="parsed",
        timeout=None,
        max_retries=2
    )

    status_toolkit = StatusToolKit(
        os.environ["PASSWORD"],
        os.environ["NAME"],
        os.environ["MNEMONIC"],
        os.environ["ALCHEMY_TOKEN"],
        os.environ["COINGECKO_API_KEY"],
        os.environ["INFURA_TOKEN"]
    )
    agent = create_agent(
        model=llm,
        tools=status_toolkit.get_tools(),
        system_prompt=(
            "You are my personal crypto assistant. "
            "Use the available tools to answer questions accurately. "
            "You have access to my account."
        )
    )

    for message in status_toolkit.account.listen_messages():
        content = None
        for chat in message["event"]["chats"]:

            latest_message: dict = chat.get("lastMessage", {})
            if not latest_message:
                continue

            from_public_key = latest_message.get("from")
            if from_public_key != PUBLIC_KEY:
                continue

            content = chat["lastMessage"]["text"]
            payment_requests: list[dict] = latest_message.get("paymentRequests", [])
            if payment_requests:
                payment_request = payment_requests[0]
                amount = status_toolkit.normalize_amount(payment_request["amount"], payment_request["tokenKey"])
                chain_id, token_address = payment_request["tokenKey"].split("-")
                payment_content = {
                    "Receiver Wallet": payment_request['receiver'],
                    "Token Symbol": payment_request['symbol'],
                    "Token Address": token_address,
                    "Amount": amount,
                    "Chain ID": chain_id
                }
                content += f"\n---\n# Payment request\n" + "\n".join([
                    f"{name}: {value}"
                    for name, value in payment_content.items()
                ])

            break

        if not content:
            continue

        result = agent.invoke({
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ]
        })

        response = result['messages'][-1].content
        status_toolkit.account.send_message(PUBLIC_KEY, response)
