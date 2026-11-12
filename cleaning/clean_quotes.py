import csv
from pathlib import Path
from statistics import median

PROJECT = Path(__file__).resolve().parent.parent
INPUT_CSV = PROJECT / 'output_binaries/quotes/quotes_MSFT.csv'
OUTPUT_CSV = PROJECT / 'output_binaries/quotes_clean/quotes_MSFT_clean.csv'
MARKET_OPEN_NS = (9 * 3600 + 30 * 60) * 1_000_000_000
MARKET_CLOSE_NS = 16 * 3600 * 1_000_000_000
MAX_SPREAD_MULTIPLE = 50


def to_ticks(price):
    return int(price.replace('.', ''))


def read_quotes(path):
    with path.open(newline='') as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def no_zero_quotes(rows):
    return [r for r in rows if r['bid_price'] and r['ask_price']
            and to_ticks(r['bid_price']) > 0 and to_ticks(r['ask_price']) > 0]


def exchange_hours_only(rows):
    return [r for r in rows if MARKET_OPEN_NS <= int(r['timestamp_ns']) <= MARKET_CLOSE_NS]


def rm_large_spread(rows):
    if not rows:
        return rows
    spreads = [to_ticks(r['ask_price']) - to_ticks(r['bid_price']) for r in rows]
    limit = MAX_SPREAD_MULTIPLE * median(spreads)
    return [r for r, s in zip(rows, spreads) if s <= limit]


def write_quotes(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    fieldnames, rows = read_quotes(INPUT_CSV)
    print(f'Read {len(rows):,} rows from {INPUT_CSV.name}')
    for step in (no_zero_quotes, exchange_hours_only, rm_large_spread):
        before = len(rows)
        rows = step(rows)
        print(f'{step.__name__:<20} dropped {before - len(rows):>8,}  kept {len(rows):>8,}')
    write_quotes(OUTPUT_CSV, fieldnames, rows)
    print(f'Wrote {OUTPUT_CSV}')


if __name__ == '__main__':
    main()
