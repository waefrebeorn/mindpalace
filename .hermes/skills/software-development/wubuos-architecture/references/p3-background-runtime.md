# P3 /n/background runtime — the Mint-baseline session future

Derived from `os-studies/linuxmint_background_baseline.md`: model Cinnamon/Mint's
layered background (session manager + message bus + XDG autostart + the 5
service contracts) as tested C11 modules, all observable through the one
STYX/9P `/n` namespace. **10 primitives / 174 checks / ~30 runtime source files**
(`wubu_*` in `src/runtime/`), each with a `make test_<x>` target.

## Module map (all in src/runtime/)

| Module | Contract | make target |
|--------|----------|-------------|
| `wubu_bus.{c,h}` | D-Bus well-known-name ownership + **on-demand activation** (§4.1): `send_to_name` to an UNOWNED name fires the `set_activator` hook (bus starts the service on first call); unowned placeholder slot is claimable by name, only another-OWNED name is rejected | test_wubu_bus (26) |
| `wubu_xdg_autostart.{c,h}` | freedesktop `.desktop` parser + launcher (§3.2): gates on `Type=Application`, `Hidden=true`, `X-GNOME-Autostart-enabled=false`; strips field codes `%f%F%u%U%d%D%n%N%i%c%k`, `%%`→`%`, keeps quoted args as one token; launch decoupled so argv can go through `wubu_exec` | test_xdg_autostart (13) |
| `wubu_session_boot.{c,h}` | ties bus+autostart: scans dirs, claims `org.wubu.autostart.<basename>` per app on the bus, launches via INJECTABLE handler; refuses until launcher set, releases name if launcher refuses | test_session_boot (12) |
| `wubu_ns_background.{c,h}` | publishes the control tree via ns_mkdir/ns_write (no daemon): `bus/names`, `bus/nconn`, `autostart/*`, `session_boot`, and (added with the daemon) `wubu_ns_publish_login` (session/{active,seat,type,count,list}) + `wubu_ns_publish_auth` (auth/{rules,rulecount,has_agent}) | test_ns_background (17) |
| `wubu_svc_socket.{c,h}` | socket activation (§4.2): Unix-domain listen socket fires activator ONCE on first poll()-connection, then hands accepted fd to service (LISTEN_FDS); refused → re-arms | test_svc_socket (17) |
| `wubu_logind.{c,h}` | logind-equivalent (§4.3/§153): session registry id/seat/type/class/uid/state, query by id/active, replace-by-id (no dup); power ops gated by injectable authorizer (the polkit seam), default DENY | test_logind (17) |
| `wubu_auth.{c,h}` | polkit authority (§4.4/§154): subject→action→allow|deny|interactive rule table, hard DENY overrules, wildcard `WUBU_AUTH_UID_ANY`, INTERACT resolves via per-session agent, fail-closed (no rule or no agent = DENY), rule() replaces no-dup | test_auth (24) |
| `wubu_session_daemon.{c,h}` | the role-up: owns session-boot + login + auth WIRED as the login power gate; `wubu_session_daemon_publish` writes the whole /n/background tree | test_session_daemon (15) |
| `wubu_deskenv.{c,h}` | DE-daemon surface (§154/§5): tray `{slot,owner}` ownership (one owner per slot, late different claimant refused, same-owner re-claim idempotent, release by owner only) + one `nemo-desktop` desktop owner; publishes `de/tray`, `de/traycount`, `de/desktop` | test_deskenv (20) |
| `wubu_session_mgr.{c,h}` | ONE-call login boot: `wubu_session_mgr_boot(dirs,n,launcher,ud)` composes all of it (session daemon + default power policy + autostart + desktop/tray + full publish) | test_session_mgr (13) |

## Two bugs that MUST be remembered (same class, will recur)

1. **Enum-0-as-denial bridging.** `auth_authorizer` (returns allow/deny to the
   login power gate) did `return (allowed) ? 0 : WUBU_AUTH_DENY;` — but
   `WUBU_AUTH_DENY == 0`, so a DENIAL returned 0, and the login gate treats
   0 as **allow**. When bridging two modules where ONE side uses `0=success,
   nonzero=deny` and the OTHER side's first enum value is 0, the "deny" must
   be mapped to a nonzero code (`WUBU_AUTH_DENY + 1`). **Check enum value 0
   when one module's return convention is 0-means-success.**

2. **File-vs-directory namespace collision.** `wubu_ns_publish_background` wrote
   a flat `background/session` FILE while `wubu_ns_publish_login` did
   `ns_mkdir("background/session")` (a DIRECTORY) — the mkdir failed on the
   existing file and the whole `publish` returned -1 with NO diagnostic. When
   two publishers write the same `/n` subtree, one flat file per path: an
   authoritative directory belongs to exactly one publisher; the other's flat
   file must live at a different name (`background/session_boot`). A
   mkdir-on-existing-file is a silent whole-tree failure, not a per-file one.

## Test-pattern notes

- **Memory-constrained rule (every /n subtree test):** link `wubu_ns_fs.o` +
  the *source modules*, and re-point the root directly —
  `*(const char **)&g_ns_root = NSROOT;` (mkdir NSROOT first) — do NOT link
  `wubu_ns_bridge.o` (drags the whole archd/bottle graph). Compile the test to
  a `.o` separately, then link `-no-pie` with `wubu_ns_fs.o` + module `.c`s.
- **Link-regression sweep:** a shared publisher module (`wubu_ns_background.c`)
  that gains a dependency (login/auth) breaks EVERY recipe listing it — the
  `test_ns_background` target must add `wubu_logind.c` + `wubu_auth.c`. One
  passing make target does not catch sibling targets; re-run each affected one.
- **Order-independent reads:** assert autostart files "one of these names" not
  "index 1 is X" — scan order is readdir-dependent.
- **`-DWUBU_HOSTED` on every recipe that links a holyd/`hd_*` TU:** a test
  recipe that compiles `holyd_codegen_api.c` (or any holyd front-end) but omits
  `-DWUBU_HOSTED` compiles fine and then segfaults at RUNTIME inside
  `hd_eval`/`hd_compile_func` (the JIT exec-allocator path only exists under the
  flag). `test_wubu` hit exactly this after the holyc→holyd migration. The
  failure is invisible to `make all` (which does not exercise that recipe's run
  step) and to a compile-only pass — you must RUN the specific target. Grep the
  recipe for `WUBU_HOSTED` whenever you touch a test line that lists these TUs,
  the same way the JIT test recipes already do.
- Hosted test `.c` files need `_GNU_SOURCE` as the FIRST line (before includes)
  for `mkdtemp`/`PATH_MAX`; see the skill's "Feature Macros Must Precede
  Includes" section.
