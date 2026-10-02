# asus-oled-brightness

**中文摘要**：ASUS ROG OLED 笔记本（GU605MV，三星 ATNA60DL01-0 面板）在 Linux **混合显卡模式**下屏幕亮度不可调、低亮度频闪严重。根因：i915 因面板 EDID 缺 HDR 元数据而放弃面板的 IHDR 背光接口，落到一条坏路径上。内核参数 **`i915.enable_dpcd_backlight=3`** 强制走 IHDR 后，全量程可调、最低亮度无频闪。本仓库 = 修复说明 + `dpcd_read.py`（读 eDP DPCD 寄存器的小工具，用于验证）。

**TL;DR** — On ASUS ROG OLED laptops under Linux hybrid graphics, screen brightness is uncontrollable because i915 rejects the panel's IHDR backlight interface (EDID lacks HDR static metadata). Force it with the kernel parameter `i915.enable_dpcd_backlight=3`.

```bash
# /etc/default/grub
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash i915.enable_dpcd_backlight=3"
sudo update-grub && sudo reboot
```

## Problem

Tested on an ASUS ROG Zephyrus G16 **GU605MV** (Samsung **ATNA60DL01-0** OLED, 2560x1600 @ 240 Hz) running Ubuntu 22.04 / kernel 6.8.

With hybrid graphics (`gpu_mux_mode=1`, internal panel driven by the Intel iGPU):

- Fn brightness keys and the GNOME slider move, sysfs values change -- **the panel ignores them**.
- The panel can get stuck near 1% brightness with heavy flicker.
- Windows works fine (it uses the ACPI `_BCM` path).

## Root cause

The kernel log says it outright:

```
i915 ...: Panel is missing HDR static metadata. ... If your backlight
controls don't work try booting with i915.enable_dpcd_backlight=3
```

The panel **is** IHDR-capable -- DPCD `0x340-0x342` reads `01 77 01`
(TCON v1, `BRIGHTNESS_NITS_CAP`, `SDR_uses_AUX`) -- and it does honor IHDR
writes (verified by hand: 4-byte nits to `0x354`, then enable bit 4 of
`0x344`). But i915's capability check refuses the panel because its EDID
lacks CTA-861 HDR static metadata (the brightness data lives in a DisplayID
block instead). The panel ends up on the old, broken path.

### Dead ends (don't bother)

| Path | Result |
|---|---|
| `acpi_backlight=video` (ACPI `_BCM`/`_BQC`) | writes accepted, values read back, **panel ignores** |
| `nvidia_wmi_ec_backlight` (forced load) | same -- silent no-op |
| old intel PWM path | broken in hybrid mode; DPCD `0x721` shows preset-mode |

## The fix

`i915.enable_dpcd_backlight` semantics: `0` = disable, `1` = enable with
capability check (default), `2` = force VESA interface, `3` = **force Intel
HDR (IHDR) interface**. Option `3` skips the metadata check that is failing.

Add to the kernel command line (e.g. `/etc/default/grub`
`GRUB_CMDLINE_LINUX_DEFAULT`), run `sudo update-grub`, reboot.

### Verify it worked

- `/sys/class/backlight/intel_backlight` exists and `max_brightness` is `512`
  (the IHDR path; the old path exposed a different range).
- DPCD `0x344` bit 4 is set and `0x354` tracks the sysfs brightness 1:1:

```console
$ sudo ./dpcd_read.py
== /dev/drm_dp_aux0
0x340 (4B): 01 77 01 00  # IHDR caps -- expect '01 77 01' ...
0x344 (1B): 10  [IHDR backlight ENABLED (bit4)]
0x354 (4B): 7a 01 00 00  [brightness = 378 nits]
...
```

- Fn keys / slider now visibly change the panel; no flicker at minimum
  brightness (nits-based DC dimming, not PWM).

## dpcd_read.py

Tiny dependency-free reader for DPCD registers over native AUX.

```console
# backlight preset (IHDR caps / enable / nits + VESA registers)
sudo ./dpcd_read.py

# another AUX device
sudo ./dpcd_read.py -d /dev/drm_dp_aux1

# arbitrary addresses, addr[:len]
sudo ./dpcd_read.py 0x700 0x701:4 0x721
```

Notes:

- Must run as root. `pkexec ./dpcd_read.py` gives a GUI password prompt
  (handy over SSH-less desktop sessions).
- `/dev/drm_dp_aux*` are native AUX transactions (`lseek` + `read`). The i2c
  `AUX x/DDI x` adapters are DDC/EDID semantics -- they will **not** return
  DPCD registers.
- On Intel hybrid graphics the internal eDP panel is usually
  `/dev/drm_dp_aux0`; if the output looks wrong, try the other indices.

## Register cheat sheet

| Address | Meaning |
|---|---|
| `0x340-0x342` | IHDR caps: `01 77 01` = TCON v1 + nits cap + SDR via AUX |
| `0x344` bit 4 | IHDR backlight enable |
| `0x354-0x357` | IHDR brightness, 16-bit little-endian nits |
| `0x700` | eDP revision (`0x05` = eDP 1.4b) |
| `0x701` | VESA backlight caps (bit 2 = AUX enable cap; may be 0) |
| `0x720-0x723` | VESA backlight mode set / 16-bit brightness |

## Related

- asusctl [#352](https://github.com/OpenGamingCollective/asusctl/issues/352) --
  the same silent no-op signature (writes accepted, no error, panel ignores)
  in the *opposite* MUX mode: dGPU drives the panel and the firmware's ACPI
  `_BCM` stub turns out to be **an empty function**. Cross-check for our
  `acpi_backlight=video` dead end: on this firmware family, "value accepted"
  proves nothing.

## Tested on

- ASUS ROG Zephyrus G16 GU605MV, Samsung ATNA60DL01-0 OLED
- Ubuntu 22.04, kernel 6.8.0-138, hybrid graphics (`gpu_mux_mode=1`)

## License

MIT
