# WuBuOS Image Builder Implementation Reference

## Overview
The Image Builder (`wubu_image.c`) implements a Dockerfile-like build system for `.wubu` containers with multi-stage builds, layer caching, and OCI export capability.

## WuBuFile Syntax

```dockerfile
# Base image
FROM archlinux:latest AS base
# Or Steam Runtime
FROM steam-runtime-2.0:soldier AS runtime
# Or Proton
FROM proton:GE AS proton

# Build arguments
ARG VERSION=1.0
ARG BUILD_TYPE=release

# Environment
ENV APP_NAME=myapp \
    APP_VERSION=${VERSION} \
    PATH=/usr/local/bin:$PATH

# Working directory
WORKDIR /app

# Copy source
COPY src/ ./src/
COPY Cargo.toml ./
COPY package.json ./

# Build commands
RUN pacman -Sy --noconfirm --needed base-devel git cmake
RUN cargo build --release --features ${BUILD_TYPE}

# Runtime stage
FROM archlinux:latest
COPY --from=base /app/target/release/myapp /usr/local/bin/myapp
USER 1000:1000
EXPOSE 8080
ENTRYPOINT ["myapp"]
CMD ["--config", "/etc/myapp/config.toml"]
```

## Supported Instructions

| Instruction | Description |
|-------------|-------------|
| `FROM <image>[:tag] [AS <name>]` | Base image, starts new stage |
| `RUN <command>` | Execute command in layer |
| `COPY [--from=<stage>] <src>... <dest>` | Copy files from context or previous stage |
| `ADD [--from=<stage>] <src>... <dest>` | Copy with auto-extract (tar/gzip) |
| `CMD ["exe", "arg"]` | Default command |
| `ENTRYPOINT ["exe", "arg"]` | Fixed entrypoint |
| `ENV <key>=<val> ...` | Environment variables |
| `ARG <name>[=<default>]` | Build-time arguments |
| `WORKDIR <path>` | Working directory |
| `USER <user>[:<group>]` | User/group for subsequent commands |
| `EXPOSE <port>[/protocol]` | Document exposed ports |
| `VOLUME ["/path1", "/path2"]` | Mount points |
| `LABEL <key>=<val> ...` | Image metadata |
| `SHELL ["exe", "-c"]` | Default shell |
| `ARCH <arch>` | Target architecture (x86_64, aarch64, riscv64, wasm) |
| `OS <os>` | Target OS (linux, windows, macos, native) |

## Multi-Stage Builds

Each `FROM` starts a new build stage. Use `--from=<stage>` in `COPY` to reference previous stages:

```dockerfile
FROM archlinux:latest AS builder
RUN pacman -Sy --noconfirm cargo
COPY src/ .
RUN cargo build --release

FROM scratch AS runtime
COPY --from=builder /target/release/myapp /myapp
ENTRYPOINT ["/myapp"]
```

## Layer Caching

- Each stage creates a layer with SHA256 content-addressable digest
- Cache stored at `/var/cache/wubu/layers/<sha256>`
- Cache hit: layer reused without rebuild
- Cache invalidation: any instruction change invalidates subsequent layers

```bash
# Manual cache operations
wubu_layer_cache_get <digest> <out_data> <out_size>
wubu_layer_cache_put <digest> <data> <size>
wubu_layer_cache_exists <digest>
```

## Base Image Loaders

```c
// Arch Linux package base
wubu_image_load_base_arch("base-devel", "latest", stage);

// Steam Runtime 2.0 "Soldier"
wubu_image_load_steam_runtime(WUBU_ARCH_X86_64, stage);

// Proton-GE
wubu_image_load_proton("GE-Proton9-24", stage);
```

## Build API

```c
WubuBuildContext ctx = {0};
ctx.output_tag = "myapp:latest";
ctx.progress_cb = my_progress_callback;

if (wubu_parse_wubufile("WuBuFile", &ctx) == 0) {
    WubuImageManifest manifest;
    wubu_image_build(&ctx, &manifest);
    
    // Export to .wubu (native format)
    wubu_image_export_wubu(&manifest, "myapp.wubu");
    
    // Export to OCI tarball (Docker-compatible)
    wubu_image_export_oci(&manifest, "myapp.tar");
}
```

## Export Formats

### .wubu (Native)
```c
WUBU_HEADER (64 bytes) + JSON manifest payload
```

### OCI v1.0.2 Layout (Docker Compatible)
```
<output_dir>/
├── oci-layout          {"imageLayoutVersion":"1.0.0"}
├── index.json          OCI Image Index (multi-arch)
├── blobs/
│   └── sha256/
│       ├── <config_digest>     # Image config
│       ├── <manifest_digest>   # Image manifest
│       └── <layer_digestN>     # Layer tars
```

## Progress Callback

```c
void my_progress_callback(const char *stage, const char *instruction,
                          int current, int total, void *user_data) {
    printf("[%d/%d] %s: %s\n", current, total, stage, instruction);
}

ctx.progress_cb = my_progress_callback;
```

## Tag Management

```c
wubu_image_tag("sha256:abc123...", "myapp:v1.0");
wubu_image_untag("myapp:latest");
wubu_image_list(tags, max);
```

## Manifest JSON

```c
char json[65536];
wubu_manifest_to_json(&manifest, json, sizeof(json));
// {"image_id":"sha256:...","name":"myapp","tag":"latest","arch":0,"os":0,"created":1234567890,"layer_count":5,"entrypoint":["/app/myapp"],"cmd":[]}
```

## Integration with Container Runtime

```c
// Create container from .wubu image
WubuCt *ct = WubuCtCreate("myapp", "/var/wubu/roots/arch-base", CT_NATIVE);
WubuCtAddBind(ct, "/host/path", "/container/path", FALSE);
WubuCtSetCmd(ct, 2, {"/usr/local/bin/myapp", "--serve"});
WubuCtStart(ct);
WubuCtWait(ct);
```

## Testing

```bash
make test_wubu_image  # When test target is added
```

## Key Implementation Details

1. **No OpenSSL dependency** - SHA256 implemented inline (FIPS 180-4)
2. **POSIX only** - Uses `tar`, `mkdir`, `cp` via system() for simplicity
3. **Layer isolation** - Each stage builds in `/tmp/wubu_build_<pid>/stageN/`
4. **Content-addressable** - Layers identified by SHA256 of tar content
5. **OCI compliance** - Produces valid OCI Image Layout v1.0.0