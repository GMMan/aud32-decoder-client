import os
import sys
from pyrsp.rsp import CortexM3

from converter import Converter


# Start QEMU first:
# qemu-system-arm -cpu cortex-m3 -machine lm3s6965evb -nographic -kernel core1_rom_decomp.bin -s

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: {} <src_path> <dest_path>'.format(sys.argv[0]))
        sys.exit(1)
    
    src_path = sys.argv[1]
    dest_path = sys.argv[2]

    rsp = CortexM3(1234, verbose=False)
    converter = Converter(rsp)
    for path in os.listdir(src_path):
        print(path)
        filename = os.path.basename(path)
        filename_no_ext = os.path.splitext(filename)[0]
        converter.start_convert(os.path.join(src_path, path), os.path.join(dest_path, '{}.wav'.format(filename_no_ext)))
        rsp.run(setpc=False)
