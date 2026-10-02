#!/usr/bin/env python3
"""Read DPCD registers from a DisplayPort / eDP AUX device.

Reads via /dev/drm_dp_auxN using lseek(addr) + read(), i.e. native AUX
transactions.  Do NOT use the i2c "AUX x/DDI x" adapters for this: those
have DDC/EDID semantics and will hand you EDID bytes, not DPCD registers.

Requires root -- use sudo, or pkexec for a GUI password prompt.

Examples:
    sudo ./dpcd_read.py                        # backlight-related preset
    sudo ./dpcd_read.py -d /dev/drm_dp_aux1    # preset on another AUX device
    sudo ./dpcd_read.py 0x700 0x701:4 0x721    # arbitrary addr[:len]

Written for debugging OLED backlight on ASUS laptops under Linux:
https://github.com/Tensor-0/asus-oled-brightness
"""

import argparse
import os
import sys

# eDP backlight / IHDR registers worth looking at when brightness is broken.
PRESET = [
    (0x340, 4, "IHDR caps -- expect '01 77 01' (TCON v1, BRIGHTNESS_NITS_CAP, SDR_uses_AUX)"),
    (0x344, 1, ""),
    (0x354, 4, ""),
    (0x700, 4, "VESA eDP revision (0x05 = eDP 1.4b)"),
    (0x701, 4, "VESA backlight caps"),
    (0x720, 4, "VESA backlight mode set"),
]


def parse_addr(spec):
    addr, _, length = spec.partition(":")
    return int(addr, 0), int(length or "16", 0)


def decode(addr, data):
    """Human-readable meaning for the registers we know."""
    if addr == 0x344 and data:
        return "IHDR backlight " + ("ENABLED (bit4)" if data[0] & 0x10 else "not enabled")
    if addr == 0x354 and len(data) >= 2:
        return "brightness = %d nits" % int.from_bytes(data[:2], "little")
    return ""


def main():
    ap = argparse.ArgumentParser(
        description="Read DPCD registers via native AUX (/dev/drm_dp_auxN).",
        epilog="With no addresses, reads the eDP backlight preset. "
               "Addresses: 0x hex, optional :length (default 16).",
    )
    ap.add_argument("-d", "--dev", default="/dev/drm_dp_aux0",
                    help="AUX device, default /dev/drm_dp_aux0 "
                         "(list with: ls /dev/drm_dp_aux*)")
    ap.add_argument("addrs", nargs="*", help="address[:length] ...")
    args = ap.parse_args()

    if args.addrs:
        regs = [(a, n, "") for a, n in map(parse_addr, args.addrs)]
    else:
        regs = PRESET

    try:
        fd = os.open(args.dev, os.O_RDWR)
    except FileNotFoundError:
        sys.exit("%s: not found -- list devices with: ls /dev/drm_dp_aux*" % args.dev)
    except PermissionError:
        sys.exit("%s: permission denied -- run as root (sudo, or pkexec for a GUI prompt)"
                 % args.dev)

    print("== %s" % args.dev)
    rc = 0
    for addr, length, note in regs:
        try:
            os.lseek(fd, addr, os.SEEK_SET)
            data = os.read(fd, length)
        except OSError as e:
            print("0x%03x (%dB): ERROR: %s" % (addr, length, e))
            rc = 1
            continue
        line = "0x%03x (%dB): %s" % (addr, length, data.hex(" "))
        meaning = decode(addr, data)
        if meaning:
            line += "  [%s]" % meaning
        if note:
            line += "  # %s" % note
        print(line)
    os.close(fd)
    sys.exit(rc)


if __name__ == "__main__":
    main()
