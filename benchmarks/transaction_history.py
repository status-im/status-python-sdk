"""Run Account.get_transactions against controlled JSON-RPC over loopback HTTP.

This measures request counts and output correctness, not production latency.
Run this candidate-owned script with --sdk-root to measure an unmodified checkout.
An oracle failure still produces JSON and returns a nonzero exit status.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
from threading import Thread
from unittest.mock import patch
from urllib.parse import urlparse


HERE = Path(__file__).resolve().parents[1]
OUTPUT_COLUMNS = [
    "timestamp", "block_number", "trx_hash", "from_address", "to_address",
    "amount", "symbol", "trx_type", "chain_id",
]


@contextmanager
def loopback_transport(account_module, responder):
    """Retain actual requests encoding/HTTP/response decoding without external I/O."""
    import requests

    records = []
    handler_errors = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                original_url = self.headers["X-Fixture-Alchemy-URL"]
                records.append({"domain": urlparse(original_url).hostname, "payload": payload})
                response = responder(original_url, json=payload).json()
                encoded = json.dumps(response).encode()
                self.send_response(200)
            except Exception as error:
                handler_errors.append(f"{type(error).__name__}: {error}")
                encoded = json.dumps({"error": {"message": str(error)}}).encode()
                self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    session = requests.Session()
    session.trust_env = False
    local_url = f"http://127.0.0.1:{server.server_port}/json-rpc"

    def post(url, **kwargs):
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".g.alchemy.com"):
            raise AssertionError(f"Unexpected SDK destination: {url}")
        headers = dict(kwargs.pop("headers", {}))
        headers["X-Fixture-Alchemy-URL"] = url
        kwargs.setdefault("timeout", 5)
        return session.post(local_url, headers=headers, **kwargs)

    try:
        with patch.object(account_module.requests, "post", post):
            yield records, handler_errors
    finally:
        session.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if thread.is_alive():
            raise RuntimeError("Loopback fixture server did not stop")


def validate_frame(frame, expected):
    """Use fixture-defined outcomes independent of the SDK timestamp derivation."""
    failures = []
    columns = list(frame.columns)
    if columns != OUTPUT_COLUMNS:
        failures.append(f"schema: expected {OUTPUT_COLUMNS!r}, got {columns!r}")
    actual_rows = frame.to_dict("records")
    if len(actual_rows) != len(expected):
        failures.append(f"row count: expected {len(expected)}, got {len(actual_rows)}")
    observed = Counter((int(row["chain_id"]), row["trx_hash"]) for row in actual_rows)
    desired = Counter(expected.keys())
    if observed != desired:
        failures.append("transaction chain/hash multiset does not match fixture")
    wrong_timestamps = 0
    timestamp_mismatches = []
    wrong_amounts = 0
    wrong_directions = 0
    wrong_blocks = 0
    for row in actual_rows:
        oracle = expected.get((int(row["chain_id"]), row["trx_hash"]))
        if oracle is None:
            continue
        timestamp = row["timestamp"]
        if timestamp.tzinfo is None or int(timestamp.timestamp()) != oracle["timestamp"]:
            wrong_timestamps += 1
            timestamp_mismatches.append({
                "chain_id": int(row["chain_id"]), "transaction_hash": row["trx_hash"],
                "expected_unix_seconds": oracle["timestamp"], "actual": str(timestamp),
            })
        if row["amount"] != oracle["amount"]:
            wrong_amounts += 1
        if row["trx_type"] != oracle["direction"]:
            wrong_directions += 1
        if row["block_number"] != oracle["block_number"]:
            wrong_blocks += 1
    for count, label in [
        (wrong_timestamps, "timestamps"), (wrong_amounts, "signed amounts"),
        (wrong_directions, "sent/received classifications"), (wrong_blocks, "block numbers"),
    ]:
        if count:
            failures.append(f"{count} incorrect {label}")
    return {
        "rows": len(actual_rows), "columns": columns,
        "incorrect_timestamps": wrong_timestamps, "incorrect_signed_amounts": wrong_amounts,
        "incorrect_directions": wrong_directions, "incorrect_block_numbers": wrong_blocks,
        "timestamp_mismatches": timestamp_mismatches,
        "failures": failures,
    }


def make_scenarios(fixtures):
    def timestamp_metadata(seconds):
        return {"blockTimestamp": datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")}

    def new_scenario(name, description, chains, expected_requests):
        return {"name": name, "description": description, "chains": chains,
                "expected_requests": expected_requests, "pages": {}, "blocks": {}, "expected": {}}

    def add(scenario, domain, chain_id, block, seconds, direction, tx_number, metadata=True):
        sender = fixtures.WALLET_ADDRESS if direction == "sent" else fixtures.OTHER_ADDRESS
        recipient = fixtures.OTHER_ADDRESS if direction == "sent" else fixtures.WALLET_ADDRESS
        tx_hash = f"0x{tx_number:064x}"
        values = {"block": hex(block), "transaction_hash": tx_hash, "sender": sender,
                  "recipient": recipient, "value": 1.25}
        if metadata:
            values["metadata"] = timestamp_metadata(seconds)
        item = fixtures.transfer(**values)
        query_direction = "fromAddress" if direction == "sent" else "toAddress"
        scenario["pages"].setdefault((domain, query_direction, ""), {"transfers": []})["transfers"].append(item)
        scenario["blocks"][(domain, hex(block))] = hex(seconds)
        scenario["expected"][(chain_id, tx_hash)] = {
            "timestamp": seconds, "amount": -1.25 if direction == "sent" else 1.25,
            "direction": direction, "block_number": block,
        }

    metadata = new_scenario(
        "ethereum_40_blocks_80_transfers_with_metadata",
        "40 sent and 40 received distinct transactions across 40 Ethereum blocks; every response includes timestamp metadata when requested",
        {"eth-mainnet": 1}, 2,
    )
    for index in range(40):
        for offset, direction in enumerate(("sent", "received")):
            add(metadata, "eth-mainnet", 1, 100 + index, 1_700_000_000 + 12 * index,
                direction, index * 2 + offset + 1)

    collision = new_scenario(
        "same_height_different_chain_timestamps",
        "Ethereum and Base have equal numeric block heights but different timestamps; metadata is available for both",
        {"eth-mainnet": 1, "base-mainnet": 8453}, 4,
    )
    add(collision, "eth-mainnet", 1, 100, 1_700_000_000, "sent", 1_001)
    add(collision, "base-mainnet", 8453, 100, 1_800_000_000, "received", 1_002)

    fallback = new_scenario(
        "mixed_metadata_chain_scoped_fallback",
        "Metadata timestamps are retained; four missing metadata entries share two chain/block pairs and require exactly one fallback per pair",
        {"eth-mainnet": 1, "base-mainnet": 8453}, 6,
    )
    for index, (domain, chain_id, start) in enumerate([
        ("eth-mainnet", 1, 1_700_000_000), ("base-mainnet", 8453, 1_800_000_000),
    ]):
        add(fallback, domain, chain_id, 100, start, "sent", 2_000 + 10 * index)
        add(fallback, domain, chain_id, 101, start + 12, "sent", 2_001 + 10 * index, metadata=False)
        add(fallback, domain, chain_id, 101, start + 12, "received", 2_002 + 10 * index, metadata=False)
    return [metadata, collision, fallback]


def load_sdk(sdk_root):
    sys.path.insert(0, str(sdk_root))
    module = importlib.import_module("status_sdk.account")
    source = Path(module.__file__).resolve()
    requested = (sdk_root / "status_sdk" / "account.py").resolve()
    if source != requested:
        raise RuntimeError(f"Wrong source imported: {source}; requested {requested}")
    spec = importlib.util.spec_from_file_location(
        "history_benchmark_fixtures", HERE / "tests" / "transaction_fixtures.py",
    )
    fixtures = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = fixtures
    spec.loader.exec_module(fixtures)
    return module, fixtures, source


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", type=Path, default=HERE,
                        help="Checkout whose actual status_sdk.account is imported")
    parser.add_argument("--output", type=Path, help="Also save the JSON report here")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    module, fixtures, source = load_sdk(args.sdk_root.resolve())
    report = {
        "format_version": 1,
        "scope": "Controlled JSON-RPC responses over loopback HTTP; no real Alchemy, credentials, or Status backend",
        "measurement": "Actual HTTP request counts and fixture-oracle output correctness; no production latency claim",
        "source": {"file": "status_sdk/account.py", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
        "python": platform.python_version(), "repeats": args.repeats, "scenarios": [],
    }
    for scenario in make_scenarios(fixtures):
        runs = []
        for repetition in range(args.repeats):
            responder = fixtures.RecordingAlchemy(deepcopy(scenario["pages"]), deepcopy(scenario["blocks"]))
            account = fixtures.make_account()
            result = {"repetition": repetition + 1, "failures": []}
            with patch.dict(module.constants.ALCHEMY_CHAIN_IDS, scenario["chains"], clear=True):
                with loopback_transport(module, responder) as (records, handler_errors):
                    try:
                        frame = account.get_transactions(refresh=True)
                        result.update(validate_frame(frame, scenario["expected"]))
                    except Exception as error:
                        result["failures"].append(f"SDK raised {type(error).__name__}: {error}")
            by_method = Counter(record["payload"].get("method") for record in records)
            by_domain = Counter(record["domain"] for record in records)
            metadata_requested = sum(
                record["payload"].get("method") == "alchemy_getAssetTransfers"
                and record["payload"]["params"][0].get("withMetadata") is True
                for record in records
            )
            result.update({"request_count": len(records), "requests_by_method": dict(by_method),
                           "requests_by_domain": dict(by_domain), "metadata_transfer_requests": metadata_requested,
                           "block_lookups": [
                               {"domain": record["domain"], "block_number": record["payload"]["params"][0]}
                               for record in records if record["payload"].get("method") == "eth_getBlockByNumber"
                           ],
                           "http_handler_errors": handler_errors})
            result["failures"].extend(handler_errors)
            if len(records) != scenario["expected_requests"]:
                result["failures"].append(
                    f"request budget: expected {scenario['expected_requests']}, got {len(records)}"
                )
            result["passed"] = not result["failures"]
            runs.append(result)
        report["scenarios"].append({"name": scenario["name"], "description": scenario["description"],
                                    "expected_requests": scenario["expected_requests"], "runs": runs,
                                    "passed": all(run["passed"] for run in runs)})
    report["passed"] = all(scenario["passed"] for scenario in report["scenarios"])
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
