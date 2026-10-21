# Transaction-history tests and request counts

`Account.get_transactions` requests Alchemy transfer metadata and uses each
transfer's `metadata.blockTimestamp`. If it is missing, malformed, or lacks a
timezone, the method falls back to `eth_getBlockByNumber` on the transfer's chain.
Contradictory metadata for the same chain/block pair also triggers a lookup.
Fallback lookups are deduplicated by `(chain_id, block_number)`. Timestamps retain
the existing integer-second, UTC representation.

The metadata option is documented in the [Alchemy transfer API](https://www.alchemy.com/docs/data/transfers-api/transfers-endpoints/alchemy-get-asset-transfers)
and its [official request/response reference](https://github.com/alchemyplatform/skills/blob/main/skills/alchemy-api/references/data-transfers-api.md).

## Run without credentials

From a source checkout, using Python 3.11 or later:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m benchmarks.transaction_history --repeats 3 --output transaction-history.json
```

No Alchemy token, wallet keys, logged-in account, or running Status backend is
needed. Tests construct an `Account` without its backend initializer and execute
the imported production method. The recording fixture replaces the external
response boundary. It returns metadata only when the request opts in.

The benchmark sends real JSON-RPC HTTP requests to a temporary server bound to
`127.0.0.1`. It redirects the SDK's configured Alchemy destinations to that
server, preserving the original destination in a fixture header. Responses and
wallet addresses are synthetic. A constrained runner must permit loopback
binding; the server closes when each run finishes.

## What is checked

- Metadata is requested on every page; usable timestamps avoid block requests.
- Equal heights on Ethereum and Base retain distinct timestamps.
- Missing or invalid metadata uses the matching chain, with one lookup per pair.
- A Base height unavailable on Ethereum does not query Ethereum.
- Pagination, signed amounts, existing output columns, height sorting, cache
  copies, refreshes and raised transport failures retain their behavior.

The benchmark also checks the transaction chain/hash multiset, signed amounts,
directions, heights and timestamps against fixture-defined outcomes. Every JSON
report includes the SHA256 of the imported `account.py`. It writes results and
returns a nonzero exit status if a correctness or request-count check fails.

| Controlled scenario | Expected requests after this change |
| --- | ---: |
| 80 transfers across 40 Ethereum blocks, all with metadata | 2 transfer requests, 0 block requests |
| Ethereum and Base at the same height with distinct metadata timestamps | 4 transfer requests, 0 block requests |
| Mixed metadata, with missing entries at two distinct chain/block pairs | 4 transfer requests, 2 block requests |

Each repetition uses a fresh `Account`, so the request counts measure a cold
history fetch. Warm-cache behavior is checked separately in the unit tests.
There are two direction queries per configured chain, plus any pagination;
the first scenario deliberately configures only Ethereum.

## Compare an unmodified checkout

The benchmark can import another checkout's SDK while retaining the same
candidate-owned fixtures and oracles:

```sh
.venv/bin/python -m benchmarks.transaction_history \
  --sdk-root /absolute/path/to/unmodified/status-python-sdk \
  --repeats 3 --output baseline-history.json
```

The unmodified source used during development was commit
`6eddfc2ea56da2d23d535d143243515ebd751772`. It made 42 requests in the
metadata-rich scenario and reused Ethereum timestamps for the Base examples.
The baseline benchmark is expected to fail the candidate acceptance criteria;
its JSON retains the actual incorrect timestamps and lookup destinations.

## Bounds

This is a request-count and output-correctness measurement under controlled
responses. It does not measure live Alchemy availability, production latency,
rate limits, or supported transfer categories across every configured network.
Elapsed local execution time is not a wallet performance claim.

The public method's output fields and block-height sorting remain unchanged;
height order is not chronological order across chains. This change does not
implement the native `wallet_` endpoint requested in
[status-go #7883](https://github.com/status-im/status-go/issues/7883), add token
addresses, or change provider error/retry policies.
