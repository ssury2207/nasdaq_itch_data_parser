# Research data cleanup library: current progress

Last updated: 2026-10-28

## Goal and scope

Build a basic market-data cleanup library for research using Nasdaq public
TotalView-ITCH market-event data. The current milestone is to reconstruct
**one symbol's displayed order book** and generate a best-bid/ask quotes CSV.

This milestone is implemented in `main.py`, with AAPL as the default symbol.
Trade CSV generation, cleanup rules, multiple-symbol book processing, and
performance optimizations have not been implemented.

## Project files

| File or directory | Purpose |
| --- | --- |
| `main.py` | All order-book reconstruction, filtering, CLI, and CSV-writing code. |
| `quotes.csv` | Default generated output; its contents depend on the latest run. |
| `PROGRESS.md` | Current behavior, verification history, and next steps. |
| `.venv/` | Python environment containing the installed `itch` package. |
| `input_file/S112825-v50.txt` | Default uncompressed input, approximately 11 GB (10.5 GiB). |
| `input_file/S112825-v50.txt.gz` | Compressed copy of the default input. |
| `input_file/S061226-v50.txt` | Larger dataset, not used by default. |

At the user's request, all implementation code was consolidated into `main.py`.
The separate `generate_quotes.py`, `order_book.py`, and `test_order_book.py`
files were removed. There are no retained project test files.

Despite the `.txt` extension, the input contains binary ITCH messages, not text
lines. The script currently opens uncompressed input. Reading `.gz` directly
would require `gzip.open(..., 'rb')`; that support is not implemented.

## Running the script

Run these commands from the project directory:

```bash
# Default: process the complete input for AAPL and write quotes.csv.
.venv/bin/python main.py

# Short run: stop after 100 matching AAPL messages, or earlier if the feed ends.
.venv/bin/python main.py --max-events 100

# Explicit full-file run with a separate output filename.
.venv/bin/python main.py --max-events 0 --output AAPL_quotes.csv

# Select another symbol and set an optional cap.
.venv/bin/python main.py --symbol MSFT --max-events 1000 --output MSFT_quotes.csv
```

| Argument | Default | Meaning |
| --- | --- | --- |
| `--input` | `input_file/S112825-v50.txt` | Uncompressed daily input. |
| `--output` | `quotes.csv` | Destination CSV, overwritten when opened. |
| `--symbol` | `AAPL` | Symbol to reconstruct; CLI input is trimmed and uppercased. |
| `--max-events` | `0` | Zero means no message cap; a positive value limits matching messages. |

Both the CLI and `generate_quotes()` currently default to `max_events=0`.
`main()` explicitly passes the CLI value to the function, so changing only the
function's default does not change command-line behavior.

The cap counts **all messages matching the selected symbol's locate code**,
including directory/status messages. It is not a count of all input messages,
order-book updates alone, or output quote rows. There is no elapsed-time cap.

Processing ends at the cap, input EOF, or the parser's end-of-messages system
event (`S` with event code `C`). The script prints a completion summary rather
than printing every market event. It does not currently print periodic progress.

Each run starts a fresh book and rewrites its selected output; it does not
resume from an earlier CSV. A failed reconstruction may leave partial output.

## How symbol filtering works

1. Parse messages sequentially from the beginning of the input.
2. Find the selected symbol's stock-directory message (`R`).
3. Save its `stock_locate` code.
4. Pass messages with that locate code to the selected symbol's book.

In the checked file, AAPL maps to locate code **24**. The code discovers this
mapping for each run instead of hardcoding it. This includes updates that carry
a locate code but do not repeat the symbol, such as cancellations/executions.

The parser still fully decodes messages for other stocks before filtering them
out. No separate symbol-only input file is created.

## What the quotes CSV represents

Each row describes Nasdaq's displayed top of book immediately after a message
changes at least one of these values:

- **Best bid:** highest active displayed buy price.
- **Bid size:** sum of remaining displayed shares at that exact price.
- **Best ask:** lowest active displayed sell price.
- **Ask size:** sum of remaining displayed shares at that exact price.

These are outstanding offers to buy and sell; a quote row does not establish
that a trade happened. The output represents Nasdaq's displayed liquidity,
not a consolidated national best bid and offer across all exchanges.
All displayed sizes, including odd lots, are aggregated; the script does not
implement regulatory round-lot quote eligibility rules.

The internal book retains deeper levels. If the best level disappears, the
next available level becomes best. An update away from the best prices is
stored but produces no row unless it changes the top of book.

## Initialization and daily history

The book starts empty: bid and ask prices are unavailable, and both sizes are
zero. The first buy establishes a bid; the first sell establishes an ask.
One-sided books are preserved.

A complete daily ITCH replay establishes the session's displayed orders through
add messages. We do not carry yesterday's order-reference map into today's
file. An investor's instruction can have multi-day validity, but that is
separate from establishing the displayed orders in the daily market-data feed.

The script assumes the input contains the history required for reconstruction.
It has not independently established full-file completeness. A cancellation,
execution, deletion, or replacement for an unknown order is an error, not a
reason to invent a starting order or silently ignore the update.

For quotes beginning at a later time, earlier events must still establish the
book, or a correctly aligned snapshot is required. Snapshot recovery and
starting output at a specified time are not implemented.

## Order events and their handling

An order event describes an addition or change to an order in the book.
The code maintains an order-ID lookup and aggregated quantities by price:

```text
order ID -> side, integer price, remaining shares
buy price -> total displayed shares
sell price -> total displayed shares
```

| Type | Meaning | Implemented book action |
| --- | --- | --- |
| `A` | Add an unattributed order | Store the order; add its displayed shares to its price level. |
| `F` | Add an attributed order | Same quantity/price handling as `A`. |
| `X` | Cancel a specified quantity | Subtract cancelled shares; remove the order if none remain. |
| `D` | Delete an order | Remove all its remaining shares and its order ID. |
| `U` | Replace an order | Remove the old order; add the new ID, price, and quantity, retaining the side. |
| `E` | Execute an existing order | Subtract executed shares at the resting order's stored price. |
| `C` | Execute with a specified execution price | Reduce the resting order at its stored book price, regardless of printability. |

For `U`, the replacement quantity is its new total, not an increment. Later
updates use the new order ID. For `C`, a different execution price does not move
the resting order to a new book price level.

Empty levels and fully removed orders are deleted. Other message types do not
change this displayed book: `P`/`Q` trade messages do not directly add/remove
displayed orders, and `B` broken-trade messages do not restore an order.

We do not need separate market-order/limit-order handlers: the displayed-book
messages describe the changes needed for quotes. Hidden liquidity is excluded.

The code rejects duplicate active order IDs, invalid add sides/quantities,
unknown referenced orders, and reductions exceeding an order's remaining size.
Unusual quotes, including locked or crossed states, are not cleaned or removed.

## Example from the initial AAPL events

Assuming all earlier events have been processed:

| Incoming event | Best bid | Bid size | Best ask | Ask size | Quote row? |
| --- | ---: | ---: | ---: | ---: | --- |
| Add buy 100 at 276.90 | 276.90 | 100 | unavailable | 0 | Yes |
| Add sell 15 at 278.50 | 276.90 | 100 | 278.50 | 15 | Yes |
| Add buy 300 at 276.96 | 276.96 | 300 | 278.50 | 15 | Yes |
| Add buy 100 at 275.98 | 276.96 | 300 | 278.50 | 15 | No |

Additional shares at the current best price change its size and produce a row.
Deleting the best level exposes a deeper price and also produces a row.

## CSV columns

```csv
timestamp_ns,source_event_index,symbol,bid_price,bid_size,ask_price,ask_size,event_type
```

| Column | Meaning |
| --- | --- |
| `timestamp_ns` | Original ITCH timestamp: nanoseconds since exchange-local midnight, not UTC. |
| `source_event_index` | One-based position of the parsed message in the entire input stream, before filtering. |
| `symbol` | Selected stock symbol. |
| `bid_price`, `ask_price` | Best prices after the triggering event, formatted with four decimal places. |
| `bid_size`, `ask_size` | Total displayed shares at the corresponding best price. |
| `event_type` | ITCH message type that caused the quote change. |

`source_event_index` counts messages across all symbols, not bytes or text lines.
It is a script-generated counter, not an exchange-provided sequence number.
It traces each quote to its input event and preserves ordering when timestamps
are identical.

Prices remain integers internally to avoid floating-point comparison errors.
A missing side has an empty price and size zero. The script writes only changed
quotes, not fixed-interval snapshots. A verified trading date and timezone-aware
absolute timestamp are not currently included in the CSV.

## Verification completed

These are bounded checks, not evidence of a completed full-day validation:

- Initial filter check: 401,497 input messages yielded only 270 AAPL messages,
  including an update without a symbol field.
- Quote preview: 325,328 input messages contained the first 100 matching AAPL
  messages and produced five quote rows consistent with the example above.
- Larger reconstruction check: 15,091,504 input messages contained 10,000 AAPL
  messages and produced 722 quote changes without reconstruction errors. The
  sample included 1,652 deletions, 1,236 replacements, 29 cancellations, and
  271 `E` executions. No `F` or `C` messages occurred in that sample.
- Before their removal, five automated tests passed for empty/one-sided books,
  aggregation, deeper-level promotion, cancellation/deletion, replacement,
  executions including non-printable `C`, exact prices, and invalid updates.
- After consolidation into `main.py`, the preview CSV was byte-for-byte
  unchanged. No test file was retained.
- Default-cap change: a temporary 105-message fixture was processed to EOF by
  default; an explicit cap of 100 stopped at exactly 100 matching messages.

## Performance findings and proposed improvements

The current implementation is intended to be understandable first. Two likely
costs remain, but their contribution has not been profiled:

1. Fully decoding every stock's messages before selecting AAPL.
2. Finding best prices with `max()`/`min()` across active levels before and after
   every supported book event, even if a distant price level changed.

A 100-message AAPL cap may require scanning many more input messages; the
observed preview scanned 325,328. If a function default is changed but the CLI
still passes zero, the script will continue through the complete feed instead.
Both defaults in the current code are zero.

Per-event terminal printing from the original inspection script has already
been removed. CSV output streams to disk; the whole file and output are not
loaded into memory. The active selected-symbol book remains in memory.

Possible next optimizations, discussed but **not implemented**:

- Profile a bounded run to separate parsing, book-update, and CSV costs.
- Inspect message framing and locate codes before fully decoding other stocks.
- Cache best prices or use ordered price structures to avoid repeated scans.
- Extract a reusable symbol-only input for repeated research runs, preserving
  directory information and event order. Keep an original-index mapping if
  quotes must retain positions in the original daily file.

The original input must still be scanned at least once. Any faster version
should produce the same quote rows, prices, sizes, timestamps, and original
source indexes for the same input range.

## Remaining work

1. Profile the current code before implementing optimizations.
2. Validate longer/full-day runs and compare with an independent reference
   where available; distinguish internal consistency from proven completeness.
3. Verify trading-date metadata and decide how to expose absolute timestamps.
4. Add cleanup rules and trade generation only after quote reconstruction is
   sufficiently validated.

There is no elapsed-runtime cap, snapshot recovery, feed-gap recovery, gzip
input handling, or optimization implementation yet. Those require separate
changes; this documentation update does not modify the code or rerun the data.
