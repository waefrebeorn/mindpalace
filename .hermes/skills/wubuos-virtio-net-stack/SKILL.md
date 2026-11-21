---
name: wubuos-virtio-net-stack
description: Use when extending WuBuOS virtio-net or 9P-over-UDP.
---

# WuBuOS L5 virtio-net + minimal netstack — ownership and gates

## One owner: the vring core
`src/kernel/wubu_virtqueue.c/.h` owns ALL legacy split-virtqueue
machinery (layout, page-aligned DMA ring alloc, desc chains, avail/used
publish, doorbell, polled completion) for every legacy virtio device.
Device drivers (wubu_virtio_blk.c, wubu_virtio_net.c) keep only
device-specific config + request encoding. Never copy ring code into a
new driver — extend the core. Injectable seams: `wubu_vq_io` (port
hooks) and `wubu_vq_mem` (DMA allocator); hosted tests include the core
.c TU and install a fake window + low static arena (`-no-pie`, legacy
queue PFN is 32-bit).

## Netstack facts (wubu_netstack.c/.h)
- Static slirp defaults: 10.0.2.15/24, gw 10.0.2.2; IPs are host-order
  uint32_t (WUBU_NET_IP4), wire big-endian. Source UDP port 9000.
- API: wubu_net_udp_send / wubu_net_poll(cb,ctx) / wubu_net_ping /
  wubu_net_arp_resolve; wubu_net_selftest() is the boot gate hook.
- Gate port is FIXED (WUBU_NET_GATE_PORT 39001) because the metal kernel
  has no cmdline channel (crt0 does not plumb -append); the gate script
  binds the same constant on host loopback — slirp forwards guest UDP
  to 10.0.2.2:P to 127.0.0.1:P.
- QEMU legacy net: `-netdev user,id=u0 -device
  virtio-net-pci,netdev=u0,disable-modern=on`; device ID 0x1000 class
  0x02 (blk is class 0x01 — class disambiguates). Negotiate only MAC
  (bit 5): no offloads, 10-byte legacy hdr. RX q0 posted buffers, TX q1.
  Slirp answers ARP + ICMP echo for the gateway (verified QEMU 8.2.2).

## Pitfalls (each cost a debug cycle)
- UDP checksum: the "computed 0 -> send 0xFFFF" rule belongs to the
  SENDER only. Applying it inside the shared compute/verify function
  makes verification of a valid datagram return 0xFFFF instead of 0 and
  silently drops every checksummed RX packet. Keep raw ~sum; map at
  the write site.
- Symbol collision: the driver-zoo detection stub wubu_drv_virtio.c
  already defines `wubu_virtio_net_mac(void)` (returns a pointer). The
  real driver's accessor is `wubu_virtio_net_get_mac(n, out)`. Grep the
  zoo for a name before exporting it from a new kernel leaf.
- Unit-test fakes must match renamed signatures exactly (a space before
  '(' defeats naive string-rename sweeps; link error, not compile).
- Kernel BSS/stack are higher-half VAs — NOT DMA-able. Build frames on
  the stack only because the NIC driver bounces TX through heap and
  copies RX out; heap (phys 0x400000) is the identity-mapped DMA window.

## Gates (behavior or it didn't happen)
- `make test_virtio_blk` / `test_virtio_net` / `test_netstack` (fake
  window / fake dual-queue device / fake NIC + crafted frames; checksum
  anchors: IPv4 0xb861, UDP 0x9299, ICMP 0x8e81 — python-computed).
- `make virtio-net-gate` (tools/virtio_net_gate.py): asserts BOTH the
  serial 'NET-OK: udp round-trip <n> bytes' AND that the host echo
  server received the exact 64-byte marker (i*13+7).
- Refactor regressions: test_virtio_blk + `make virtio-persist-gate`.
- Always: `make kernel-strict` 0 errors + `python3
  tools/ci_boot_assert.py src/kernel/kernel.elf --kernel`; default boot
  must contain ZERO network lines when no virtio-net device is present.
