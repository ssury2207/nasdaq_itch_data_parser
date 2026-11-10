"""Copy one symbol's messages and all market-wide messages into a smaller ITCH file.

The output keeps the original binary format, so main.py can read it unchanged.
"""

import argparse
from pathlib import Path

CHUNK_SIZE = 64 * 1024 * 1024
MARKET_WIDE_LOCATE = 0  # System event and other market-wide messages.


def extract_symbol(input_path, output_path, symbol='AAPL'):
    if input_path.resolve() == output_path.resolve():
        raise ValueError('Input and output paths must differ')
    target = symbol.encode().ljust(8)
    stock_locate = None
    scanned = kept = 0
    buffer = b''

    with input_path.open('rb') as source, output_path.open('wb') as destination:
        while chunk := source.read(CHUNK_SIZE):
            buffer += chunk
            view = memoryview(buffer)
            position, end = 0, len(buffer)
            out = bytearray()
            # Each message is a 2-byte big-endian length followed by the message.
            while position + 2 <= end:
                length = (view[position] << 8) | view[position + 1]
                stop = position + 2 + length
                if stop > end:
                    break
                message_type = view[position + 2]
                locate = (view[position + 3] << 8) | view[position + 4]
                if (stock_locate is None and message_type == ord('R')
                        and view[position + 13:position + 21] == target):
                    stock_locate = locate
                if locate == MARKET_WIDE_LOCATE or locate == stock_locate:
                    out += view[position:stop]
                    kept += 1
                scanned += 1
                position = stop
            destination.write(out)
            view.release()
            buffer = buffer[position:]

    if buffer:
        raise ValueError(f'Input ends with {len(buffer)} bytes of an incomplete message')
    if stock_locate is None:
        raise ValueError(f'No stock-directory entry found for {symbol}')
    return scanned, kept


def main():
    args_parser = argparse.ArgumentParser(description=__doc__)
    args_parser.add_argument('--input', type=Path, default=Path('input_file/S112825-v50.txt'))
    args_parser.add_argument('--output', type=Path, default=None,
                             help='Default: <input name>_<SYMBOL>.txt next to the input')
    args_parser.add_argument('--symbol', default='AAPL')
    args = args_parser.parse_args()
    symbol = args.symbol.strip().upper()
    output = args.output or args.input.with_name(f'{args.input.stem}_{symbol}{args.input.suffix}')
    try:
        scanned, kept = extract_symbol(args.input, output, symbol)
    except (OSError, ValueError) as error:
        args_parser.exit(1, f'Error: {error}\n')
    print(f'Scanned {scanned:,} messages; kept {kept:,} for {symbol} and market-wide events '
          f'in {output}.')


if __name__ == '__main__':
    main()
