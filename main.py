"""Generate one symbol's best bid/ask CSV from a daily Nasdaq ITCH feed."""

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from itch.messages import StockDirectoryMessage
from itch.parser import MessageParser

@dataclass(frozen=True)
class Order:
    side: bytes
    price: int
    shares: int


@dataclass(frozen=True)
class Quote:
    bid_price: int | None
    bid_size: int
    ask_price: int | None
    ask_size: int


class OrderBook:
    def __init__(self):
        self.orders = {}
        self.bids = {}
        self.asks = {}

    def quote(self):
        bid = max(self.bids, default=None)
        ask = min(self.asks, default=None)
        return Quote(bid, self.bids.get(bid, 0), ask, self.asks.get(ask, 0))

    def _order(self, order_id):
        if order_id not in self.orders:
            raise ValueError(f"Unknown order reference {order_id}; book history may be incomplete")
        return self.orders[order_id]

    def _validate_add(self, order_id, side, shares):
        if order_id in self.orders:
            raise ValueError(f"Duplicate order reference {order_id}")
        if side not in (b'B', b'S') or shares <= 0:
            raise ValueError(f"Invalid side or quantity for order {order_id}")

    def _add(self, order_id, side, price, shares):
        self._validate_add(order_id, side, shares)
        self.orders[order_id] = Order(side, price, shares)
        levels = self.bids if side == b'B' else self.asks
        levels[price] = levels.get(price, 0) + shares

    def _reduce(self, order_id, shares):
        order = self._order(order_id)
        if not 0 < shares <= order.shares:
            raise ValueError(f"Invalid reduction {shares} for order {order_id} with {order.shares} shares")
        levels = self.bids if order.side == b'B' else self.asks
        levels[order.price] -= shares
        if levels[order.price] == 0:
            del levels[order.price]
        if shares == order.shares:
            del self.orders[order_id]
        else:
            self.orders[order_id] = Order(order.side, order.price, order.shares - shares)

    def apply(self, message):
        """Apply one symbol-filtered message; return a quote only if it changed."""
        kind = message.message_type
        if kind not in (b'A', b'F', b'X', b'D', b'U', b'E', b'C'):
            return None
        before = self.quote()
        order_id = message.order_reference_number
        if kind in (b'A', b'F'):
            self._add(order_id, message.buy_sell_indicator, message.price, message.shares)
        elif kind == b'X':
            self._reduce(order_id, message.cancelled_shares)
        elif kind in (b'E', b'C'):
            # Even a non-printable execution reduces the displayed resting order.
            # Use its stored book price, not C's execution_price.
            self._reduce(order_id, message.executed_shares)
        elif kind == b'D':
            self._reduce(order_id, self._order(order_id).shares)
        elif kind == b'U':
            old = self._order(order_id)
            new_id = message.new_order_reference_number
            self._validate_add(new_id, old.side, message.shares)
            self._reduce(order_id, old.shares)
            self._add(new_id, old.side, message.price, message.shares)
        after = self.quote()
        return after if after != before else None


def format_price(price):
    """Convert ITCH Price(4) to an exact decimal string without floats."""
    if price is None:
        return ''
    return f'{price // 10000}.{price % 10000:04d}'


def generate_quotes(input_path, output_path, symbol='AAPL', max_events=0):
    if input_path.resolve() == output_path.resolve():
        raise ValueError('Input and output paths must differ')
    book = OrderBook()  # Empty at the start of the daily feed.
    stock_locate = None
    matched = rows = scanned = 0

    with input_path.open('rb') as source, output_path.open('w', newline='') as destination:
        writer = csv.writer(destination)
        writer.writerow(['timestamp_ns', 'source_event_index', 'symbol',
                         'bid_price', 'bid_size', 'ask_price', 'ask_size', 'event_type'])
        for scanned, message in enumerate(MessageParser().parse_file(source), start=1):
            if isinstance(message, StockDirectoryMessage) and message.stock.decode().strip() == symbol:
                stock_locate = message.stock_locate
            if stock_locate is None or message.stock_locate != stock_locate:
                continue
            matched += 1
            try:
                quote = book.apply(message)
            except ValueError as error:
                raise ValueError(f'Event {scanned}, type {message.message_type.decode()}, '
                                 f'timestamp {message.timestamp}: {error}. '
                                 f'{output_path} contains partial output.') from error
            if quote is not None:
                writer.writerow([message.timestamp, scanned, symbol,
                                 format_price(quote.bid_price), quote.bid_size,
                                 format_price(quote.ask_price), quote.ask_size,
                                 message.message_type.decode()])
                rows += 1
            # Counts all matching messages, including directory and status messages.
            if max_events and matched >= max_events:
                break
    if stock_locate is None:
        raise ValueError(f'No stock-directory entry found for {symbol}')
    return scanned, matched, rows


def main():
    args_parser = argparse.ArgumentParser(description=__doc__)
    args_parser.add_argument('--input', type=Path, default=Path('input_file/S112825-v50.txt'))
    args_parser.add_argument('--output', type=Path, default=Path('quotes.csv'))
    args_parser.add_argument('--symbol', default='AAPL')
    args_parser.add_argument('--max-events', type=int, default=0,
                             help='Optional cap on matching messages (default: 0, process entire file)')
    args = args_parser.parse_args()
    if args.max_events < 0:
        args_parser.error('--max-events must be zero or positive')
    try:
        scanned, matched, rows = generate_quotes(args.input, args.output,
                                               args.symbol.strip().upper(), args.max_events)
    except (OSError, ValueError) as error:
        args_parser.exit(1, f'Error: {error}\n')
    print(f'Scanned {scanned:,} messages; processed {matched:,} for {args.symbol.upper()}; '
          f'wrote {rows:,} quote changes to {args.output}.')
    if args.max_events and matched >= args.max_events:
        print('Message cap reached. Omit --max-events or set it to 0 to process the entire file.')


if __name__ == '__main__':
    main()
