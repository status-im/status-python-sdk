from dotenv import load_dotenv
from status_sdk import Account, Community, launch_docker_container, exceptions
import os, ollama, argparse


def parse_args() -> argparse.Namespace:
    """
    Parse the command line arguments of the greeter.

    Output:
        - the parsed `channel_name` and `approve` arguments
    """
    parser = argparse.ArgumentParser(
        prog="community-greet",
        description="Greet new Status Community members with an LLM generated message."
    )
    parser.add_argument(
        "-c", "--channel-name",
        default="intro",
        help="The channel to greet new members in. Created if it does not exist yet. Defaults to '%(default)s'."
    )
    parser.add_argument(
        "-a", "--approve",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Accept pending join requests automatically. Skip the argument to only greet members an admin has accepted."
    )
    return parser.parse_args()


def generate_message(public_key: str) -> str:
    """
    Generate greeting message for new users.

    Parameters:
        - `public_key` - the Status public key of the new joiner

    Output:
        - Personalized LLM message
    """
    prompt = """
    You are the Herald of Battle World, a dark realm inspired by Marvel's Battleworld.

    Welcome each new member with a unique, epic greeting as if they have just entered Battle World.

    Rules:
    - Always include the literal text "{public_key}" exactly as written.
    - Never replace or modify "{public_key}".
    - Write 1 short sentence.
    - Use a mysterious, battle-hardened, RPG tone.
    - Mention Battle World.
    - Refer to the newcomer as a warrior, champion, survivor, contender, or traveller.
    - End with a short call to action about battle, alliances, or survival.
    - Do not mention AI, assistants, Discord, Status, or apps.
    - No emojis or Markdown.
    - Output only the greeting.

    Example:
    A new champion steps onto the scarred lands of Battle World. Welcome, {public_key}. The coming war will test your resolve—forge your legend.
    """

    response = ollama.chat(
        model=os.environ.get("MODEL_NAME"),
        messages=[{'role': 'user', 'content': prompt}],
        options={
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.1,
            "num_predict": 100,
        }
    )

    placeholder = "{public_key}"
    mention = f"@{public_key}"
    output = str(response.message.content).replace("\"", "").replace("—", "-")

    # `str.format` would parse the whole model output, so any stray brace it writes raises
    if placeholder in output:
        output = output.replace(placeholder, mention)
    else:
        output = f"{mention}\n{output}"

    return output

def main(channel_name: str, approve: bool):
    """
    Listen for community join requests and greet every new member in `channel_name`.

    Parameters:
        - `channel_name` - the channel to greet new members in. Created if it does not exist yet
        - `approve` - if `True`, pending join requests are accepted automatically. If `False`, only members accepted by an admin are greeted
    """
    launch_docker_container()
    account = Account(backup_folder=os.path.dirname(__file__))
    account.login(
        password=os.environ["PASSWORD"],
        name=os.environ["NAME"],
        mnemonic=os.environ["MNEMONIC"]
    )
    community = Community(account, url=os.environ["COMMUNITY_URL"])

    try:
        community.create_channel(channel_name, "Greet new community members")
        account.logger.info(f"Channel '{channel_name}' created")
    except exceptions.CommunityDuplicateError:
        account.logger.info(f"Channel '{channel_name}' already exists")

    channel = community[channel_name]

    account.logger.info(f"Listening for incoming {community.name} [{community.id}] requests")
    pending_requests = []
    for request in community.listen_requests():
        member_public_key: str = request["public_key"]
        request_id: str = request["request_id"]
        if request["state"] == "pending" and member_public_key not in pending_requests:
            pending_requests.append(member_public_key)

        if approve and request["state"] == "pending":
            community.accept(request_id)
            account.logger.info(f"Accepted {member_public_key}")
            continue

        if request["state"] != "accept" or member_public_key not in pending_requests:
            continue

        message = generate_message(member_public_key)
        channel.send_message(message)
        pending_requests.remove(member_public_key)


if __name__ == "__main__":
    args = parse_args()
    load_dotenv()
    main(args.channel_name, args.approve)
