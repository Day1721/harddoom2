#!/usr/bin/env python3

from argparse import ArgumentParser

parser = ArgumentParser(description="Converts the microcode from raw binary to C header file.")
parser.add_argument('input', help="the input file")
parser.add_argument('output', help="the output file")

if __name__ == '__main__':
    args = parser.parse_args()

    with open(args.input, 'rb') as f:
        d = f.read()

    if len(d) % 4:
        raise ValueError("length not divisible by 4")

    with open(args.output, 'w') as f:
        f.write('static const uint32_t doomcode2[] = {\n')
        for i in range(0, len(d), 4):
            x = d[i:i+4]
            x = int.from_bytes(x, 'little')
            f.write(f'\t0x{x:08x},\n')
        f.write('};\n')
