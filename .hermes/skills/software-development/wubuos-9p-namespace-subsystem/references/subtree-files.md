# Per-item / subtree namespace files: the `<name>/<item>/<leaf>` recipe

When a subsystem exposes MANY items, each its own file, use one shape. The
worked example is `wubu_ns_experts.c` (`/n/experts/layer/<L>`, one line per
resident slot). The same shape fits `/n/hive/cell/<id>`, `/n/kv/<layer>/<slot>`,
`/n/models/<name>`.

## Mirror shape
A fixed-capacity file-static mirror holds every item's state. Bounded arrays,
no malloc (matches the codebase's fixed-array discipline):

```c
#define NSX_MAX_LAYERS 256
#define NSX_MAX_SLOTS  64
static struct {
    int  n_layers, n_experts, d_model, d_ff, slot_bank; /* config */
    long stat_pageins, stat_hits; long long stat_bytes;  /* stats  */
    int  slots[NSX_MAX_LAYERS][NSX_MAX_SLOTS]; /* item -> sub-item id, -1 free */
    long lru[NSX_MAX_LAYERS][NSX_MAX_SLOTS];
    int  n_slots[NSX_MAX_LAYERS];
} g_x;
```

Setters take an item index and a small array; clamp the index and the count
against the max, ignore out-of-range (never crash):

```c
void wubu_ns_experts_set_layer(int layer, const int *slots, const long *lru, int n){
    if (layer < 0 || layer >= NSX_MAX_LAYERS) return;
    if (n > NSX_MAX_SLOTS) n = NSX_MAX_SLOTS;
    g_x.n_slots[layer] = n;
    for (int s = 0; s < n; s++) {
        g_x.slots[layer][s] = slots ? slots[s] : -1;
        g_x.lru[layer][s]   = lru   ? lru[s]   : 0;
    }
}
```

## Sync: mkdir every level, then loop items
`ns_write` does NOT create parents, so `ns_mkdir` the item subdir BEFORE the
loop, then write one file per item. Build each multi-line body with a running
offset and bound every `snprintf` so it cannot overrun the buffer:

```c
int wubu_ns_experts_sync(void){
    if (!g_ns_root) return -1;
    char sub[128], buf[4096];
    if (ns_mkdir("experts") != 0) return -1;
    if (ns_mkdir("experts/layer") != 0) return -1;   /* <-- the level people miss */
    /* ...config + stats via ns_write("experts/config", ...)... */
    for (int L = 0; L < g_x.n_layers && L < NSX_MAX_LAYERS; L++){
        snprintf(sub, sizeof sub, "experts/layer/%d", L);
        int off = 0;
        off += snprintf(buf+off, sizeof(buf)-off, "# slot:expert:lru\n");
        for (int s = 0; s < g_x.n_slots[L]; s++){
            int w = snprintf(buf+off, sizeof(buf)-off, "%d:%d:%ld\n",
                             s, g_x.slots[L][s], g_x.lru[L][s]);
            if (w < 0 || (size_t)(off+w) >= sizeof(buf)) break;  /* bounded */
            off += w;
        }
        if (ns_write(sub, buf) != 0) return -1;
    }
    return 0;
}
```

## Test
Set the ns root directly (`g_ns_root = <tmpdir>`), push config/stats/one
item, sync, then read the files back and assert on substrings (state, not
pixel/byte counts). Also assert `sync()` returns -1 when `g_ns_root` is NULL.
Re-push changed stats and re-sync to prove updates flow through. Link only
`$(RT)/wubu_ns_fs.o` + the module `.c` — the mirror means no dependency on
the real subsystem.
