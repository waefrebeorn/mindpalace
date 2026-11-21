# EDID and GOP wire formats (condensed)

Verified against uefi.org UEFI 2.10/2.11 section 12.9 and against a real 128-byte EDID
captured from the dev machine's eDP panel.

## EDID base block (128 bytes, little-endian)

| Offset | Size | Field |
|---|---|---|
| 0 | 8 | header `00 FF FF FF FF FF FF 00` |
| 8 | 2 | manufacturer ID: three 5-bit letters, big-endian packed (`((v>>10)&0x1F)+'A'-1`) |
| 10 | 2 | product code (LE) |
| 12 | 4 | serial (LE) |
| 16 | 1 | manufacture week (0 = unspecified) |
| 17 | 1 | year - 1990 |
| 18 | 1 | EDID version -- only 1.x has this layout |
| 19 | 1 | revision |
| 21 | 1 | max horizontal image size in CM (0 = unknown; multiply by 10 for mm) |
| 22 | 1 | max vertical image size in CM |
| 54/72/90/108 | 18 each | descriptor slots |
| 126 | 1 | extension count |
| 127 | 1 | checksum: sum of all 128 bytes mod 256 == 0 |

Refuse unless header matches, version is 1, and the checksum validates. A corrupt blob
must never be reported as a real monitor.

### Descriptor slot layout (18 bytes)

```
[0..2]  00 00 00        must be zero
[3]     type: FC = monitor name, FF = serial string, FE = unspecified text,
              FD = range limits, FB = colour point
[4]     reserved (00)
[5..17] ASCII text, terminated by 0A
```

### Detailed timing descriptor 1 (bytes 54..71) -- THE PACKING TRAP

```
 0..1  pixel clock in 10 kHz units (LE)
 2     h_active low 8 bits
 3     h_blank  low 8 bits
 4     h_active high 2 bits (0xF0) | h_blank high 2 bits (0x0F)   <-- SHARED BYTE
 5     v_active low 8 bits
 6     v_blank  low 8 bits
 7     v_active high 2 bits (0xF0) | v_blank high 2 bits (0x0F)   <-- SHARED BYTE
 8..17 timing parameters (front/back porch, sync, size)
```

```c
h_active = t[2] | (((unsigned)t[4] & 0xF0) << 4);
h_blank  = t[3] | (((unsigned)t[4] & 0x0F) << 8);
v_active = t[5] | (((unsigned)t[7] & 0xF0) << 4);
v_blank  = t[6] | (((unsigned)t[7] & 0x0F) << 8);
refresh_hz = (clock10k * 10000.0) / ((h_active+h_blank) * (v_active+v_blank));
```

Verified example: a real eDP panel decodes to `CMN N156HRA-EA1`, 340x190 mm
(the kernel separately reports 344x194 mm -- EDID stores whole centimetres), preferred
timing 1920x1080 @ 144 Hz.

## EFI_GRAPHICS_OUTPUT_MODE_INFORMATION (UEFI GOP)

Already defined in `src/firmware/efi.h`; include it, do not restate it. Layout:

```
offset  0  UINT32 Version                       must be 0
offset  4  UINT32 HorizontalResolution
offset  8  UINT32 VerticalResolution
offset 12  EFI_GRAPHICS_PIXEL_FORMAT PixelFormat
offset 16  UINT32 RedMask       \ EFI_PIXEL_BITMASK,
offset 20  UINT32 GreenMask      | valid ONLY when PixelFormat == PixelBitMask
offset 24  UINT32 BlueMask       |
offset 28  UINT32 ReservedMask  /
offset 32  UINT32 PixelsPerScanLine           the REAL stride, may exceed the width
```

Total 36 bytes. `_Static_assert(sizeof(...) == 36, ...)` catches drift at build time.

Pixel format enum (from `efi.h`): 0 RGBReserved8, 1 BGRReserved8, 2 BitMask,
3 BltOnly (NO linear framebuffer), 4 FormatMax. Refuse format >= FormatMax.

`EFI_GRAPHICS_OUTPUT_PROTOCOL_MODE` = `{UINT32 MaxMode; UINT32 Mode;
INFO *Info; UINTN SizeOfInfo; PHYS_ADDRESS FrameBufferBase; UINTN FrameBufferSize;}`.
Reading it requires locating GOP via the EFI system table -- firmware environment only,
not verifiable from a Linux userspace process.

## `xrandr -q --props` structure (the fallback source)

```
Screen 0: minimum ... current ... maximum ...        <- header, ignore
<name> connected primary (normal ...)               <- column 0 => new connector
	EDID:                                          <- one leading tab
		<32 hex chars><32 hex chars>                <- TWO leading tabs => 16 EDID bytes
	1920x1080  144.00 +  60.02                      <- one tab + digits; NOT hex data
	SOME_OTHER_PROP: value                          <- one tab => terminates the block
```

Identify EDID data lines by TWO leading tabs plus hex-and-whitespace only. Read ahead
only within a buffer you keep: consuming the line that terminates the block can swallow
the NEXT CONNECTOR.

## Connector naming across sources

KMS gives `connector_type` + `connector_type_id`; map back to what users recognise
(eDP, HDMI-A, HDMI-B, DP, DVI-I/D/A, VGA, LVDS, DSI, CVBS) so all three sources can be
compared. Strip a leading `<card>-` prefix from sysfs directory names, keeping the raw
name too -- keying logic off the full name is brittle.
