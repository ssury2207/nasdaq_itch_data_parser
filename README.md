# data_analysis

Builds one symbol's best bid/ask quotes CSV from a daily Nasdaq TotalView-ITCH 5.0 feed.

## Requirements

- Python 3.10 or newer (tested with 3.12)
- Packages in `requirements.txt`

## Setup

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Input data

Put the uncompressed ITCH files in `input_file/` (default: `input_file/S112825-v50.txt`).
Despite the `.txt` extension, these are binary files. The script cannot read `.gz` files directly, so decompress first:

```bash
gunzip -c zip/S112825-v50.txt.gz > input_file/S112825-v50.txt
```

## Running

```bash
# Full run for AAPL, writes quotes.csv
.venv/bin/python main.py

# Quick test: stop after 100 AAPL messages
.venv/bin/python main.py --max-events 100

# Another symbol and output file
.venv/bin/python main.py --symbol MSFT --output MSFT_quotes.csv
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--input` | `input_file/S112825-v50.txt` | Uncompressed ITCH input file |
| `--output` | `quotes.csv` | Output CSV (overwritten if it exists) |
| `--symbol` | `AAPL` | Stock symbol |
| `--max-events` | `0` | Stop after this many messages for the symbol; `0` means the whole file |

## Output columns

`timestamp_ns, source_event_index, symbol, bid_price, bid_size, ask_price, ask_size, event_type`

A row is written only when the best bid or ask changes.
