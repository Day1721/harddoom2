#!/usr/bin/env python3

"""A dead simple microcode assembler for HardDoom ][™ microcode.

Accepts 4 things in the source:

- "reg abc 12": defines the name abc as register #12
- "const abc 12": defines the name abc as the constant 12
- "abc:": defines the name abc as a constant equal to the current code
  position
- "<instruction> <arguments>...": arguments can be immediate constants, names
  defined as constants or registers, or simple constant expressions involving +.

Works in two simple passes:

- first pass: determines the value of every name, counts instructions to know
  the current position for labels
- second pass: assembles the instructions
"""

from argparse import ArgumentParser

from sys import exit

parser = ArgumentParser(description="Assemble HardDoom™ microcode.")
parser.add_argument('source', help="the source file")
parser.add_argument('output', help="the output file")


MAX_INSNS = 0x1000


class Reg:
    def __init__(self, pos):
        self.pos = pos

    def assemble(self, symtab, arg):
        t, v = symtab[arg]
        if t != 'R':
            raise ValueError(f"argument needs to be a register")
        return v << self.pos


class Imm:
    def __init__(self, pos, size, *, signed=False, offset=0):
        self.pos = pos
        self.size = size
        self.signed = signed
        self.offset = offset

    def assemble(self, symtab, arg):
        val = 0
        if arg[0].isdigit() or arg[0] == '-':
            off = int(arg, 0)
            sym = None
        elif '+' in arg:
            sym, off = arg.split('+')
            off = int(off, 0)
        elif '-' in arg:
            sym, off = arg.split('-')
            off = -int(off, 0)
        else:
            sym = arg
            off = 0
        if sym is None:
            val = 0
        else:
            t, val = symtab[sym]
            if t != 'C':
                raise ValueError(f"argument needs to be a constant")
        val += off
        val -= self.offset
        if self.signed:
            m = 1 << (self.size - 1)
            r = range(-m, m)
        else:
            r = range(1 << self.size)
        if val not in r:
            raise ValueError(f"immediate out of range ({val})")
        val &= (1 << self.size) - 1
        return val << self.pos


class Insn:
    def __init__(self, opcode, *args):
        self.opcode = opcode
        self.args = args

    def assemble(self, symtab, *args):
        if len(args) != len(self.args):
            raise ValueError(f"instruction needs {len(self.args)} arguments")
        res = self.opcode
        for a, sa in zip(args, self.args):
            res |= sa.assemble(symtab, a)
        return res

REG_A = Reg(21)
REG_B = Reg(16)
REG_C = Reg(11)
IMM_12 = Imm(0, 12)
IMM_7 = Imm(12, 7)
IMM_S11 = Imm(0, 11, signed=True)
IMM_S16 = Imm(0, 16, signed=True)
IMM_B = Imm(16, 5)
IMM_CO1 = Imm(11, 5, offset=1)
IMM_D = Imm(6, 5)
IMM_E = Imm(1, 5)


INSNS = {
    # Unconditional branch.
    'b':        Insn(0x00000000, IMM_12),
    # Branch with link -- saves return address to given reg.
    'bl':       Insn(0x00010000, REG_A, IMM_12),
    # Branch indirect -- jumps to reg+imm.
    'bi':       Insn(0x00020000, REG_A, IMM_12),
    # Alias of the above, with imm == 0.
    'br':       Insn(0x00020000, REG_A),
    # Fetches next command from the FIFO to the registers.
    'rcmd':     Insn(0x00030000),
    # Triggers PONG_ASYNC interrupt.
    'pong':     Insn(0x00040000),
    # Triggers FE_ERROR interrupt, halts FE.  Argument is error code.
    'error':    Insn(0x00050000, IMM_12),
    # Bumps the given statistics counter by one.
    'stat':     Insn(0x00060000, IMM_12),
    # Loads a new page table.  First argument selects which page table to reload, second
    # is the (shifted) address.
    'setpt':    Insn(0x00070000, IMM_12, REG_A),
    # Sends a command to one of the FIFOs.  First argument is command type, second is payload.
    'xycmd':    Insn(0x00080000, IMM_12, REG_A),
    'texcmd':   Insn(0x00090000, IMM_12, REG_A),
    'flatcmd':  Insn(0x000a0000, IMM_12, REG_A),
    'fuzzcmd':  Insn(0x000b0000, IMM_12, REG_A),
    'ogcmd':    Insn(0x000c0000, IMM_12, REG_A),
    # Translate a virtual address to physical (arg 1 is destination,
    # arg 2 is virtual address, arg 3 selects which page table to use).
    # The result is bits 8-39 of the phys address.
    "tlb":      Insn(0x00001000, REG_A, REG_B, IMM_12),
    # Store (arg 1 is value, arg 2 + 3 are the address).
    "st":       Insn(0x00002000, REG_A, REG_B, IMM_12),
    # Load (arg 1 is value, arg 2 + 3 are the address).
    "ld":       Insn(0x00003000, REG_A, REG_B, IMM_12),
    # Branch if equal.
    "be":       Insn(0x00004000, REG_A, REG_B, IMM_12),
    # Branch if not equal.
    "bne":      Insn(0x00005000, REG_A, REG_B, IMM_12),
    # Branch if greater (unsigned).
    "bg":       Insn(0x00006000, REG_A, REG_B, IMM_12),
    # Branch if less or equal (unsigned).
    "ble":      Insn(0x00007000, REG_A, REG_B, IMM_12),
    # Branch if bit set (argument 1 is value to check, argument 2 is bit index).
    "bbs":      Insn(0x00008000, REG_A, IMM_B, IMM_12),
    # Branch if bit clear.
    "bbc":      Insn(0x00009000, REG_A, IMM_B, IMM_12),
    # Branch if equal (with immediate).
    "bei":      Insn(0x04000000, REG_A, IMM_7, IMM_12),
    # Branch if not equal (with immediate).
    "bnei":     Insn(0x04080000, REG_A, IMM_7, IMM_12),
    # Branch if greater (unsigned, with immediate).
    "bgi":      Insn(0x04100000, REG_A, IMM_7, IMM_12),
    # Branch if less or equal (unsigned, with immediate).
    "blei":     Insn(0x04180000, REG_A, IMM_7, IMM_12),
    # Move bitfield.  Arguments: dst reg, dst start bit, src reg, src start bit, size.
    "mb":       Insn(0x08000000, REG_A, IMM_D, REG_B, IMM_E, IMM_CO1),
    # Deposit.  Alias of the above, with src start bit set to 0.
    "dep":      Insn(0x08000000, REG_A, IMM_D, REG_B, IMM_CO1),
    # Move bitfield with clear.  Like mb, but clears remaining bits of the destination.
    "mbc":      Insn(0x08000001, REG_A, IMM_D, REG_B, IMM_E, IMM_CO1),
    # Extract.  Alias of the above, with dst start bit set to 0.
    "extr":     Insn(0x08000001, REG_A, REG_B, IMM_E, IMM_CO1),
    # Move.  Alias of the above, with both start bits set to 0 and length set to 32.
    "mov":      Insn(0x0800f801, REG_A, REG_B),
    # Deposit immediate.  Arguments: dst reg, dst bit position, source value, size.
    "depi":     Insn(0x0c000000, REG_A, IMM_B, IMM_S11, IMM_CO1),
    # Clear bit.  Alias of the above, with value fixed to 0 and size to 1.
    "clrb":     Insn(0x0c000000, REG_A, IMM_B),
    # Set bit.  Likewise.
    "setb":     Insn(0x0c000001, REG_A, IMM_B),
    # Load immediate.
    "li":       Insn(0x10000000, REG_A, IMM_S16),
    # Add immediate.
    "ai":       Insn(0x14000000, REG_A, REG_B, IMM_S16),
    # Add (a = b + i + c).
    "a":        Insn(0x18000000, REG_A, REG_B, IMM_S11, REG_C),
    # Add register (alias of the above with immediate == 0).
    "ar":       Insn(0x18000000, REG_A, REG_B, REG_C),
    # Subtract (a = b + i - c).
    "s":        Insn(0x1c000000, REG_A, REG_B, IMM_S11, REG_C),
    # Subtract register (alias of the above with immediate == 0).
    "sr":       Insn(0x1c000000, REG_A, REG_B, REG_C),
    # Sign: a = signum(b - c).
    "sign":     Insn(0x20000000, REG_A, REG_B, REG_C),
}



def assemble(f):
    # First pass.
    symtab = {}
    insns = []

    for i, l in enumerate(f):
        lno = i + 1
        l, _, _ = l.partition('#')
        l = l.strip().split()
        try:
            while l and l[0].endswith(':'):
                name = l[0][:-1]
                if not name:
                    raise ValueError("empty label name")
                l = l[1:]
                if name in symtab:
                    raise ValueError(f"{name} is already in the symbol table")
                symtab[name] = ('C', len(insns))
            if not l:
                continue
            if l[0] == 'reg':
                _, name, reg = l
                reg = int(reg)
                if reg not in range(32):
                    raise ValueError(f"register {reg} is out of range")
                if name in symtab:
                    raise ValueError(f"{name} is already in the symbol table")
                symtab[name] = ('R', reg)
            elif l[0] == 'const':
                _, name, val = l
                val = int(val, 0)
                if name in symtab:
                    raise ValueError(f"{name} is already in the symbol table")
                symtab[name] = ('C', val)
            else:
                if len(insns) == MAX_INSNS:
                    raise OverflowError("code length limit reached")
                insn = INSNS[l[0]]
                insns.append((insn, lno, l[1:]))
        except Exception as e:
            print(f"Error in line {lno}: {e}")
            exit(1)

    # Second pass.
    res = []
    for insn, lno, args in insns:
        try:
            res.append(insn.assemble(symtab, *args).to_bytes(4, 'little'))
        except Exception as e:
            print(f"Error in line {lno}: {e}")
            exit(1)
    return b''.join(res)

if __name__ == '__main__':
    args = parser.parse_args()
    with open(args.source) as f:
        data = assemble(f)
    with open(args.output, 'wb') as f:
        f.write(data)
