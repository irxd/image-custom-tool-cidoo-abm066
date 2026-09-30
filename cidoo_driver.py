#!/usr/bin/env python3
"""
CIDOO ABM066 Keyboard LCD Driver for macOS.
Reverse engineered from Windows Image Custom Tool 0703.exe.
Uses macOS native IOKit / CoreFoundation via ctypes (zero external dependencies).
"""

import ctypes
import ctypes.util
import time
import datetime
from typing import List, Tuple, Optional, Callable

# Load macOS system frameworks
_iokit = ctypes.cdll.LoadLibrary(ctypes.util.find_library('IOKit'))
_cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library('CoreFoundation'))

kCFAllocatorDefault = ctypes.c_void_p()
kCFRunLoopDefaultMode = ctypes.c_void_p.in_dll(_cf, 'kCFRunLoopDefaultMode')

# Setup CoreFoundation prototypes
_cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
_cf.CFStringCreateWithCString.restype = ctypes.c_void_p

_cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
_cf.CFStringGetCString.restype = ctypes.c_bool

_cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
_cf.CFNumberGetValue.restype = ctypes.c_bool

_cf.CFSetGetCount.argtypes = [ctypes.c_void_p]
_cf.CFSetGetCount.restype = ctypes.c_long

_cf.CFSetGetValues.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
_cf.CFSetGetValues.restype = None

_cf.CFRunLoopGetCurrent.restype = ctypes.c_void_p
_cf.CFRunLoopRunInMode.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_bool]
_cf.CFRunLoopRunInMode.restype = ctypes.c_int32

_cf.CFRelease.argtypes = [ctypes.c_void_p]

# Setup IOKit prototypes
_iokit.IOHIDManagerCreate.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
_iokit.IOHIDManagerCreate.restype = ctypes.c_void_p

_iokit.IOHIDManagerSetDeviceMatching.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

_iokit.IOHIDManagerOpen.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
_iokit.IOHIDManagerOpen.restype = ctypes.c_int

_iokit.IOHIDManagerClose.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
_iokit.IOHIDManagerClose.restype = ctypes.c_int

_iokit.IOHIDManagerCopyDevices.argtypes = [ctypes.c_void_p]
_iokit.IOHIDManagerCopyDevices.restype = ctypes.c_void_p

_iokit.IOHIDDeviceGetProperty.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_iokit.IOHIDDeviceGetProperty.restype = ctypes.c_void_p

_iokit.IOHIDDeviceOpen.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
_iokit.IOHIDDeviceOpen.restype = ctypes.c_int

_iokit.IOHIDDeviceClose.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
_iokit.IOHIDDeviceClose.restype = ctypes.c_int

IOHIDReportCallback = ctypes.CFUNCTYPE(
    None,
    ctypes.c_void_p,                 # context
    ctypes.c_int32,                  # result
    ctypes.c_void_p,                 # sender
    ctypes.c_uint32,                 # type
    ctypes.c_uint32,                 # reportID
    ctypes.POINTER(ctypes.c_uint8),  # report
    ctypes.c_long                    # reportLength
)

_iokit.IOHIDDeviceRegisterInputReportCallback.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_long,
    IOHIDReportCallback,
    ctypes.c_void_p
]

_iokit.IOHIDDeviceScheduleWithRunLoop.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
_iokit.IOHIDDeviceUnscheduleFromRunLoop.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]

_iokit.IOHIDDeviceSetReport.argtypes = [
    ctypes.c_void_p,
    ctypes.c_uint32,                 # reportType (1 = Output)
    ctypes.c_long,                   # reportID
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_long                    # reportLength
]
_iokit.IOHIDDeviceSetReport.restype = ctypes.c_int32


def _cfstr(s: str) -> ctypes.c_void_p:
    return _cf.CFStringCreateWithCString(kCFAllocatorDefault, s.encode('utf-8'), 0x08000100)


def _get_int_property(device: ctypes.c_void_p, key: str) -> Optional[int]:
    key_ref = _cfstr(key)
    prop = _iokit.IOHIDDeviceGetProperty(device, key_ref)
    _cf.CFRelease(key_ref)
    if not prop:
        return None
    val = ctypes.c_int32()
    if _cf.CFNumberGetValue(prop, 3, ctypes.byref(val)):
        return val.value
    return None


def _get_str_property(device: ctypes.c_void_p, key: str) -> Optional[str]:
    key_ref = _cfstr(key)
    prop = _iokit.IOHIDDeviceGetProperty(device, key_ref)
    _cf.CFRelease(key_ref)
    if not prop:
        return None
    buf = ctypes.create_string_buffer(256)
    if _cf.CFStringGetCString(prop, buf, 256, 0x08000100):
        return buf.value.decode('utf-8')
    return None


def to_bcd(val: int) -> int:
    """Convert integer to Binary Coded Decimal."""
    return ((val // 10) << 4) | (val % 10)


def from_bcd(val: int) -> int:
    """Convert Binary Coded Decimal to integer."""
    return ((val >> 4) * 10) + (val & 0x0F)


class CidooABM066:
    KNOWN_VIDS = [0x320F, 0x0C45]
    KNOWN_PIDS = [0x5055, 0x1007]
    USAGE_PAGE = 0xFF1C
    USAGE = 0x92
    REPORT_ID = 4
    REPORT_LEN = 64
    SCREEN_WIDTH = 96
    SCREEN_HEIGHT = 160
    RAW_FRAME_SIZE = SCREEN_WIDTH * SCREEN_HEIGHT * 2  # 30,720 bytes
    PADDED_FRAME_SIZE = 32768                          # 32 KB flash block per frame
    CHUNK_SIZE = 56                                    # 56 bytes payload per 64-byte packet

    def __init__(self):
        self.mgr = None
        self.device = None
        self.last_response = None
        self._callback_ref = None
        self._in_buf = None
        self._run_loop = None

    def find_and_open(self) -> bool:
        """Find the CIDOO ABM066 LCD custom HID interface and open it."""
        self.close()

        self.mgr = _iokit.IOHIDManagerCreate(kCFAllocatorDefault, 0)
        _iokit.IOHIDManagerSetDeviceMatching(self.mgr, None)
        ret = _iokit.IOHIDManagerOpen(self.mgr, 0)
        if ret != 0:
            return False

        dev_set = _iokit.IOHIDManagerCopyDevices(self.mgr)
        if not dev_set:
            return False

        count = _cf.CFSetGetCount(dev_set)
        dev_array = (ctypes.c_void_p * count)()
        _cf.CFSetGetValues(dev_set, dev_array)

        target = None
        for i in range(count):
            dev = dev_array[i]
            vid = _get_int_property(dev, 'VendorID')
            pid = _get_int_property(dev, 'ProductID')
            page = _get_int_property(dev, 'PrimaryUsagePage')
            usage = _get_int_property(dev, 'PrimaryUsage')
            prod = _get_str_property(dev, 'Product') or ''

            # Match either by known VID/PID & usage, or by product name containing CIDOO & usage
            is_match = (
                (vid in self.KNOWN_VIDS and pid in self.KNOWN_PIDS and page == self.USAGE_PAGE and usage == self.USAGE) or
                ('CIDOO' in prod.upper() and page == self.USAGE_PAGE and usage == self.USAGE)
            )
            if is_match:
                target = dev
                break

        _cf.CFRelease(dev_set)

        if not target:
            return False

        ret = _iokit.IOHIDDeviceOpen(target, 0)
        if ret != 0:
            return False

        self.device = target

        # Register input report callback to capture device responses
        def _on_report(context, result, sender, rtype, reportID, report, reportLength):
            self.last_response = bytes(report[:reportLength])

        self._callback_ref = IOHIDReportCallback(_on_report)
        self._in_buf = (ctypes.c_uint8 * self.REPORT_LEN)()
        _iokit.IOHIDDeviceRegisterInputReportCallback(self.device, self._in_buf, self.REPORT_LEN, self._callback_ref, None)

        self._run_loop = _cf.CFRunLoopGetCurrent()
        _iokit.IOHIDDeviceScheduleWithRunLoop(self.device, self._run_loop, kCFRunLoopDefaultMode)

        # Briefly pump runloop to flush any pending reports
        for _ in range(5):
            _cf.CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.01, False)

        return True

    def close(self):
        """Close device and release HID manager."""
        if self.device and self._run_loop:
            _iokit.IOHIDDeviceUnscheduleFromRunLoop(self.device, self._run_loop, kCFRunLoopDefaultMode)
            _iokit.IOHIDDeviceClose(self.device, 0)
            self.device = None
        if self.mgr:
            _iokit.IOHIDManagerClose(self.mgr, 0)
            _cf.CFRelease(self.mgr)
            self.mgr = None
        self._callback_ref = None
        self._in_buf = None
        self._run_loop = None

    def send_packet(self, pkt: bytearray, timeout: float = 1.0, retries: int = 3) -> Optional[bytes]:
        """Send a 64-byte HID output report and wait for response with automatic retry."""
        if not self.device:
            raise RuntimeError("Device not opened")

        # Ensure packet is 64 bytes
        if len(pkt) < self.REPORT_LEN:
            pkt.extend(b'\x00' * (self.REPORT_LEN - len(pkt)))
        elif len(pkt) > self.REPORT_LEN:
            pkt = pkt[:self.REPORT_LEN]

        # Calculate checksum: sum(pkt[3:64]) & 0xFFFF
        chk = sum(pkt[3:]) & 0xFFFF
        pkt[1] = chk & 0xFF
        pkt[2] = (chk >> 8) & 0xFF

        cmd_id = pkt[3]

        for attempt in range(max(1, retries)):
            # Drain any residual/stale reports before sending
            for _ in range(3):
                self.last_response = None
                _cf.CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.001, False)
                if self.last_response is None:
                    break

            self.last_response = None
            out_buf = (ctypes.c_uint8 * self.REPORT_LEN)(*pkt)
            ret = _iokit.IOHIDDeviceSetReport(self.device, 1, self.REPORT_ID, out_buf, self.REPORT_LEN)
            if ret != 0:
                raise RuntimeError(f"IOHIDDeviceSetReport failed: 0x{ret:x}")

            start = time.time()
            while time.time() - start < timeout:
                _cf.CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.001, False)
                if self.last_response is not None:
                    # Validate that response corresponds to the sent command
                    if len(self.last_response) >= 4 and self.last_response[3] == cmd_id:
                        return self.last_response
                    if cmd_id == 0x21 and len(self.last_response) >= 4 and self.last_response[3] in (0x21, 0x00):
                        return self.last_response
                    # If device responded with AA (busy/error), wait slightly and continue loop
                    self.last_response = None

            time.sleep(0.05)

        return self.last_response

    def read_config(self, slot: int = 0) -> bytearray:
        """
        Read the 48-byte screen configuration block.
        slot: 0 for Custom 1, 1 for Custom 2.
        Uses Command 0x05 (read).
        """
        start_offset = slot * 0x80
        config = bytearray(48)

        for off in range(0, 48, 4):
            pkt = bytearray(self.REPORT_LEN)
            pkt[0] = self.REPORT_ID
            pkt[3] = 0x05
            pkt[4] = 0x04  # 4 bytes per read
            target_off = start_offset + off
            pkt[5] = target_off & 0xFF
            pkt[6] = (target_off >> 8) & 0xFF
            pkt[7] = 0x00

            resp = self.send_packet(pkt)
            if not resp or len(resp) < 8 or resp[3] != 0x05:
                raise RuntimeError(f"Failed to read config at offset {target_off}: resp={resp.hex() if resp else None}")
            config[off : off + 4] = resp[4:8]

        return config

    def write_config(self, config: bytearray, slot: int = 0) -> bool:
        """
        Write the 48-byte screen configuration block.
        slot: 0 for Custom 1, 1 for Custom 2.
        Uses Command 0x06 (write).
        """
        if len(config) != 48:
            raise ValueError(f"Config must be 48 bytes, got {len(config)}")

        start_offset = slot * 0x80
        pkt = bytearray(self.REPORT_LEN)
        pkt[0] = self.REPORT_ID
        pkt[3] = 0x06
        pkt[4] = 48  # chunk length = 48
        pkt[5] = start_offset & 0xFF
        pkt[6] = (start_offset >> 8) & 0xFF
        pkt[7] = 0x00
        pkt[8 : 8 + 48] = config

        resp = self.send_packet(pkt)
        if not resp or len(resp) < 4 or resp[3] != 0x06:
            raise RuntimeError(f"Failed to write config: resp={resp.hex() if resp else None}")
        return True

    def sync_time(self, slot: int = 0) -> datetime.datetime:
        """
        Synchronize keyboard LCD clock to current Mac local time.
        """
        config = self.read_config(slot)
        now = datetime.datetime.now()

        config[35] = to_bcd(now.second)
        config[36] = to_bcd(now.minute)
        config[37] = to_bcd(now.hour)
        # Windows CTime Day of Week: 1=Sun, 2=Mon...7=Sat
        w = (now.weekday() + 2) % 7
        if w == 0:
            w = 7
        config[38] = w
        config[39] = to_bcd(now.day)
        config[40] = to_bcd(now.month)
        config[41] = to_bcd(now.year % 100)

        self.write_config(config, slot)
        return now

    def upload_frames(
        self,
        frames: List[bytes],
        slot: int = 1,
        interval_ms: int = 40,
        progress_cb: Optional[Callable[[int, int, str], None]] = None
    ) -> bool:
        """
        Upload one or more 96x160 RGB565 frames to keyboard LCD flash memory.
        frames: list of bytes objects, each 30,720 bytes (96*160*2 in RGB565 Big Endian).
        slot: 1 for Custom 1, 2 for Custom 2.
        interval_ms: frame delay in milliseconds (e.g. 25, 40, 50, 60, 100).
        progress_cb: optional callback(bytes_sent, total_bytes, message).
        """
        if not frames:
            raise ValueError("No frames provided")

        frame_count = len(frames)
        for i, f in enumerate(frames):
            if len(f) != self.RAW_FRAME_SIZE:
                raise ValueError(f"Frame {i} size {len(f)} does not match 96x160 RGB565 ({self.RAW_FRAME_SIZE} bytes)")

        # Prepare flash stream: each frame padded to 32,768 bytes (32 KB flash block)
        full_buffer = bytearray()
        for f in frames:
            full_buffer.extend(f)
            # Pad to 65,536 bytes
            padding = self.PADDED_FRAME_SIZE - len(f)
            full_buffer.extend(b'\x00' * padding)

        total_bytes = len(full_buffer)

        # Step 1: Command 0x23 (Start screen upload / Erase)
        if progress_cb:
            progress_cb(0, total_bytes, "Starting custom screen mode...")
        resp = None
        for attempt in range(5):
            pkt = bytearray(self.REPORT_LEN)
            pkt[0] = self.REPORT_ID
            pkt[3] = 0x23
            resp = self.send_packet(pkt, timeout=2.0, retries=3)
            if resp and resp[3] == 0x23:
                break
            time.sleep(0.4)

        if not resp or resp[3] != 0x23:
            raise RuntimeError(f"Start upload (0x23) failed: resp={resp.hex() if resp else None}")

        # Step 2: Command 0x01 (Prepare / Reset)
        if progress_cb:
            progress_cb(0, total_bytes, "Preparing device flash...")
        pkt = bytearray(self.REPORT_LEN)
        pkt[0] = self.REPORT_ID
        pkt[3] = 0x01
        resp = self.send_packet(pkt, timeout=2.5, retries=5)
        if not resp or resp[3] != 0x01:
            raise RuntimeError(f"Prepare upload (0x01) failed: resp={resp.hex() if resp else None}")

        # Step 3: Stream chunks with Command 0x21
        sent_bytes = 0
        chunk_size = self.CHUNK_SIZE  # 56 bytes

        while sent_bytes < total_bytes:
            remaining = total_bytes - sent_bytes
            this_chunk_len = min(chunk_size, remaining)

            pkt = bytearray(self.REPORT_LEN)
            pkt[0] = self.REPORT_ID
            pkt[3] = 0x21
            pkt[4] = this_chunk_len
            pkt[5] = sent_bytes & 0xFF
            pkt[6] = (sent_bytes >> 8) & 0xFF
            pkt[7] = (sent_bytes >> 16) & 0xFF
            pkt[8 : 8 + this_chunk_len] = full_buffer[sent_bytes : sent_bytes + this_chunk_len]

            resp = self.send_packet(pkt, timeout=1.0)
            if not resp or resp[3] != 0x21:
                raise RuntimeError(f"Chunk transfer (0x21) failed at offset {sent_bytes}: resp={resp.hex() if resp else None}")

            if len(resp) >= 8 and (resp[7] == 0xFF or resp[7] == 0xFE):
                raise RuntimeError(f"Flash write error at offset {sent_bytes}: {resp.hex()}")

            # Hardware requirement: 500ms delay after the very first chunk at offset 0
            if sent_bytes == 0:
                time.sleep(0.5)

            sent_bytes += this_chunk_len

            if progress_cb and (sent_bytes % (chunk_size * 20) == 0 or sent_bytes == total_bytes):
                progress_cb(sent_bytes, total_bytes, f"Writing frames: {sent_bytes}/{total_bytes} bytes ({sent_bytes*100//total_bytes}%)")

        # Step 4: Command 0x02 (Finish / Commit)
        if progress_cb:
            progress_cb(total_bytes, total_bytes, "Finalizing transfer...")
        time.sleep(0.02)
        pkt = bytearray(self.REPORT_LEN)
        pkt[0] = self.REPORT_ID
        pkt[3] = 0x02
        resp = self.send_packet(pkt, timeout=1.0)
        if not resp or resp[3] != 0x02:
            raise RuntimeError(f"Finalize upload (0x02) failed: resp={resp.hex() if resp else None}")

        # Step 5: Update config (slot, frame_count, interval, and time sync)
        if progress_cb:
            progress_cb(total_bytes, total_bytes, "Updating keyboard screen configuration...")

        config = self.read_config(0)

        # Set slot and frame count
        config[33] = slot            # Slot number: 1 or 2
        config[34] = frame_count     # Total frames
        config[46] = min(255, max(1, interval_ms))  # Frame interval ms

        # Sync local time
        now = datetime.datetime.now()
        config[35] = to_bcd(now.second)
        config[36] = to_bcd(now.minute)
        config[37] = to_bcd(now.hour)
        w = (now.weekday() + 2) % 7
        if w == 0:
            w = 7
        config[38] = w
        config[39] = to_bcd(now.day)
        config[40] = to_bcd(now.month)
        config[41] = to_bcd(now.year % 100)

        self.write_config(config, 0)

        if progress_cb:
            progress_cb(total_bytes, total_bytes, "Upload completed successfully!")

        return True


def rgb_to_rgb565_be(r: int, g: int, b: int) -> bytes:
    """Convert 8-bit RGB components to 2-byte Big Endian RGB565."""
    val = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    return bytes([(val >> 8) & 0xFF, val & 0xFF])


def rgba_pixels_to_rgb565(rgba_bytes: bytes, width: int = 96, height: int = 160) -> bytes:
    """
    Convert RGBA buffer (width*height*4 bytes, row-major) into RGB565 big endian (width*height*2 bytes).
    The CIDOO ABM066 LCD controller scans along the vertical axis (160 scanlines of 96 columns),
    requiring hardware buffer indexing: (x * height + y) * 2.
    """
    expected = width * height * 4
    if len(rgba_bytes) < expected:
        raise ValueError(f"Expected at least {expected} RGBA bytes, got {len(rgba_bytes)}")

    out = bytearray(width * height * 2)

    for y in range(height):
        for x in range(width):
            in_idx = (y * width + x) * 4
            r = rgba_bytes[in_idx]
            g = rgba_bytes[in_idx + 1]
            b = rgba_bytes[in_idx + 2]
            # 16-bit Big Endian RGB565: RRRRRGGG GGGBBBBB
            val = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            # Hardware column-major address: Column x (0..95), Row y (0..159)
            out_idx = (x * height + y) * 2
            out[out_idx] = (val >> 8) & 0xFF
            out[out_idx + 1] = val & 0xFF

    return bytes(out)
