# FFmpeg Pipe Subprocess Pattern

When WuBuOS needs media decode/encode, the pattern is to spawn `ffmpeg` as a
subprocess and communicate via pipes — no libav* linking required.

## Decoder (ffmpeg → pipe → WuBuOS)

```
[Media File] → ffmpeg -f rawvideo (or s16le) → stdout pipe → read() in C
```

### Video frames (raw RGBA)
```bash
ffmpeg -v quiet -i '<path>' -f rawvideo -pix_fmt rgba -
```
Each `read()` gets `width * height * 4` bytes of RGBA.

### Audio frames (PCM s16le)
```bash
ffmpeg -v quiet -i '<path>' -f s16le -acodec pcm_s16le -
```
Each `read()` gets interleaved `int16_t` samples.

### Seeking
Kill the old ffmpeg process, respawn with `-ss <timestamp>`:
```bash
ffmpeg -v quiet -ss <timestamp> -i '<path>' -f rawvideo ...
```

## Encoder (WuBuOS → pipe → ffmpeg)

```
stdin pipe → write() in C → ffmpeg -f rawvideo (or s16le) -i - → [Output File]
```

### Video frames
```bash
ffmpeg -y -v quiet -f rawvideo -pix_fmt rgba -s WxH -r FPS -i - -c:v <codec> '<output>'
```

### Audio frames
```bash
ffmpeg -y -v quiet -f s16le -ar 44100 -ac 2 -i - -c:a <codec> '<output>'
```

## C Implementation Pattern

### Fork + pipe setup
```c
int fds[2];
pipe(fds);
pid_t pid = fork();
if (pid == 0) {
    close(fds[READ_END]);
    dup2(fds[WRITE_END], STDOUT_FILENO);  // for decoder
    // OR: dup2(fds[READ_END], STDIN_FILENO); // for encoder
    execvp("ffmpeg", argv);
    _exit(1);
}
close(fds[WRITE_END]);  // decoder: read from fds[READ_END]
// OR: close(fds[READ_END]);  return fds[WRITE_END]; // encoder
```

### Pitfalls
- `ffprobe` (JSON metadata) uses `popen()` not fork+pipe — different pattern
- The ffmpeg CLI uses stdout for raw data and stderr for progress/logs — redirect
  stderr to `/dev/null` in hosted mode, or capture it in debug builds
- Without `-v quiet`, stray stderr output interleaves with pipe data and corrupts frames
- The cmd-string-to-argv split (strtok on spaces) is fragile for paths with spaces —
  use explicit argv arrays for real deployments
- Always `waitpid()` on close to prevent zombies
