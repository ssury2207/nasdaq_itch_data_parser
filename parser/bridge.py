"""Decode ITCH messages for one symbol and feed them to the C++ order book.

Each order message becomes one text line on the C++ program's standard input:
    order_id type side price shares new_order_id timestamp event_index
- type: A, F, X, D, U, E or C
- side: B or S for A/F; '-' when the message has no side
- price, shares, new_order_id: 0 when the message has no such field
- timestamp: nanoseconds since midnight
- event_index: position of the message in the input file (counts every message, from 1)

Usage:
    .venv/bin/python parser/bridge.py                      # decode and run orderbook/main
    .venv/bin/python parser/bridge.py --print | head       # only print the decoded lines
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from itch.messages import StockDirectoryMessage
from itch.parser import MessageParser

ORDER_TYPES = (b'A', b'F', b'X', b'D', b'U', b'E', b'C')


def decoded_lines(input_path, symbol):
    """Yield one text line per order message for the chosen symbol."""
    stock_locate = None
    with input_path.open('rb') as source:
        for event_index, message in enumerate(MessageParser().parse_file(source), start=1):
            if isinstance(message, StockDirectoryMessage) and message.stock.decode().strip() == symbol:
                stock_locate = message.stock_locate
            if stock_locate is None or message.stock_locate != stock_locate:
                continue
            kind = message.message_type
            if kind not in ORDER_TYPES:
                continue
            side, price, shares, new_id = '-', 0, 0, 0
            if kind in (b'A', b'F'):
                side, price, shares = message.buy_sell_indicator.decode(), message.price, message.shares
            elif kind == b'X':
                shares = message.cancelled_shares
            elif kind in (b'E', b'C'):
                shares = message.executed_shares
            elif kind == b'U':
                price, shares = message.price, message.shares
                new_id = message.new_order_reference_number
            yield (f'{message.order_reference_number} {kind.decode()} {side} {price} {shares} {new_id} '
                   f'{message.timestamp} {event_index}\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', type=Path, default=Path('input_file/S112825-v50_AAPL.txt'))
    parser.add_argument('--symbol', default='AAPL')
    parser.add_argument('--cpp', default='orderbook/main', help='Compiled C++ program to feed (default: orderbook/main)')
    parser.add_argument('--print', action='store_true', help='Print decoded lines instead of running C++')
    args = parser.parse_args()
    lines = decoded_lines(args.input, args.symbol.strip().upper())

    if args.print:
        try:
            sys.stdout.writelines(lines)
        except BrokenPipeError:  # e.g. piped into `head`
            sys.stdout = open(os.devnull, 'w')
        return

    cpp = subprocess.Popen([args.cpp], stdin=subprocess.PIPE, text=True)
    sent = 0
    try:
        for line in lines:
            cpp.stdin.write(line)
            sent += 1
    except BrokenPipeError:
        print('C++ program stopped reading early.', file=sys.stderr)
    finally:
        try:
            cpp.stdin.close()
        except BrokenPipeError:
            pass
    code = cpp.wait()
    print(f'\nSent {sent:,} messages to {args.cpp}; it exited with code {code}.', file=sys.stderr)


if __name__ == '__main__':
    main()
