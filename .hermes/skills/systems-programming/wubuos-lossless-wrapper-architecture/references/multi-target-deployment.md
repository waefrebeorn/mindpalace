# WuBuOS Multi-Target Deployment (Phase 4)

Documentation of the deployment subsystem created in Phase 4 Item 1 for building WuBuOS for 4 targets:
- Bare metal (ISO with limine bootloader)
- WSL2 (tar.gz distro package)
- OCI/Docker (container image)
- macOS AVF (Virtualization.framework app bundle)

## Overview

The `wubu_deploy` subsystem provides a unified C API for building WuBuOS for different deployment targets. All targets share a common rootfs creation function and produce a single binary (`wubu`).

### Files
- `src/gui/wubu_deploy.h` — Public API with configs for all 4 targets
- `src/gui/wubu_deploy.c` — Implementation (rootfs, limine.conf, wsl.conf, Dockerfile, macOS Swift launcher)
- `src/gui/wubu_deploy_test.c` — 9 unit tests covering all targets

### Key Design Decisions
1. **Rootfs is shared** — All targets use `wubu_deploy_create_rootfs()` to create a minimal Linux rootfs
2. **Theme-agnostic kernel** — VBE layer has no theme knowledge; colors passed from GUI at render time
3. **Single binary** — One `wubu` binary works across all targets (headless, Wayland, or VM)
4. **No external deps** — Uses system tools (mkinitcpio, cpio, tar, docker, xcodebuild) at build time

## Target Details

### 1. Bare Metal (`wubu_deploy_baremetal`)

**Inputs**: `wubu_baremetal_config_t`
- `kernel_path` — Linux kernel (bzImage)
- `initramfs_path` — Output initramfs path
- `limine_cfg_path` — Limine config path
- `output_iso` — Final ISO path
- `wubu_binary` — Path to built binary
- `rootfs_dir` — Staging directory
- `include_firmware`, `include_drivers` — Kernel modules
- `kernel_cmdline` — Kernel parameters

**Process**:
1. Create rootfs with busybox layout + wubu binary + init script
2. Generate `limine.conf` with kernel cmdline
3. Copy kernel + limine.conf to rootfs/boot/
4. Create initramfs via `cpio + gzip`
5. Build ISO using `xorriso` + `limine bios-install`

**Output**: `wubuos-baremetal.iso` (bootable on real hardware or QEMU)

**Boot flow**: limine → kernel → initramfs → `/init` → `/usr/bin/wubu -w 1024 768`

### 2. WSL2 (`wubu_deploy_wsl2`)

**Inputs**: `wubu_wsl2_config_t`
- `distro_name` — e.g., "WuBuOS"
- `rootfs_path` — Staging directory
- `output_tar` — `.tar.gz` output
- `wubu_binary` — Path to built binary
- `default_user` — Default username
- `systemd` — Enable systemd (WSL2 feature)
- `wsl_conf` — Custom wsl.conf (or auto-generated)

**Process**:
1. Create rootfs (same as bare metal)
2. Generate `/etc/wsl.conf` with systemd, automount, network, interop
3. Create `tar.gz` with `--numeric-owner`

**Output**: `wubuos-wsl2.tar.gz`

**Install**: `wsl --import WuBuOS <path> wubuos-wsl2.tar.gz --version 2`

**Key wsl.conf settings**:
```ini
[boot]
systemd=true

[automount]
enabled=true
root=/mnt/
options="metadata,uid=1000,gid=1000,umask=022,fmask=111"

[network]
generateResolvConf=true
generateHosts=true

[interop]
enabled=true
appendWindowsPath=true

[user]
default=wubu
```

### 3. OCI/Docker (`wubu_deploy_oci`)

**Inputs**: `wubu_oci_config_t`
- `image_name` — e.g., "wubuos:latest"
- `dockerfile_path` — Dockerfile path
- `context_dir` — Build context
- `wubu_binary` — Path to built binary
- `base_image` — "scratch" | "alpine" | "debian" | custom
- `entrypoint` — Container entrypoint
- `env_vars` — NULL-terminated array
- `ports` — Exposed ports (e.g., "wayland")
- `volumes` — Mount points
- `multi_arch` — Build amd64/arm64 via buildx

**Process**:
1. Create rootfs in `context_dir/rootfs/`
2. Generate Dockerfile:
   - `scratch`: `COPY rootfs/ /`
   - `alpine`: `apk add libwayland-client libxkbcommon mesa-dri-gallium libdrm libgbm fontconfig ttf-dejavu ca-certificates`
   - `debian`: `apt-get install libwayland-client0 libxkbcommon0 mesa-vulkan-drivers libdrm2 libgbm1 fontconfig fonts-dejavu-core ca-certificates`
3. `docker build` or `docker buildx build`

**Output**: Local Docker image `wubuos:latest`

**Run**: `docker run --rm -it --device=/dev/dri wubuos:latest -w 1024 768`

### 4. macOS AVF (`wubu_deploy_macos`)

**Inputs**: `wubu_macos_config_t`
- `app_bundle_id` — e.g., "com.wubuos.app"
- `app_name` — Display name
- `kernel_path` — Linux kernel for VM
- `initramfs_path` — Initramfs for VM
- `output_app` — Output .app bundle path
- `wubu_binary` — Host binary (not used in VM)
- `entitlements` — Entitlements plist path
- `vm_memory_mb` — VM RAM
- `vm_cpus` — VM vCPUs
- `gui_enabled` — Enable virtio-gpu
- `rosetta` — Enable Rosetta for x86_64 Linux

**Process**:
1. Create `.app/Contents/{MacOS,Resources,Frameworks}` structure
2. Generate `Info.plist` (bundle ID, executable, min macOS 13.0)
3. Generate entitlements (hypervisor, vm.networking, Rosetta)
4. Copy kernel + initramfs to `Resources/`
5. Generate Swift launcher (`wubu_launcher.swift`) using Virtualization.framework:
   - `VZVirtualMachineConfiguration`
   - `VZLinuxBootLoader` with kernel + initrd
   - `VZVirtioEntropyDevice`, `VZVirtioTraditionalMemoryBalloonDevice`
   - `VZVirtioConsoleDeviceSerialPort` (stdio)
   - `VZVirtioNetworkDevice` (NAT)
   - `VZVirtioGPUDevice` (if gui_enabled)
   - `VZLinuxRosettaDirectoryShare` (if rosetta)
6. Generate `build_macos.sh` script (run on macOS with Xcode 15+)

**Output**: `WuBuOS.app` bundle structure + build script

**Build on macOS**:
```bash
cd WuBuOS.app
./build_macos.sh
open WuBuOS.app
```

## Rootfs Structure (Shared)

```
rootfs/
├── bin/ -> usr/bin
├── sbin/ -> usr/sbin
├── etc/
│   ├── passwd          # root:wubu
│   ├── group           # root:wubu:video:input
│   ├── hostname        # wubuos
│   ├── hosts           # localhost + wubuos.localdomain
│   ├── resolv.conf     # 1.1.1.1, 8.8.8.8
│   ├── fstab           # proc, sysfs, tmpfs
│   ├── profile         # PATH, HOME, USER, TERM
│   ├── bashrc          # aliases, PS1
│   └── wsl.conf        # WSL2 config
├── init                # Bare metal init script
├── proc/, sys/, dev/, run/, tmp/
├── var/log/, var/lib/, var/cache/
├── root/
├── home/wubu/
├── usr/bin/wubu        # Copied binary
├── lib/, lib64/
└── boot/
    ├── vmlinuz         # Kernel (bare metal only)
    ├── initramfs.img   # Initramfs (bare metal only)
    └── limine.conf     # Bootloader (bare metal only)
```

## Init Script (Bare Metal)

```sh
#!/bin/sh
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t tmpfs tmpfs /run
mkdir -p /dev/pts /dev/shm
mount -t devpts devpts /dev/pts
mount -t tmpfs tmpfs /dev/shm

# Load kernel modules
modprobe virtio_gpu 2>/dev/null
modprobe virtio_input 2>/dev/null
modprobe i915 2>/dev/null
modprobe amdgpu 2>/dev/null

# Setup networking
ip link set lo up
ip link set eth0 up 2>/dev/null || true
udhcpc -i eth0 -b 2>/dev/null || true

# Start WuBuOS
exec /usr/bin/wubu -w 1024 768
```

## API Summary

```c
/* Init/shutdown */
bool wubu_deploy_init(void);
void wubu_deploy_shutdown(void);

/* Default configs */
void wubu_deploy_get_default_baremetal(wubu_baremetal_config_t* config);
void wubu_deploy_get_default_wsl2(wubu_wsl2_config_t* config);
void wubu_deploy_get_default_oci(wubu_oci_config_t* config);
void wubu_deploy_get_default_macos(wubu_macos_config_t* config);

/* Validation */
bool wubu_deploy_validate_baremetal(const wubu_baremetal_config_t* config);
bool wubu_deploy_validate_wsl2(const wubu_wsl2_config_t* config);
bool wubu_deploy_validate_oci(const wubu_oci_config_t* config);
bool wubu_deploy_validate_macos(const wubu_macos_config_t* config);

/* Build targets */
bool wubu_deploy_baremetal(const wubu_baremetal_config_t* config);
bool wubu_deploy_wsl2(const wubu_wsl2_config_t* config);
bool wubu_deploy_oci(const wubu_oci_config_t* config);
bool wubu_deploy_macos(const wubu_macos_config_t* config);

/* Helpers */
bool wubu_deploy_create_rootfs(const char* rootfs_dir, const char* wubu_binary);
bool wubu_deploy_generate_limine_conf(const char* output_path, const char* kernel_cmdline);
bool wubu_deploy_generate_wsl_conf(const char* output_path, bool systemd);
bool wubu_deploy_generate_dockerfile(const wubu_oci_config_t* config, const char* output_path);
bool wubu_deploy_generate_entitlements(const wubu_macos_config_t* config, const char* output_path);
bool wubu_deploy_generate_infoplist(const wubu_macos_config_t* config, const char* output_path);
bool wubu_deploy_verify_output(const char* output_path, const char* expected_sha256);
```

## Test Coverage

All 9 tests pass:
```
test_deploy_lifecycle          PASS
test_default_configs           PASS
test_validation                PASS
test_limine_generation         PASS
test_wsl_conf_generation       PASS
test_dockerfile_generation     PASS (scratch, alpine, debian)
test_entitlements_generation   PASS (with/without Rosetta)
test_infoplist_generation      PASS
test_rootfs_creation           PASS
```

## Makefile Integration

```makefile
GUI_OBJS += $(GUI)/wubu_deploy.o

HOSTED_OBJS += $(GUI)/wubu_deploy.o

hosted: $(HOSTED_OBJS) ...
    $(GUI)/wubu_deploy.c ...

test_deploy:
    $(CC) ... $(GUI)/wubu_deploy.c $(GUI)/wubu_settings.c $(GUI)/wubu_theme.c \
        $(GUI)/wubu_deploy_test.c -o $(GUI)/wubu_deploy_test
    $(GUI)/wubu_deploy_test

test: test_deploy ...
```

## Common Pitfalls

1. **symlink return values** — `symlink()` return is ignored in rootfs creation (OK for build)
2. **uint64_t format** — Use `%lu` not `%llu` on Linux (warning in macOS launcher generation)
3. **snprintf truncation** — Buffer sizes adequate but compiler warns; paths < 512 chars
4. **dangling pointer** — `config->volumes` default uses compound literal (stack); OK since used immediately
5. **macOS build requires macOS** — Generated structure + script must be built on macOS with Xcode
6. **Rootfs paths** — Fixed hardcoded `/home/wubu/...` paths to use `rootfs_dir` parameter

## Future Enhancements

- [ ] PXE boot support
- [ ] ARM64 bare metal (Raspberry Pi)
- [ ] Signed macOS app bundle (Developer ID)
- [ ] SBOM generation for OCI image
- [ ] GitHub Actions CI for all 4 targets