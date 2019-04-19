all: doomcode2.bin doomcode2.h

doomcode2.h: doomcode2.bin
	python mkhdr.py doomcode2.bin doomcode2.h

doomcode2.bin: doomcode2.hd2
	python hd2asm.py doomcode2.hd2 doomcode2.bin
