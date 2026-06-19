from langchain_groq import ChatGroq
from langchain.agents import create_agent
from dotenv import load_dotenv
import os
import sys

# Temp solution until repo it turned into a PyPI library
# Add the repo root to sys.path so `bot` is importable when running this
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import tools
from bot import Account, launch_docker_container

class StatusToolKit:

    def __init__(self, password: str, display_name: str, mnemonic: str, alchemy_token: str, coingecko_api_key: str):
        self.account = Account()
        self.account.login(
            password=password,
            display_name=display_name,
            mnemonic=mnemonic,
            alchemy_token=alchemy_token,
            coingecko_api_key=coingecko_api_key
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
            tools.SendMessagesTool(account=self.account)
        ]


    def get_tools(self) -> list:
        return self.tools


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
        os.environ["DISPLAY_NAME"],
        os.environ["MNEMONIC"],
        os.environ["ALCHEMY_TOKEN"],
        os.environ["COINGECKO_API_KEY"]
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
        latest_message = None
        for chat in message["event"]["chats"]:

            from_public_key = chat.get("lastMessage", {}).get("from")
            if from_public_key != PUBLIC_KEY:
                continue

            latest_message = chat["lastMessage"]["text"]
            break

        if not latest_message:
            continue

        result = agent.invoke({
            "messages": [
                {
                    "role": "user",
                    "content": latest_message
                }
            ]
        })

        response = result['messages'][-1].content
        status_toolkit.account.send_message(PUBLIC_KEY, response)
