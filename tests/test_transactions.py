"""Run with: python -m unittest discover -s tests -v."""

import unittest
from unittest.mock import patch

import pandas as pd
import requests

from status_sdk import exceptions
from tests.transaction_fixtures import (
    CHAINS, OTHER_ADDRESS, WALLET_ADDRESS, RecordingAlchemy, make_account, transfer,
)


class TransactionHistoryTests(unittest.TestCase):
    def setUp(self):
        self.chain_patch = patch("status_sdk.account.constants.ALCHEMY_CHAIN_IDS", CHAINS)
        self.chain_patch.start()
        self.addCleanup(self.chain_patch.stop)

    def fetch(self, fixture, account=None, refresh=False):
        account = account if account is not None else make_account()
        with patch("status_sdk.account.requests.post", fixture):
            return account.get_transactions(refresh=refresh)

    def test_metadata_avoids_block_requests(self):
        fixture = RecordingAlchemy(pages={
            ("base-mainnet", "fromAddress", ""): {"transfers": [
                transfer(metadata={"blockTimestamp": "2024-06-15T10:30:00.000Z"}),
            ]},
        })
        result = self.fetch(fixture)
        self.assertEqual(result.iloc[0]["timestamp"], pd.Timestamp("2024-06-15T10:30:00Z"))
        self.assertEqual(fixture.block_calls, [])

    def test_every_page_requests_metadata(self):
        fixture = RecordingAlchemy(pages={
            ("eth-mainnet", "fromAddress", ""): {"transfers": [], "pageKey": "next"},
            ("eth-mainnet", "fromAddress", "next"): {"transfers": []},
        })
        self.fetch(fixture)
        self.assertEqual(len(fixture.transfer_calls), 5)
        self.assertTrue(all(call["params"][0].get("withMetadata") is True
                            for call in fixture.transfer_calls))

    def test_metadata_same_height_on_different_chains_stays_distinct(self):
        fixture = RecordingAlchemy(pages={
            ("eth-mainnet", "fromAddress", ""): {"transfers": [
                transfer(transaction_hash="eth", metadata={"blockTimestamp": "2024-01-01T00:00:00Z"}),
            ]},
            ("base-mainnet", "fromAddress", ""): {"transfers": [
                transfer(transaction_hash="base", metadata={"blockTimestamp": "2025-01-01T00:00:00Z"}),
            ]},
        })
        result = self.fetch(fixture).set_index("trx_hash")
        self.assertEqual(result.loc["eth", "timestamp"], pd.Timestamp("2024-01-01T00:00:00Z"))
        self.assertEqual(result.loc["base", "timestamp"], pd.Timestamp("2025-01-01T00:00:00Z"))
        self.assertEqual(fixture.block_calls, [])

    def test_metadata_timezones_normalize_to_utc(self):
        fixture = RecordingAlchemy(pages={
            ("eth-mainnet", "fromAddress", ""): {"transfers": [
                transfer(transaction_hash="z", metadata={"blockTimestamp": "2024-06-15T10:30:00.000Z"}),
                transfer(transaction_hash="offset", metadata={"blockTimestamp": "2024-06-15T12:30:00+02:00"}),
            ]},
        })
        result = self.fetch(fixture)
        self.assertTrue(all(value == pd.Timestamp("2024-06-15T10:30:00Z") for value in result.timestamp))
        self.assertEqual(str(result.timestamp.dt.tz), "UTC")
        self.assertEqual(fixture.block_calls, [])

    def test_missing_metadata_uses_correct_chain_and_distinct_pair_keys(self):
        fixture = RecordingAlchemy(pages={
            ("eth-mainnet", "fromAddress", ""): {"transfers": [transfer(transaction_hash="eth")]},
            ("base-mainnet", "fromAddress", ""): {"transfers": [transfer(transaction_hash="base")]},
        }, blocks={("eth-mainnet", "0x64"): "0x3e8", ("base-mainnet", "0x64"): "0x7d0"})
        result = self.fetch(fixture).set_index("trx_hash")
        self.assertEqual(result.loc["eth", "timestamp"], pd.Timestamp(1000, unit="s", tz="UTC"))
        self.assertEqual(result.loc["base", "timestamp"], pd.Timestamp(2000, unit="s", tz="UTC"))
        self.assertEqual({(call["domain"], call["params"][0]) for call in fixture.block_calls},
                         {("eth-mainnet", "0x64"), ("base-mainnet", "0x64")})

    def test_base_height_above_ethereum_head_does_not_query_ethereum(self):
        fixture = RecordingAlchemy(pages={
            ("base-mainnet", "toAddress", ""): {"transfers": [
                transfer(block="0x2000000", sender=OTHER_ADDRESS, recipient=WALLET_ADDRESS),
            ]},
        }, blocks={("eth-mainnet", "0x2000000"): None, ("base-mainnet", "0x2000000"): "0x7d0"})
        result = self.fetch(fixture)
        self.assertEqual(result.iloc[0]["timestamp"], pd.Timestamp(2000, unit="s", tz="UTC"))
        self.assertEqual([call["domain"] for call in fixture.block_calls], ["base-mainnet"])

    def test_missing_null_and_invalid_metadata_share_one_fallback(self):
        fixture = RecordingAlchemy(pages={
            ("base-mainnet", "fromAddress", ""): {"transfers": [
                transfer(transaction_hash="missing"),
                transfer(transaction_hash="null", metadata=None),
                transfer(transaction_hash="invalid", metadata={"blockTimestamp": "not-a-date"}),
                transfer(transaction_hash="empty", metadata={}),
            ]},
        }, blocks={("base-mainnet", "0x64"): "0x7d0"})
        result = self.fetch(fixture)
        self.assertEqual(len(result), 4)
        self.assertTrue(all(value == pd.Timestamp(2000, unit="s", tz="UTC") for value in result.timestamp))
        self.assertEqual(len(fixture.block_calls), 1)
        self.assertEqual(fixture.block_calls[0]["domain"], "base-mainnet")

    def test_later_metadata_for_same_chain_block_avoids_fallback(self):
        fixture = RecordingAlchemy(pages={
            ("base-mainnet", "fromAddress", ""): {"transfers": [transfer(transaction_hash="missing")]},
            ("base-mainnet", "toAddress", ""): {"transfers": [
                transfer(transaction_hash="known", sender=OTHER_ADDRESS, recipient=WALLET_ADDRESS,
                         metadata={"blockTimestamp": "2024-01-01T00:00:00Z"}),
            ]},
        })
        result = self.fetch(fixture)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(value == pd.Timestamp("2024-01-01T00:00:00Z") for value in result.timestamp))
        self.assertEqual(fixture.block_calls, [])

    def test_unusable_metadata_timestamp_values_use_chain_fallback(self):
        for value in [None, 123, True, [], "2024-01-01T00:00:00", "not-a-date"]:
            with self.subTest(value=value):
                fixture = RecordingAlchemy(pages={
                    ("base-mainnet", "fromAddress", ""): {"transfers": [
                        transfer(metadata={"blockTimestamp": value}),
                    ]},
                }, blocks={("base-mainnet", "0x64"): "0x7d0"})
                result = self.fetch(fixture)
                self.assertEqual(result.iloc[0]["timestamp"], pd.Timestamp(2000, unit="s", tz="UTC"))
                self.assertEqual(len(fixture.block_calls), 1)
                self.assertEqual(fixture.block_calls[0]["domain"], "base-mainnet")

    def test_conflicting_metadata_for_same_chain_block_uses_one_lookup(self):
        fixture = RecordingAlchemy(pages={
            ("base-mainnet", "fromAddress", ""): {"transfers": [
                transfer(transaction_hash="first", metadata={"blockTimestamp": "2024-01-01T00:00:00Z"}),
                transfer(transaction_hash="second", metadata={"blockTimestamp": "2025-01-01T00:00:00Z"}),
                transfer(transaction_hash="third", metadata={"blockTimestamp": "2024-01-01T00:00:00Z"}),
            ]},
        }, blocks={("base-mainnet", "0x64"): "0x7d0"})
        result = self.fetch(fixture)
        self.assertTrue(all(value == pd.Timestamp(2000, unit="s", tz="UTC") for value in result.timestamp))
        self.assertEqual(len(fixture.block_calls), 1)
        self.assertEqual(fixture.block_calls[0]["domain"], "base-mainnet")

    def test_distinct_missing_blocks_each_looked_up_once(self):
        fixture = RecordingAlchemy(pages={
            ("eth-mainnet", "fromAddress", ""): {"transfers": [
                transfer(block="0x64", transaction_hash="a"),
                transfer(block="0x64", transaction_hash="b"),
                transfer(block="0x65", transaction_hash="c"),
            ]},
        }, blocks={("eth-mainnet", "0x64"): "0x3e8", ("eth-mainnet", "0x65"): "0x3f4"})
        self.fetch(fixture)
        self.assertEqual(len(fixture.block_calls), 2)

    def test_pagination_schema_signs_and_existing_height_sort_are_preserved(self):
        stamp = {"blockTimestamp": "2024-01-01T00:00:00Z"}
        fixture = RecordingAlchemy(pages={
            ("eth-mainnet", "fromAddress", ""): {"transfers": [
                transfer(block="0x64", transaction_hash="sent", value=2, metadata=stamp),
            ], "pageKey": "next"},
            ("eth-mainnet", "fromAddress", "next"): {"transfers": [
                transfer(block="0x66", transaction_hash="self", recipient=WALLET_ADDRESS, metadata=stamp),
            ]},
            ("base-mainnet", "toAddress", ""): {"transfers": [
                transfer(block="0x65", transaction_hash="received", sender=OTHER_ADDRESS,
                         recipient=WALLET_ADDRESS, value=3, symbol="USDC", metadata=stamp),
            ]},
        })
        result = self.fetch(fixture)
        self.assertEqual(result.columns.tolist(), ["timestamp", "block_number", "trx_hash", "from_address",
                         "to_address", "amount", "symbol", "trx_type", "chain_id"])
        self.assertEqual(result.trx_hash.tolist(), ["self", "received", "sent"])
        self.assertEqual(result.block_number.tolist(), [102, 101, 100])
        by_hash = result.set_index("trx_hash")
        self.assertEqual(by_hash.loc["sent", "amount"], -2)
        self.assertEqual(by_hash.loc["received", "amount"], 3)
        self.assertEqual(by_hash.loc["received", "trx_type"], "received")
        self.assertEqual(by_hash.loc["received", "chain_id"], 8453)
        self.assertEqual(by_hash.loc["self", "trx_type"], "sent")
        self.assertEqual(len(fixture.transfer_calls), 5)

    def test_cache_returns_copies_without_network_calls(self):
        fixture = RecordingAlchemy(pages={
            ("eth-mainnet", "fromAddress", ""): {"transfers": [
                transfer(metadata={"blockTimestamp": "2024-01-01T00:00:00Z"}),
            ]},
        })
        account = make_account()
        first = self.fetch(fixture, account)
        request_count = len(fixture.calls)
        first.loc[0, "amount"] = 999
        second = self.fetch(fixture, account)
        self.assertEqual(second.loc[0, "amount"], -1.25)
        second.loc[0, "amount"] = 888
        self.assertEqual(self.fetch(fixture, account).loc[0, "amount"], -1.25)
        self.assertEqual(len(fixture.calls), request_count)

    def test_refresh_refetches_and_replaces_cache(self):
        key = ("eth-mainnet", "fromAddress", "")
        fixture = RecordingAlchemy(pages={key: {"transfers": [
            transfer(transaction_hash="first", metadata={"blockTimestamp": "2024-01-01T00:00:00Z"}),
        ]}})
        account = make_account()
        self.fetch(fixture, account)
        fixture.pages[key] = {"transfers": [
            transfer(transaction_hash="second", metadata={"blockTimestamp": "2025-01-01T00:00:00Z"}),
        ]}
        result = self.fetch(fixture, account, refresh=True)
        self.assertEqual(result.trx_hash.tolist(), ["second"])
        self.assertEqual(len(fixture.transfer_calls), 8)
        self.assertEqual(self.fetch(fixture, account).trx_hash.tolist(), ["second"])

    def test_failed_refresh_preserves_previous_cached_snapshot(self):
        previous = pd.DataFrame({"existing": ["keep"]})
        account = make_account(transactions=previous.copy())
        fixture = RecordingAlchemy(fail_on={
            ("eth-mainnet", "alchemy_getAssetTransfers", ("fromAddress", "")):
                requests.exceptions.ConnectionError("fixture offline"),
        })
        with self.assertRaises(requests.exceptions.ConnectionError):
            self.fetch(fixture, account, refresh=True)
        pd.testing.assert_frame_equal(self.fetch(fixture, account), previous)

    def test_failed_block_lookup_does_not_cache_partial_history(self):
        account = make_account()
        fixture = RecordingAlchemy(pages={
            ("base-mainnet", "fromAddress", ""): {"transfers": [transfer()]},
        }, fail_on={
            ("base-mainnet", "eth_getBlockByNumber", "0x64"):
                requests.exceptions.Timeout("fixture timed out"),
        })
        with self.assertRaises(requests.exceptions.Timeout):
            self.fetch(fixture, account)
        self.assertIsNone(account._Account__transactions)

    def test_empty_history_preserves_existing_empty_output(self):
        fixture = RecordingAlchemy()
        result = self.fetch(fixture)
        self.assertTrue(result.empty)
        self.assertEqual(result.columns.tolist(), [])
        self.assertEqual(fixture.block_calls, [])

    def test_missing_token_rejected_before_any_request(self):
        fixture = RecordingAlchemy()
        with self.assertRaises(exceptions.WalletNotConfiguredError):
            self.fetch(fixture, make_account(token=None))
        self.assertEqual(fixture.calls, [])


if __name__ == "__main__":
    unittest.main()
