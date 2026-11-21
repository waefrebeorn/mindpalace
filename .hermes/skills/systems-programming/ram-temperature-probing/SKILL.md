---
name: ram-temperature-probing
description: Read DRAM/SPD temperature like HWiNFO; not ACPI.
---

# RAM temperature like HWiNFO

Use when asked to expose memory temperature, reconcile HWiNFO's "RAM" reading with Linux sensors, or decide whether an ACPI thermal zone is a DRAM sensor.

## What HWiNFO actually reads
- DDR5: the SPD hub's own thermal sensor, not the DRAM cells. HWiNFO labels it "SPD Hub Temperature"; its author says this is one chip (the SPD hub) on the DIMM, near the PMIC. Treat it as DIMM/PCB temperature.
- DDR4: consumer non-ECC DIMMs usually have no standard thermal sensor; ECC/RDIMM/NVDIMM may. HWiNFO may instead show CPU IMC/chipset-derived values. Fail closed rather than relabeling IMC as DRAM.
- AMD: k10temp/k10expose may expose SoC/IMC-ish temperatures via SMU, but there is no cross-vendor sysfs `ram_temp`.
- Intel: coretemp/x86_pkg_temp are CPU package/core sensors; DDR5 SPD temperature comes from SMBus via the IMC, not from coretemp.

## DDR5 SPD read path (root required)
- SPD hub base I²C address: `0x50 + slot` (0x50..0x57).
- Device-id registers 0x00..0x01: `0x5118` means SPD5 hub with thermal sensor.
- Temperature: MR49/MR50 = registers 0x31/0x32, 16-bit little-endian. MR36 = 0x24 holds resolution bits; common values give 0.25 C or 0.5 C per LSB.
- Decode using MR36[1:0]: shifts `{3,2,1,0}`, sign bits `{0x200,0x400,0x800,0x1000}`, LSB milli-Celsius x2 `{1000,500,250,125}` (divide product by 2). Example raw `0x0154` decodes to 21 C at both 0.5 and 0.25 C/LSB; use exact fractions, not 63 mC for 0.0625 C.
- Linux options: `i2c-tools` (`i2cdetect`, `decode-dimms`) plus the `spd5118`/`eeprom` kernel driver; or open `/dev/i2c-N` with `i2c-dev` and do SMBus byte/word reads directly. `/dev/i2c-*` is normally root-only.
- Always identify the source in UI/logs: `spd5-hub:slot0`, `imc`, `acpitz` — never a bare "RAM" if the sensor is not DRAM.

## ACPI is not RAM temperature
- `acpitz` (`/sys/class/thermal/thermal_zone*/type=acpitz`) is a platform/EC thermal zone, often an aggregate or worst-case point, with policy/trip points. It may read a few degrees above CPU core sensors; that is normal and does not mean RAM is hotter.
- On the WuBu rebuild box (2026-11-21): `acpitz=41 C`, `x86_pkg_temp/coretemp=39 C`, `TCPU=39.05 C`, NVMe=34.9 C, WiFi=31 C. No SPD devices bound, no RAM temp in sysfs. `acpitz` had a single `critical=100 C` trip under `user_space` policy.
- Laptop DSDTs often expose vendor zones (`INT3400`, `TCPU`, `SEN4`) with raw/unscaled values; do not treat their names as physical sensor identities without a driver that knows the scaling.

## WuBuOS integration rule
- Keep `WUBU_RAM_TEMP_SYSFS` as an explicit override, but add a real SPD5 reader behind it: probe `/dev/i2c-*`, read `0x50+slot` id `0x5118`, decode MR49/MR50 using MR36, label as `spd5-hub:slotN`, and fail closed if no sensor/permission.
- Never substitute `acpitz` for RAM. If only ACPI is available, show it separately with its own label.

## Pitfalls
- DDR5 SPD registers are memory-mapped into the hub's register space; a plain DDR4 SPD EEPROM dump at `0x50` will not contain the temperature at the same offsets.
- `/dev/i2c-*` is root-only; `sudo -n` may be unavailable. The WuBuOS reader reports -1 in that case. A decoder vector gate proves the math, but a live hardware reading needs an authorized root run.
- HWiNFO's DIMM temperature can exceed package sensor readings because the SPD hub/PMIC is on the DIMM PCB; that is not evidence of DRAM die temperature.
