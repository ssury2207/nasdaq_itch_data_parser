import csv
from pathlib import Path
from statistics import median

PROJECT = Path(__file__).resolve().parent.parent
INPUT_CSV = PROJECT / 'output_binaries/quotes/quotes_MSFT.csv'
OUTPUT_CSV = PROJECT / 'output_binaries/quotes_clean/quotes_MSFT_clean.csv'
MARKET_OPEN_NS = (9 * 3600 + 30 * 60) * 1_000_000_000
MARKET_CLOSE_NS = 16 * 3600 * 1_000_000_000
MAX_SPREAD_MULTIPLE = 50
OUTLIER_WINDOW = 50
OUTLIER_MAXI = 10


def to_ticks(price):
    return int(price.replace('.', ''))


def read_quotes(path):
    with path.open(newline='') as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def exchange_hours_only(rows):
    return [r for r in rows if MARKET_OPEN_NS <= int(r['timestamp_ns']) <= MARKET_CLOSE_NS]


def flag_no_spread(rows):
    for r in rows:
        two_sided = (r['bid_price'] and r['ask_price']
                     and to_ticks(r['bid_price']) > 0 and to_ticks(r['ask_price']) > 0)
        r['no_spread'] = not two_sided
    return rows


def flag_large_spread(rows):
    for r in rows:
        r['large_spread'] = False
    # Keep only the row which has bid and ask 
    ok_rows = [r for r in rows if not r['no_spread']] 
    if not ok_rows:
        return rows
    # Current Spread
    spreads = [to_ticks(r['ask_price']) - to_ticks(r['bid_price']) for r in ok_rows]
    limit = MAX_SPREAD_MULTIPLE * median(spreads)
    for r, s in zip(ok_rows, spreads):
        r['large_spread'] = s >= limit
    return rows


# Valid = has a spread and the spread is not large
def is_valid(r):
    return not r['no_spread'] and not r['large_spread']


# Keep one row per timestamp: the last valid one
# (if no row at that timestamp is valid, keep the last row)
def merge_same_timestamp(rows):
    kept = {}
    for r in rows:
        ts = r['timestamp_ns']
        # Replace if: first row, this row is valid, or the kept row is not valid
        if ts not in kept or is_valid(r) or not is_valid(kept[ts]):
            kept[ts] = r
    # Dict keeps first-seen order, so rows stay in time order
    return list(kept.values())


# Flag quotes whose midpoint is far from the median of nearby quotes (R rmOutliersQuotes, type "standard")
def flag_outliers(rows):
    for r in rows:
        r['is_outlier'] = False
    # Only valid rows are checked and used as neighbours
    valid_rows = [r for r in rows if is_valid(r)]
    if len(valid_rows) < 2:
        return rows
    mids = [(to_ticks(r['bid_price']) + to_ticks(r['ask_price'])) / 2 for r in valid_rows]
    # Whole-day median absolute deviation, scaled like R's mad()
    day_median = median(mids)
    mad = 1.4826 * median(abs(m - day_median) for m in mids)
    # Guard: with MAD = 0 every row would be flagged
    if mad == 0:
        return rows
    limit = OUTLIER_MAXI * mad
    half = OUTLIER_WINDOW // 2
    for i, (r, m) in enumerate(zip(valid_rows, mids)):
        # 25 rows before and 25 after, excluding this row (fewer at the start/end of the day)
        neighbours = mids[max(0, i - half):i] + mids[i + 1:i + 1 + half]
        r['is_outlier'] = abs(m - median(neighbours)) >= limit
    return rows


def write_quotes(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    fieldnames, rows = read_quotes(INPUT_CSV)
    print(f'Read {len(rows):,} rows from {INPUT_CSV.name}')
    steps = (
        (exchange_hours_only, None),
        (flag_no_spread, 'no_spread'),
        (flag_large_spread, 'large_spread'),
        (merge_same_timestamp, None),
        (flag_outliers, 'is_outlier'),
    )
    for step, flag in steps:
        before = len(rows)
        rows = step(rows)
        if flag:
            flagged = sum(1 for r in rows if r[flag])
            print(f'{step.__name__:<22} flagged {flagged:>8,}  rows {len(rows):>8,}')
        else:
            print(f'{step.__name__:<22} dropped {before - len(rows):>8,}  kept {len(rows):>8,}')
    write_quotes(OUTPUT_CSV, fieldnames + ['no_spread', 'large_spread', 'is_outlier'], rows)
    print(f'Wrote {OUTPUT_CSV}')


if __name__ == '__main__':
    main()
