# NVML API excerpt for monitoring

The values below are the driver ABI. Read `/usr/include/nvml.h` on the box to
confirm before relying on a constant you do not see here.

## Return codes that matter

| Code | Name | Meaning for monitoring |
|------|------|------------------------|
| 0 | `NVML_SUCCESS` | The call wrote its outputs. Read them. |
| 3 | `NVML_ERROR_NOT_SUPPORTED` | The card/driver cannot report this. Degrade the field to 0 and say so. |
| 6 | `NVML_ERROR_NOT_FOUND` | **The driver wrote ZERO samples.** The count is stale; do not read the buffer. Means "nothing on the GPU right now". |
| 7 | `NVML_ERROR_INSUFFICIENT_SIZE` | The count output is the size the driver needs. Grow the buffer and call again once. |
| 15 | `NVML_ERROR_GPU_IS_IDLE` | Same as NOT_FOUND, phrased as idleness. Capability present, no reading. |

## Constants

| Name | Value |
|------|-------|
| `NVML_TEMPERATURE_GPU` | 0 |
| `NVML_CLOCK_GRAPHICS` | 0 |
| `NVML_CLOCK_SM` | 1 |
| `NVML_CLOCK_MEM` | 2 |
| `NVML_PCIE_UTIL_TX_BYTES` | 0 (1 KB granularity) |
| `NVML_PCIE_UTIL_RX_BYTES` | 1 (1 KB granularity) |

## Types

```c
/* the handle is opaque */
typedef void *nvmlDevice_t;

/* nvmlProcessUtilizationSample_t -- percentages, NO memory */
typedef struct {
    unsigned int        pid;        /* offset 0  */
    unsigned long long  timeStamp;  /* offset 8  (microseconds) */
    unsigned int        smUtil;     /* offset 16 */
    unsigned int        memUtil;    /* offset 20 */
    unsigned int        encUtil;    /* offset 24 */
    unsigned int        decUtil;    /* offset 28 */
} nvmlProcUtilSample_t;             /* 32 bytes with padding */

/* nvmlProcessInfo_t -- memory, NO utilisation */
typedef struct {
    unsigned int        pid;
    unsigned long long  usedGpuMemory;   /* bytes */
    unsigned int        gpuInstanceId;
    unsigned int        computeInstanceId;
} nvmlProcessInfo_t;

/* card metrics */
typedef struct { unsigned int gpu, memory; } nvmlUtilization_t;
typedef struct { unsigned long long total, free, used; } nvmlMemory_t;
```

## Functions used

```c
nvmlReturn_t nvmlInit_v2(void);
nvmlReturn_t nvmlShutdown(void);
nvmlReturn_t nvmlDeviceGetCount_v2(unsigned int *count);
nvmlReturn_t nvmlDeviceGetHandleByIndex_v2(unsigned int index, nvmlDevice_t *device);
nvmlReturn_t nvmlDeviceGetName(nvmlDevice_t, char *name, unsigned int len);
nvmlReturn_t nvmlDeviceGetUtilizationRates(nvmlDevice_t, nvmlUtilization_t *util);
nvmlReturn_t nvmlDeviceGetMemoryInfo(nvmlDevice_t, nvmlMemory_t *memory);
nvmlReturn_t nvmlDeviceGetPowerUsage(nvmlDevice_t, unsigned int *milliwatts);
nvmlReturn_t nvmlDeviceGetPowerManagementLimit(nvmlDevice_t, unsigned int *milliwatts);
nvmlReturn_t nvmlDeviceGetTemperature(nvmlDevice_t, unsigned int sensor, unsigned int *celsius);
nvmlReturn_t nvmlDeviceGetClockInfo(nvmlDevice_t, unsigned int type, unsigned int *mhz);
nvmlReturn_t nvmlDeviceGetPcieThroughput(nvmlDevice_t, unsigned int counter, unsigned int *kbps);
nvmlReturn_t nvmlDeviceGetEncoderUtilization(nvmlDevice_t, unsigned int *util, unsigned int *period);
nvmlReturn_t nvmlDeviceGetDecoderUtilization(nvmlDevice_t, unsigned int *util, unsigned int *period);

/* per-process utilisation -- the percentage path */
nvmlReturn_t nvmlDeviceGetProcessUtilization(nvmlDevice_t device,
        nvmlProcessUtilizationSample_t *utilization,
        unsigned int *processSamplesCount,
        unsigned long long lastSeenTimeStamp);

/* per-process memory -- the memory path */
nvmlReturn_t nvmlDeviceGetComputeRunningProcesses_v3(nvmlDevice_t,
        unsigned int *infoCount, nvmlProcessInfo_t *infos);
nvmlReturn_t nvmlDeviceGetGraphicsRunningProcesses_v3(nvmlDevice_t,
        unsigned int *infoCount, nvmlProcessInfo_t *infos);
```

## The per-process contract

- The utilisation call returns samples newer than `lastSeenTimeStamp`. Pass 0
  the first time, then the newest `timeStamp` seen.
- It reports PERCENTAGES ONLY. A process holding 2 GB with 0% shows `smUtil 0`
  -- that is a memory-only row, not an error.
- Memory comes from the two running-process calls, keyed by pid. Merge into
  the utilisation rows; pids present only in the memory list are still real
  rows (the "idle but hogging" callout).
- `usedGpuMemory == 0xFFFFFFFFFFFFFFFF` means the driver did not report it
  (WDDM always reports this); skip the row's memory, keep the percentage.
