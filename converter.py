from enum import Enum
import struct
import wave
from pyrsp.rsp import RSP
from formats import Aud32File


class ConverterState(Enum):
    IDLE = 0
    WAIT_FOR_BP_START = 1
    WAIT_FOR_BP_INITTED = 2
    WAIT_FOR_BP_DECODED = 3


class Converter:
    CMD_IDLE = 0
    CMD_INIT = 1
    CMD_DECODE = 2

    BUFFER_COUNT = 80
    BP_ADDR = 0x1d2ac
    CTX_ADDR = 0x20000800
    CTX_SIZE = 0xd7ac  # Find this from built patch's map file

    def __init__(self, rsp: RSP) -> None:
        if rsp is None:
            raise ValueError("rsp cannot be None")

        self.rsp = rsp
        self.state = ConverterState.IDLE
        self.packet_count = 0


    def start_convert(self, in_path, out_path):
        self.a32 = Aud32File(in_path)
        self.out_path = out_path
        self.decoded_samples = bytes()
        self.frames_submitted = 0
        self.state = ConverterState.WAIT_FOR_BP_START

        def cb_thunk():
            return self._rsp_cb()

        self.rsp.set_br_a(self.rsp.format_addr(Converter.BP_ADDR), cb_thunk, sym='bp')


    def _rsp_cb(self):
        try:
            if self.state is ConverterState.IDLE:
                pass
            elif self.state is ConverterState.WAIT_FOR_BP_START:
                self._run_state_start()
            elif self.state is ConverterState.WAIT_FOR_BP_INITTED:
                self._run_state_initted()
            elif self.state is ConverterState.WAIT_FOR_BP_DECODED:
                self._run_state_decoded()

            if self.state is not ConverterState.IDLE:
                # Continue running
                self.rsp.step_over_br()
        except RuntimeError:
            self._finalize()
            raise


    def _run_state_start(self):
        params = self._make_init_params(self.a32.sr, self.a32.br * 10, self.a32.init_old_samples)
        rpc_ctx = self._make_rpc_ctx(Converter.CMD_INIT, params)
        self._put_rpc_ctx(rpc_ctx)
        self.state = ConverterState.WAIT_FOR_BP_INITTED


    def _run_state_initted(self):
        rpc_ctx = self._get_rpc_ctx()
        rc = self._extract_rc(rpc_ctx)
        if rc != 0:
            raise RuntimeError('Decoder init returned {}'.format(rc))
        self._submit_frames()


    def _run_state_decoded(self):
        rpc_ctx = self._get_rpc_ctx()
        rc = self._extract_rc(rpc_ctx)
        if rc != 0:
            raise RuntimeError('Decoder decode returned {}'.format(rc))

        params = self._extract_param(rpc_ctx)
        num_buffers = self._extract_num_buffers(params)
        out_buffer = self._extract_outbuffer(params)
        out_buffer = out_buffer[0:num_buffers * 320 * 2]
        self.decoded_samples += out_buffer

        if self.frames_submitted < self.a32.frm_len:
            self._submit_frames()
        else:
            self._finish_decode()


    def _finish_decode(self):
        if self.a32.mf:
            self.decoded_samples += self.a32.end_samples

        with wave.open(self.out_path, 'wb') as wav:
            wav.setparams((self.a32.ch, 2, self.a32.sr // self.a32.ch,
                          len(self.decoded_samples) // 2 // self.a32.ch,
                          'NONE', 'not compressed'))
            wav.writeframesraw(self.decoded_samples)

        self._finalize()


    def _submit_frames(self):
        prepared_input = bytes()
        num_frames = 0
        input_size = 0
        size_per_frame = self.a32.br * 10 // 400
        max_size = self._get_in_buffer_length()

        while self.frames_submitted + num_frames < self.a32.frm_len and \
              input_size + size_per_frame <= max_size and \
              num_frames < Converter.BUFFER_COUNT:
            prepared_input += self.a32.read_a32_frame()
            num_frames += 1
            input_size += size_per_frame

        params = self._make_decode_params(num_frames, prepared_input)
        rpc_ctx = self._make_rpc_ctx(Converter.CMD_DECODE, params)
        self._put_rpc_ctx(rpc_ctx)
        self.frames_submitted += num_frames
        self.state = ConverterState.WAIT_FOR_BP_DECODED


    def _finalize(self):
        self.rsp.del_br(self.rsp.format_addr(Converter.BP_ADDR))
        # Originally tried to use `finish_cb()` here, but it freezes on the next file
        self.rsp.exit = True
        self.a32.close()
        self.state = ConverterState.IDLE


    def _put_rpc_ctx(self, ctx):
        # with open('dumps/{}_out.bin'.format(self.packet_count), 'wb') as f:
        #     f.write(ctx)
        self.rsp.store(ctx, Converter.CTX_ADDR)


    def _get_rpc_ctx(self):
        ctx = self.rsp.dump(Converter.CTX_SIZE, Converter.CTX_ADDR)
        # with open('dumps/{}_in.bin'.format(self.packet_count), 'wb') as f:
        #     f.write(ctx)
        self.packet_count += 1
        return ctx


    def _extract_rc(self, ctx):
        (_, rc) = struct.unpack('<ii', ctx[0:8])
        return rc


    def _extract_param(self, ctx):
        return ctx[8:]


    def _extract_num_buffers(self, param):
        (num_buffers,) = struct.unpack('<i', param[0:4])
        return num_buffers


    def _extract_outbuffer(self, param):
        return param[4 + self._get_in_buffer_length():]


    def _make_rpc_ctx(self, cmd, params):
        return struct.pack('<ii', cmd, 0x12345678) + params


    def _make_init_params(self, freq, bitr, old_samples):
        has_init_old_samples = 0 if old_samples is None else 1
        if not has_init_old_samples:
            old_samples = b'\0' * 160 * 2
        return struct.pack('<iii', freq, bitr, has_init_old_samples) + old_samples


    def _make_decode_params(self, num_buffers, input_buffer):
        if num_buffers > Converter.BUFFER_COUNT:
            raise ValueError("Too many buffers")

        buffer_total_length = self._get_in_buffer_length()
        if len(input_buffer) > buffer_total_length:
            raise ValueError("Input buffer is too large")

        if len(input_buffer) < buffer_total_length:
            input_buffer += b'\0' * (buffer_total_length - len(input_buffer))

        return struct.pack('<i', num_buffers) + input_buffer


    def _get_in_buffer_length(self):
        return Converter.BUFFER_COUNT * 50
