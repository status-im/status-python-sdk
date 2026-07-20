from dotenv import load_dotenv
from status_sdk import Account, GroupChat, launch_docker_container
from detoxify import Detoxify
import os, threading, torch

# `warnings` is shared by every check_message thread, so the
# read-modify-write of a member's warning count must be atomic
warnings_lock = threading.Lock()

def check_message(account: Account, message: dict, warnings: dict, group_chat: GroupChat, model: Detoxify, threshold: float = 0.6, warning_limit: int = 3):
    """
    Score a single message and warn (or remove) its author.
    """
    public_key = message["from"]
    if public_key == account.info["public_key"]:
        return

    label, score = max(model.predict(message["text"]).items(), key=lambda item: item[1])
    account.logger.info(f"Message: '{message['text']}'\t\t{label} - {(score * 100):.2f}%")

    if score < threshold:
        return

    with warnings_lock:
        warnings[public_key] = warnings.get(public_key, 0) + 1
        count = warnings[public_key]

    if count < warning_limit:
        group_chat.send_message(f"Warning {count} /{warning_limit} - @{public_key} please keep it civil.", message["id"])
        account.logger.info(f"Sent warning to {public_key}")
    elif count >= warning_limit:
        group_chat.send_message(f"Removing @{public_key} member after {warning_limit} warnings.")
        account.logger.info(f"Removed {public_key} from {group_chat.name}")
        group_chat.remove(public_key)

def main():
    launch_docker_container()
    load_dotenv()
    account = Account(backup_folder=os.path.dirname(__file__))
    account.login(
        password=os.environ["PASSWORD"],
        name=os.environ["NAME"],
        mnemonic=os.environ["MNEMONIC"]
    )
    group_chat = GroupChat(account, os.environ["GROUP_CHAT_ID"])
    warnings = {}

    device = "cuda" if torch.cuda.is_available() else "cpu"
    account.logger.info(f"Loading Detoxify [{device}]")
    model = Detoxify("original", device=device)
    account.logger.info(f"Listening Group Chat {group_chat.name}")
    for message in account.listen_messages():
        for chat in message["event"]["chats"]:
            if chat["id"] != group_chat.id:
                continue

            threading.Thread(
                target=check_message,
                args=(account, chat["lastMessage"], warnings, group_chat, model),
                daemon=True
            ).start()

if __name__ == "__main__":
    main()
