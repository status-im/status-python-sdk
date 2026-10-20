from .utils import misc as utils
from . import exceptions
from typing import Callable, Optional, Union
import datetime, re

class SavedAddress:

    __NAME_LENGTH = 24
    def __init__(self, raw: dict, call_rpc: Callable[[str, str, Optional[Union[list, dict]]], dict]):
        self.__call_rpc = call_rpc
        self.__address: str = raw["address"]
        self.__name: str = raw["name"]
        self.__ens: str = raw["ens"]
        self.__created_at = utils.to_datetime(raw["createdAt"])
        self.__deleted = False

    @property
    def address(self) -> str:
        """
        The saved wallet address
        """
        return self.__address

    @property
    def created_at(self) -> Optional[datetime.datetime]:
        """
        When the address was saved
        """
        return self.__created_at

    @property
    def name(self) -> str:
        """
        The name the address was saved under
        """
        return self.__name

    @name.setter
    def name(self, value: str):
        self.validate_name(value)
        self.__upsert(name=value)
        self.__name = value

    @property
    def ens(self) -> str:
        """
        The ENS name of the address
        """
        return self.__ens

    @ens.setter
    def ens(self, value: str):
        self.__upsert(ens=value)
        self.__ens = value

    def delete(self):
        """
        Delete the currently saved contact from the wallet
        """
        if self.__deleted:
            return

        response = self.__call_rpc("messaging", "deleteSavedAddress", [self.address, False])
        error = response.get("error", {}) or {}
        if error:
            raise exceptions.SavedAddressError(error.get("message"))

        self.__deleted = True

    def to_dict(self) -> dict[str, Optional[Union[str, datetime.datetime]]]:
        """
        Turn the object into a dictionary.
        Useful for building a `DataFrame` out of `Wallet.saved_addresses`.

        Output:
            - dictionary with the `address`, `name`, `ens` and `created_at` properties.
            `created_at` is kept as a `datetime`, so convert it before serialising to JSON
        """
        return {
            "address": self.address,
            "name": self.name,
            "ens": self.ens,
            "created_at": self.created_at
        }

    def __str__(self):
        return "\n".join([f"{key.title().replace('_', ' ')}: " + (str(value) if value else "None") for key, value in self.to_dict().items()])

    @classmethod
    def validate_name(cls, name: str):
        """
        Validate a saved address name based on Status App rules.

        Status App validation rules:
            - Only letters, numbers, underscores (_) and hyphens (-) allowed
            - Words are separated by a **single** whitespace, so no leading, trailing or repeated whitespaces
            - Must be between 1 and 24 characters long

        Parameters:
            - `name` - the saved address name to validate
        """
        if not isinstance(name, str):
            raise exceptions.InvalidSavedAddressNameError("Saved address name must be a string.")

        if not 1 <= len(name) <= cls.__NAME_LENGTH:
            raise exceptions.InvalidSavedAddressNameError(f"Saved address name must be between 1 and {cls.__NAME_LENGTH} characters long.")

        if not re.fullmatch(r"[A-Za-z0-9_-]+(?: [A-Za-z0-9_-]+)*", name):
            raise exceptions.InvalidSavedAddressNameError("Saved address name can contain only letters, numbers, underscores (_), hyphens (-) and single whitespaces between words.")

    def __upsert(self, **changes):
        """
        Save the address back to Status Backend.

        Parameters:
            - `changes` - the fields to overwrite, by their `SavedAddress` property name
        """
        if self.__deleted:
            raise exceptions.SavedAddressError(f"'{self.__address}' has been deleted...")

        params = [{
            "address": self.__address,
            "name": changes.get("name", self.__name),
            "ens": changes.get("ens", self.__ens),
            "isTest": False
        }]
        # RPC can be used to create and edit a contact
        response = self.__call_rpc("messaging", "upsertSavedAddress", params)
        error = response.get("error", {}) or {}
        if error:
            raise exceptions.SavedAddressError(error.get("message"))
