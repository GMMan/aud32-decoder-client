import os
import struct


class Aud32File:
    def __init__(self, path) -> None:
        self.f = open(path, 'rb')
        (self.ctype,) = struct.unpack('<H', self.f.read(2))
        if self.ctype != 0x5541: # "AU"
            raise ValueError("File is not in Audio32 format")

        (self.sr, self.br, self.ch, self.frm_len, self.file_len, self.mf, self.sf, self.mbf,
         self.pcs, self.rec, self.header_len, self.audio32_type, self.stop_code, self.s_header) = \
            struct.unpack('<HHHIIHHHHHHHHH', self.f.read(0x20))

        if self.s_header != 0xffff:
            self.s_header_data = self.f.read(0x20)
        else:
            self.s_header_data = None

        if self.mf == 1:
            self.init_old_samples = self.f.read(0x140)

            orig_offset = self.f.tell()
            self.f.seek(-self.sf * 2, os.SEEK_END)
            self.end_samples = self.f.read(self.sf * 2)
            self.f.seek(orig_offset, os.SEEK_SET)
        else:
            self.init_old_samples = None
            self.end_samples = None

        self._frame_index = 0


    def read_a32_frame(self):
        if self._frame_index < self.frm_len:
            data = self.f.read(self.br * 10 // 400)
            self._frame_index += 1
            return data
        else:
            raise RuntimeError("All frames have been read")


    def close(self):
        self.f.close()
