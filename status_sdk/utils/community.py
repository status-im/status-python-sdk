from ..account import Account
from .. import exceptions
from typing import Optional
import pandas as pd

def get_community_info(account: Account, community_id: str) -> dict:
    """
    Get up to date information for the community.
    Reused in `class Community` and `class Channel`

    Parameters:
        - `account` - already logged in account
        - `community_id` - community's ID

    Output:
        - up to date community data
    """
    params = {
        "communityKey": community_id,
        "waitForResponse": True,
        "tryDatabase": True
    }
    response = account._call_rpc("messaging", "fetchCommunity", [params])
    error: dict = response.get("error", {})
    if error:
        raise exceptions.InvalidCommunityKeyError(error["message"])

    if not response["result"]:
        raise exceptions.CommunityNotFoundError(f"Community '{community_id}' was not found...")

    return response["result"]


def get_channel_permissions(account: Account, community_id: str, channel_id: Optional[str] = None) -> pd.DataFrame:
    """
    Get the current permissions for the selected Community Channel

    Parameters:
        - `account` - already logged in account
        - `community_id` - community's ID
        - `channel_id` - channel's ID from `community_id`

    Output:
        - up to date community permissions
    """
    community_info = get_community_info(account, community_id)
    if not community_info["tokenPermissions"]:
        return pd.DataFrame()
    df = pd.DataFrame(community_info["tokenPermissions"].values()).explode("chat_ids")

    # Fill is_private and expand token_criteria
    df = df.assign(
            is_private=df["is_private"].fillna(False)
        ).explode("token_criteria")\
        .reset_index(drop=True)

    # Normalize token_criteria dictionaries into columns
    token_cols = pd.json_normalize(df["token_criteria"])
    if "decimals" not in token_cols:
        token_cols["decimals"] = 0

    token_cols = token_cols.assign(
        df_index = df.index,
        decimals = token_cols["decimals"].fillna(0).astype(int)
    ).rename(columns={"amountInWei": "amount_in_wei", "type": "token_type"})
    contract_cols = [col for col in token_cols.columns if col.startswith("contract_addresses.")]

    # Convert the contract address columns into rows
    token_cols = token_cols.melt(
        id_vars=[
            col for col in token_cols.columns if col not in contract_cols
        ],
        value_vars=contract_cols,
        var_name="chain_id",
        value_name="contract_address"
    )

    # Extract chain ID from:
    # contract_addresses.1 -> 1
    # contract_addresses.42161 -> 42161
    token_cols["chain_id"] = token_cols["chain_id"].str.removeprefix("contract_addresses.").astype(int)

    # Remove rows where there is no contract address
    token_cols = token_cols.dropna(subset=["contract_address"])

    # Join the expanded token data back onto the original dataframe
    df = df.drop(columns=["token_criteria"])\
            .reset_index()\
            .rename(columns={"index": "df_index", "chat_ids": "chat_id"})\
            .merge(token_cols, on="df_index", how="left")\
            .drop(columns=["df_index"])\
            .reset_index(drop=True)

    if channel_id:
        df = df.loc[df["chat_id"] == channel_id].reset_index(drop=True)

    return df.copy()
