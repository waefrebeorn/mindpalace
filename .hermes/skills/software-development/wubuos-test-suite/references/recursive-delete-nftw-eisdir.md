# Latent Recursive-Delete Bug: nftw + unlink -> EISDIR (silent no-op)

Real bug closed 2026-07-13 (commit d51d974). A textbook "green gate, broken
code" silent mask.

## The bug
`wubu_fs_rm_rf(path)` did:
```c
nftw(path, wubu_fs_unlink_cb, 64, FTW_DEPTH | FTW_PHYS);
```
with
```c
static int wubu_fs_unlink_cb(...) { return unlink(fpath) == 0 ? 0 : -1; }
```
With FTW_DEPTH, directories are visited post-order as `FTW_DP`. `unlink()` on a
directory returns **EISDIR**, so the callback returns -1, `nftw` aborts the
traversal, and the tree is LEFT IN PLACE. Every caller (`rm_rf` in
`wubu_proton_util`, `archd_rm_rf`, `bottles_rm_rf`) ignored the return code, so
"recursive delete" silently did nothing for any directory.

A green gate never caught it - no test asserted a dir tree was actually gone.

## The fix
```c
static int wubu_fs_unlink_cb(const char *fpath, const struct stat *sb,
                             int typeflag, struct FTW *ftwbuf) {
    (void)sb; (void)ftwbuf;
    if (typeflag == FTW_DP) return rmdir(fpath) == 0 ? 0 : -1;
    return unlink(fpath) == 0 ? 0 : -1;
}
```

## Standalone verification harness
```c
#define _GNU_SOURCE
#include <ftw.h>, <sys/stat.h>, <unistd.h>, <stdio.h>
static int cb(const char*f,const struct stat*sb,int t,struct FTW*ft){
  (void)sb;(void)ft; if(t==FTW_DP) return rmdir(f); return unlink(f); }
int wubu_fs_rm_rf(const char*p){ return nftw(p,cb,64,FTW_DEPTH|FTW_PHYS); }
int main(void){
  char d[256]; snprintf(d,sizeof d,"/tmp/rmtest_%d",getpid());
  mkdir(d,0755); char f[300]; snprintf(f,sizeof f,"%s/val",d);
  FILE*fp=fopen(f,"w"); fputc('x',fp); fclose(fp);
  int rc = wubu_fs_rm_rf(d);
  printf("rc=%d after-access=%d\n", rc, access(d,F_OK));  // want rc=0, access!=0
}
```

## Class lesson
When a "helper" is called by many modules and its rc is widely ignored, grep the
callers' ignore pattern AND test the deep path (directory, not just file) before
trusting it. A handler that "returns SUCCESS" can still be a no-op underneath.
