import datetime, os, pickle, yaml, time
import pandas as pd
from typing import Any
from pathlib import Path
from dotenv import load_dotenv
from hashlib import sha256
# Manual file imports
from bot import Account, Logger
from postgres import Postgres

def to_sha256_hash(value: str) -> str:
    """
    Hash personal information before it is put in the database.

    Parameters:
        - `value` - personal information

    Output:
        - sha256 hashed value
    """
    return sha256(value.encode()).hexdigest()

def to_midnight(timestamp: datetime.datetime) -> datetime.datetime:
    """
    Convert the given timestamp to midnight

    Parameters:
        - `timestamp` - current timestap

    Output:
        - `timestamp` at midnight
    """
    return timestamp.replace(minute=0, second=0, hour=0, microsecond=0)

def load_config(file_path: str) -> dict:
    """
    Load the config file and the `.env` variables

    Parameter:
        - `file_path` - the file path of the config yaml file. The `.env` variable must be in the same folder

    Output:
        - The config variables and secret from `.env`
    """
    with open(file_path, "r") as f:
        config: dict = yaml.safe_load(f)

    env_file_path = os.path.join(os.path.dirname(file_path), ".env")
    load_dotenv(env_file_path)

    config["env_vars"] = {
        key: value
        for key, value in os.environ.items()
        if key.startswith(("POSTGRES_", "STATUS_"))
    }

    return config

def extract_community_channels(account: Account, community: dict, latest_dates: dict[str, pd.Timestamp]) -> pd.DataFrame:
    """
    Extract the community channel messages.

    Parameters:
        - `account` - logged in Status Bot account
        - `community` - the current community from `account`
        - `start_timestamp` - start timestamp for message fetching
        - `end_timestamp` - end timestamp for message fetching

    Output:
        - DataFrame with all of the community messages for the given start and end timestamps
    """
    # Column name -> True if data should be hashed
    bridge_key = "bridge_message"
    columns = {
        "id": True,
        "whisper_timestamp": False,
        "from": True,
        "seen": False,
        "chat_id": False,
        "community_id": False,
        "message_type": False,
        "response_to": True,
        "timestamp": False,
        "deleted": False,
        "extracted_timestamp": False,
    }

    final = []
    for channel in community["channels"]:

        now = datetime.datetime.now()
        start_timestamp = latest_dates.get(channel["chat_id"])
        if start_timestamp:
            start_timestamp += datetime.timedelta(seconds=1)
        else:
            # Node will only return  known / fetched messages for this channel.
            # Without enabling community archives feature the node can only fetch last 30 days (from store nodes).
            start_timestamp = to_midnight(now - datetime.timedelta(days=30))

        account.logger.info(f"Starting message extraction for # {channel['name']} [{start_timestamp} - {now}]")
        messages = account.get_messages(channel["chat_id"], start_timestamp, now)
        messages = pd.DataFrame(messages)
        if len(messages) == 0:
            account.logger.info(f"No messages found")
            continue

        account.logger.info(f"Extracted {len(messages)} message(s)")
        messages = messages.assign(
            community_id = community["id"],
            extracted_timestamp = now
        )
        final.append(messages)

    extracted_data = pd.concat(final, ignore_index=True) if final else pd.DataFrame()
    if len(extracted_data) == 0:
        return extracted_data

    existing_columns = extracted_data.columns.to_list()
    for column, should_hash in columns.items():
        if column not in existing_columns:
            loc = len(extracted_data.columns.to_list())
            extracted_data.insert(loc, column, None)
            continue

        if should_hash:
            extracted_data[column] = extracted_data[column].astype(str).apply(to_sha256_hash)

    if bridge_key in extracted_data.columns:
        extracted_data["source"] = extracted_data[bridge_key].apply(lambda value: value["bridgeName"] if not pd.isna(value) else "status")
    else:
        extracted_data["source"] = "status"

    extracted_data = extracted_data[list(columns.keys()) + ["source"]].assign(
        deleted = extracted_data["deleted"].fillna(False),
        seen = extracted_data["seen"].fillna(False)
    )
    account.logger.info(f"Sensitive data has been hashed")

    return extracted_data

def save_file(file_path: str, data: Any):
    """
    Save data to a pickle file. Creates directories if they don't exist.

    Parameters:
        - `file_path` - Full pikle path
        - `data` - Python object to be saved
    """
    folder = os.path.dirname(file_path)
    if len(folder) > 0:
        os.makedirs(folder, exist_ok=True)

    if isinstance(data, pd.DataFrame):
        data.to_csv(file_path, index=False)
        return

    with open(file_path, "wb") as f:
        pickle.dump(data, f)

def create_bot(config: dict) -> Account:
    """
    Initialized a logged in bot account that will monitor the communities.

    Parameters:
        - `config` - the `load_config` configuration

    Output:
        - Logged in Bot account
    """
    params = config.get("bot", {}).get("params", {})
    account = Account(**params)
    available_accounts = [acc["display_name"] for acc in account.available_accounts]

    prefix = "STATUS_"
    params = {
        key.replace(prefix, "").lower(): value
        for key, value in config["env_vars"].items()
        if key.startswith(prefix)
    }
    if params["display_name"] in available_accounts:
        params.pop("mnemonic")

    account.login(**params)
    if account.info["compressed_key"] != config["bot"]["compressed_key"]:
        raise Exception("Target compressed key and logged in compressed key are different...")
    else:
        account.logger.info("[SUCCESS] Logged in with correct account")

    balance = account["GBP"]
    query = (balance["symbol"] == "SNT") & (balance["fiat_value"] > 0) & (balance["chain_id"] == 1)
    if query.sum() != 1:
        raise Exception("There were issues with Infura Token and Coingecko initialization...")
    else:
        account.logger.info("[SUCCESS] Wallet balance is available")

    account.profile_picture = os.path.join(os.path.dirname(__file__), "assets", "profile.jpg")
    account.logger.info(f"Account Information:\nCompressed Key: {account.info['compressed_key']}\nPublic Key: {account.info['public_key']}\nURL: {account.info['url']}")
    return account

def download(account: Account, folder: str, config: dict):
    """
    Download Status App messages / info from communities and store them in pickle files.

    Parameters:
        - `folder` - the folder where the files will be created. Sub folders are automatically created
        - `config` - the `load_config` configuration
    """
    file_path = os.path.join(os.path.dirname(__file__), config["files"]["current_state"])
    latest_dates: dict[str, pd.Timestamp] = pd.read_pickle(file_path) if os.path.exists(file_path) else {}

    get_file_name = lambda: str(to_midnight(datetime.datetime.now()).timestamp()).replace(".", "")
    communities = account.communities
    if not communities:
        account.logger.warning("No communities found...")

    for community in communities:

        if not community["is_member"]:
            continue

        community_folder_name = community["name"].replace(" ", "-")
        messages_folder = os.path.join(folder, "messages", community_folder_name)
        community_info_folder = os.path.join(folder, "community", community_folder_name)

        account.logger.info(f"Extracting data for {community['name']}")
        community["extracted_timestamp"] = datetime.datetime.now()

        file_path = os.path.join(community_info_folder, get_file_name() + ".pkl")
        if not os.path.exists(file_path):
            save_file(file_path, community)
            account.logger.info(f"Created {file_path}")

        file_path = os.path.join(messages_folder, get_file_name() + ".csv")
        if not os.path.exists(file_path):
            messages = extract_community_channels(account, community, latest_dates)
            if len(messages) > 0:
                save_file(file_path, messages)
                account.logger.info(f"Created {file_path}")

def store(folder: str, config: dict, logger: Logger):
    """
    Upload Status App `download` file to Postgres.
    NOTE: The Postgres schema must already exist

    Parameters:
        - `folder` - the folder where the files will be created. Sub folders are automatically created
        - `config` - the `load_config` configuration
    """
    path = Path(folder)
    table_name_mapping: dict[str, str] = config["postgres"]["tables"]
    table_schema = config["postgres"]["schema"]

    upload: dict[str, list] = {}

    file_path = os.path.join(os.path.dirname(__file__), config["files"]["current_state"])
    latest_dates: dict[str, pd.Timestamp] = pd.read_pickle(file_path) if os.path.exists(file_path) else {}

    completed = []

    files = list(path.rglob("*.pkl")) + list(path.rglob("*.csv"))
    logger.info(f"There are {len(files)} file(s) to upload")
    for file_path in files:

        table_name = table_name_mapping.get(file_path.parent.parent.name)
        if not table_name:
            continue

        file_name = str(file_path.name)
        data = pd.read_pickle(file_path) if file_name.endswith(".pkl") else pd.read_csv(file_path)
        if isinstance(data, dict):
            data = pd.DataFrame([data])

        for column in data.columns:
            if "timestamp" not in column:
                continue
            data[column] = pd.to_datetime(data[column])

        if table_name not in upload:
            upload[table_name] = []

        if "timestamp" in data.columns:
            latest_dates.update(data.groupby("chat_id")["timestamp"].max().to_dict())

        upload[table_name].append(data)
        completed.append(str(file_path))

    save_file(config["files"]["current_state"], latest_dates)
    logger.info(f"Updated {config['files']['current_state']}")

    prefix = "POSTGRES_"
    params = {
        key.replace(prefix, "").lower(): value
        for key, value in config["env_vars"].items()
        if key.startswith(prefix)
    }
    connector = Postgres(**params)
    for table_name, data in upload.items():
        if len(data) == 0:
            continue

        df = pd.concat(data, ignore_index=True).assign(batch_timestamp = datetime.datetime.now())
        json_columns = [
            column
            for column in df.columns
            if len(df[column].dropna()) > 0 and isinstance(df[column].dropna().reset_index(drop=True).iloc[0], (dict, list))
        ]
        connector.insert(df, table_name, table_schema, json_columns)
        logger.info(f"Uploaded {len(df)} record(s) to {table_schema}.{table_name}")

    for file_path in completed:
        os.remove(file_path)
        logger.info(f"Deleted {file_path}")

if __name__ == "__main__":
    folder = os.path.dirname(__file__)
    config = load_config(os.path.join(folder, "config.yaml"))
    upload_folder = os.path.join(os.path.dirname(__file__), "uploads")
    logger = Logger()
    account = create_bot(config)

    while True:
        download(account, upload_folder, config)
        store(upload_folder, config, logger)
        logger.info(f"Sleeping for {config['sleep']} minute(s)")
        time.sleep(config["sleep"] * 60)
