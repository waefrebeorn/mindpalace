# UEFI Secure Boot enrollment model (omarchy/sbctl) -- expanding WuBuFW

## Why this reference exists
WuBuFW verifies EFI images against db/dbx, but enrolls policy as in-memory
arrays with a flag-flip PK -- it does not store real UEFI Secure Boot
variables. The reference model for a real enrollment flow is omarchy + sbctl:
PK/KEK/db/dbx as UEFI variables, a setup->user transition on PK, enforcement
requiring PK+db, and an sbctl-style host key/sign tool.

## The omarchy/sbctl model
- Boot chain: Microsoft-signed shim -> MokManager (enrollment) -> signed second
  stage -> signed UKI. Installed systems use a machine-local MOK; the release
  private key never touches the ESP or the installed system.
- sbctl workflow: `create-keys`, `enroll-keys --microsoft`, `sign -s <efi>`,
  `verify`, `status`. Keys live in NVRAM; signing is per-artifact.
- References: omarchy-iso `plans/consumer-secure-boot.md` (shim + MOK + UKI,
  dev-signing mode for QEMU); `rootkiller6788/mini-firmware-boot`
  `mini-secure-boot/` (from-scratch C: PK/KEK/db/dbx, signed EFI images,
  verified boot chain, UEFI Spec Ch 32).

## UEFI Secure Boot variable model
- EFI_GLOBAL_VARIABLE GUID `8BE4DF61-93CA-11D2-AA0D-00E098032B8C` carries
  `PK`, `KEK`, `SecureBoot` (UINT8), `SetupMode` (UINT8).
- db/dbx use EFI_IMAGE_SECURITY_DATABASE_GUID
  `D719B2CB-3D3A-4596-A3BC-DAD00E67656F`.
- Variable attributes: NV=0x1, BS=0x2, RT=0x4, TIME_BASED=0x20000000.
  PK = NV|BS|RT|TIME_BASED; KEK/db/dbx = NV|BS|RT.
- Setup mode = no PK enrolled. User mode = PK present. Enforcement = user
  mode AND db non-empty. Loading order matters: db/dbx first, then KEK, then
  PK; once PK is loaded the stores accept only signed updates.
- `EFI_SIGNATURE_LIST` layout: SignatureType GUID (16) + SignatureListSize
  (4) + SignatureHeaderSize (4) + SignatureSize (4) = 28-byte header, then
  SignatureHeader (SignatureHeaderSize bytes), then EFI_SIGNATURE_DATA entries
  of SignatureSize bytes each = SignatureOwner GUID (16) + SignatureData
  (SignatureSize - 16).
- SignatureType for an X.509 cert = EFI_CERT_X509_GUID
  `A5C059A1-94E4-4AA7-87B5-AB155C2BF072`. db SignatureData = DER cert;
  dbx entries are a hash or a cert.

## WuBuFW current state (the gap)
- `fw_secureboot.c`: hash-based db/dbx (SHA-256 of the DER leaf) held in
  in-memory `g_db[8]`/`g_dbx[8]`; `fw_sb_set_pk()` just flips
  `g_setup_mode`/`g_enforce` flags. There are NO real EFI variables yet -- the
  "PK/KEK/db/dbx variable storage (in the existing NV variable store)" claim
  is aspirational, not implemented.
- `fw_sb_verify()` computes the Authenticode PE hash, then matches the
  embedded leaf cert SHA-256 against db/dbx. Deliberate simplification: the
  tree has SHA-256 only (no RSA/CMS/PKCS7/X.509 parsing), so signature math is
  out of scope; the hash match is the security-relevant decision we can exercise.
- Selftests: `fw_sb_selftest` (policy engine), `fw_sb_selftest_pe` (signed PE
  verifies / unsigned rejected).
- Variable service: `fw_rt_set_variable` / `fw_rt_get_variable` (EFIAPI, in
  fw_rt.c). In-memory store: MAX_VARS 64, VAR_DATA_MAX 1024, volatile (no SPI
  flash on the QEMU `-bios` path). `GetVariable` returns EFI_NOT_FOUND when
  absent and EFI_BUFFER_TOO_SMALL (setting *size) when *size < v->size or
  data == NULL -- probe presence with data==NULL, then allocate.

## Expansion design (model to implement -- NOT yet verified)
- Store PK/KEK/db/dbx as EFI_SIGNATURE_LIST via `fw_rt_set_variable` with the
  standard GUIDs/attributes, so the OS/payload can read them (real firmware
  behavior) instead of the in-memory arrays.
- `fw_sb_enroll_esl(which, esl, len)`: parse the ESL, extract the first cert,
  store its hash in the in-memory db/dbx, write the ESL variable; for PK, flip
  to user mode and write SecureBoot=1 / SetupMode=0.
- Keep the hash-based verify (no RSA in the tree).
- Shell commands: `sbstatus`, `sbenroll <file>`, `sbpk` (self-create + enroll a
  platform key).
- Host tool (sbctl-like): `tools/mksb.c` -- create-keys (write PK/KEK/db ESLs
  + a cert), sign (attach the cert via `mkpe -cert`), verify.
- Gate: boot WuBuFW, enroll, assert enforcement + variable visibility.

## Pitfalls
- The variable store is volatile: PK/db do not survive a reboot on the QEMU
  `-bios` path. Enroll at runtime for tests; never claim persistence.
- `fw_rt_get_variable` with `data == NULL` is the presence probe -- it returns
  EFI_BUFFER_TOO_SMALL, not EFI_NOT_FOUND, when the variable exists.
- The existing `fw_sb_enroll_db/dbx(der, len)` API takes a RAW DER cert, not an
  ESL; wrap it in an ESL before feeding `fw_sb_enroll_esl`.
