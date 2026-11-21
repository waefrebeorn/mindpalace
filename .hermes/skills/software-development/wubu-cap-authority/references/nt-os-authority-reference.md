# Windows NT Object Manager & Security Reference Monitor — A Capability-Authority Reference

A precise, C-implementable specification of the NT authority model. Claims are
grounded in the ReactOS reference implementation (`reactos/reactos` — a readable
re-implementation of the NT kernel, structurally identical to Windows for the
Object Manager and SRM) plus the Windows Driver Kit / win32 APIs as the
authoritative Microsoft contract.

Local source paths below refer to `/home/wubu/reactos-study/reactos/` (checked
out at commit `71ee7547`). GitHub blob URLs are the published mirror of the
same tree: `https://github.com/reactos/reactos/blob/master/<path>`.

All C snippets are copy-paste faithful to ReactOS `ntoskrnl` / header layouts.

---

## 1. The Object Manager: handle tables, headers, namespace

### 1.1 Per-process handle table

Each process stores one handle table on `EPROCESS.ObjectTable`
(`PsGetCurrentProcess()->ObjectTable`, `ntoskrnl/ex/handle.c`), created via
`ExCreateHandleTable(NULL)`. The table is a 3-level array:

```
/* sdk/include/ndk/extypes.h — ReactOS's layout matches Windows */
typedef struct _HANDLE_TABLE_ENTRY {
    union { PVOID Object; ULONG_PTR ObAttributes; PHANDLE_TABLE_ENTRY_INFO InfoTable; ULONG_PTR Value; };
    union { ULONG GrantedAccess; struct { USHORT GrantedAccessIndex; USHORT CreatorBackTraceIndex; }; LONG NextFreeTableEntry; };
} HANDLE_TABLE_ENTRY, *PHANDLE_TABLE_ENTRY;
```

A `HANDLE` value is an index encoded with low 2 bits reserved for alignment/tag;
the kernel decodes it (`ExMapHandleToPointer` / `HandleTableEntryByIndex`) and
returns the entry, or `NULL` ⇒ caller returns `STATUS_INVALID_HANDLE`
(obhandle.c `ObpReferenceProcessObjectByHandle`: `HandleEntry = ExMapHandleToPointer(...); if (HandleEntry) {...} else {...Status = STATUS_INVALID_HANDLE;}`).

`GrantedAccess` is **the access mask actually granted when the handle was
opened** and is immutable for the life of the handle unless re-duplicated; it is
NOT re-evaluated on each use. There is a second low bit used internally:
`#define ObpAccessProtectCloseBit 0x02000000L` (`ntoskrnl/include/internal/ob.h`),
set when `OBJ_PROTECT_CLOSE` (0x01) was requested via `NtSetInformationObject`/`ObSetHandleAttributes` — this is the *only* handle-level mutability flag.

### 1.2 OBJECT_HEADER

Every kernel object is preceded by a variable-length header whose "standard"
body is `QUAD Body`. The header layout (`sdk/include/ndk/obtypes.h`):

```c
typedef struct _OBJECT_HEADER {
    LONG_PTR PointerCount;     // strong references (interlocked)
    union { LONG_PTR HandleCount; volatile PVOID NextToFree; };
    POBJECT_TYPE Type;         // points back to the OBJECT_TYPE (index lookup)
    UCHAR NameInfoOffset;      // NULL if nameless -> OBJECT_HEADER_TO_NAME_INFO NULL
    UCHAR HandleInfoOffset;
    UCHAR QuotaInfoOffset;
    UCHAR Flags;
    union { POBJECT_CREATE_INFORMATION ObjectCreateInfo; PVOID QuotaBlockCharged; };
    PSECURITY_DESCRIPTOR SecurityDescriptor;  // the SD gate
    QUAD Body;
} OBJECT_HEADER, *POBJECT_HEADER;
```

Offset fields are byte offsets from the header base; `OBJECT_HEADER_TO_NAME_INFO` /
`_TO_CREATOR_INFO` / `TO_QUOTA_INFO` are `(PUCHAR)Header + Offset` casts. The
`Body` member is the address returned to object consumers; conversion is
`OBJECT_TO_OBJECT_HEADER(Obj)` (subtract the `Body` offset) — ReactOS uses a fixed
offset; real Windows computes it from pool layout but the *concept* is identical
(obxrefs everywhere, e.g. `obref.c`).

### 1.3 Handle → object resolution

`ObReferenceObjectByHandle` (obref.c:493) is the gate used everywhere internally
(`ObReferenceObjectByHandleWithRundown` and the `...WithTag` variants share the same
resolution). Algorithm:

1. If `HandleToLong(Handle) < 0`: handle the pseudo-handles `NtCurrentProcess()` (0xFFFFFFFFFFFFFFFF)
   and `NtCurrentThread()` (0xFFFFFFFE). These bypass the table entirely:
   `GrantedAccess = Process->GrantedAccess` (set at startup to `PROCESS_ALL_ACCESS`,
   thread to `THREAD_ALL_ACCESS`, obinit.c). Then it still applies the DesiredAccess
   bitmask (`!(~GrantedAccess & DesiredAccess)`) — kernel mode always wins, user mode
   is denied → `STATUS_ACCESS_DENIED`. Any other `< 0` handle from UserMode ⇒
   `STATUS_INVALID_HANDLE`.
2. Otherwise `KeEnterCriticalRegion()`, `ExMapHandleToPointer(HandleTable, Handle)`.
   - `NULL` ⇒ `STATUS_INVALID_HANDLE`.
   - else `ObpGetHandleObject(Entry)` (mask off `OBJ_HANDLE_ATTRIBUTES` bits), validate
     `ObjectType == NULL || ObjectType == Header->Type` (else `STATUS_OBJECT_TYPE_MISMATCH`),
     then the bitmask test above. KernelMode ⇒ auto-success; UserMode ⇒ deny ⇒
     `STATUS_ACCESS_DENIED`. On success `InterlockedIncrementSizeT(&Header->PointerCount)`.

So the *two-tier* check is: (a) handle exists in the table (`STATUS_INVALID_HANDLE`),
(b) type matches (`STATUS_OBJECT_TYPE_MISMATCH`), (c) GrantedAccess ⊇ DesiredAccess
(`STATUS_ACCESS_DENIED` in UserMode; kernel-mode is unconstrained). This is the crux
for a capability layer: **rights live on the handle entry, not the object.**

### 1.4 The namespace

`ObpRootDirectoryObject` is the singleton `\` root (ObReferenceObjectByHandle on the
kernel handle to `\`). Subdirectories created at init (obinit.c `ObpCreateObjectType`
loop / `ObpCreateDosDevicesDirectory`):

- `\Type` (→ ObpTypeDirectoryObject) — every object type object is registered here by
  name; queried via `NtQuerySystemInformation(SystemObjectTypeInformation)`.
- `\KernelObjects`, `\Device`, `\Driver`, `\KnownType`, `\Sessions\…\DosDevices`, etc.

`OBJECT_DIRECTORY` is a 37-bucket hash map (`NUMBER_HASH_BUCKETS = 37`,
`ntoskrnl/include/internal/ob_x.h`) of `OBJECT_DIRECTORY_ENTRY` singly-linked chains;
lookup is `ObpLookupEntryDirectory` (obdir.c:158). The hash is a custom fold:

```c
for (HashValue = 0; TotalChars; TotalChars--) {
    CurrentChar = *Buffer++;
    HashValue += (HashValue << 1) + (HashValue >> 1);
    if (CurrentChar < 'a') HashValue += CurrentChar;
    else if (CurrentChar > 'z') HashValue += RtlUpcaseUnicodeChar(CurrentChar);
    else HashValue += (CurrentChar - ('a'-'A'));
}
HashIndex = HashValue % NUMBER_HASH_BUCKETS; // 37
```

Case folding is explicit; `OBJ_CASE_INSENSITIVE` drives `RtlEqualUnicodeString(…,TRUE)`.
Directories are matched component-by-component as `UNICODE_STRING` (delimiter
`OBJ_NAME_PATH_SEPARATOR` = `L'\'` = `'\\'`). Path parsing in `ObpLookupObjectName`
(obname.c:446) is a hand-written tokenizer:

1. Resolve the root: a `RootHandle` directory (or `\` → `ObpRootDirectoryObject`),
   or `\??\` → per-device-map `DosDevicesDirectory`.
2. `while (RemainingName.Length) { skip leading '\'; ComponentName = up-to-next-'\' ; }`
   — each component is looked up via `ObpLookupEntryDirectory`, then optionally
   *re-parsed* through the object's `TypeInfo.ParseProcedure` (the symbolic-link
  traverse: `ObpParseSymbolicLink`, max 30 reparsing iterations, else
   `STATUS_OBJECT_NAME_NOT_FOUND`).
3. `ObOpenByKeyName` is ReactOS-internal for bootstrapping; the public
   by-name entry is `NtOpenKey`/`NtOpenFile` with `OBJECT_ATTRIBUTES.RootDirectory`.

The `\\Device` and `\\Driver` directories are not magic — they are ordinary
`OBJECT_DIRECTORY`s with `ObpDirectoryObjectType`, populated by `IoCreateDevice`/`
IoCreateDriver`. The kernel does **not** recurse into a single flat name; it is
strictly hierarchical, so `\Driver\...` and `\Device\...` are disjoint namespaces
whose members are directory entries of device/driver object bodies.

### 1.5 Object type descriptors (the ValidAccessMask / GenericMapping table)

Every type carries its rights model in `OBJECT_TYPE_INITIALIZER.TypeInfo` (the
`OBJECT_TYPE` struct embeds this as `.TypeInfo`, `sdk/include/ndk/obtypes.h`):

| Field | Meaning (implementer's note) |
|---|---|
| `GenericMapping` | `{GenericRead, GenericWrite, GenericExecute, GenericAll}` — fed to `RtlMapGenericMask` so GENERIC_* resolve to type-specific bits. |
| `ValidAccessMask` | The universe of rights the SD/DACL may grant for this type. |
| `SecurityProcedure` | Per-type SD handler; `SeDefaultObjectMethod` (semgr.c:351) dispatches `AssignSecurityDescriptor`/`QuerySecurityDescriptor`/`DeleteSecurityDescriptor`. |
| `OpenProcedure`/`CloseProcedure`/`DeleteProcedure`/`ParseProcedure` | Callouts fired by the OB during create/close/lookup. |
| `SecurityRequired` | if FALSE, handle creation skips the access check (rarely set). |

Concrete `GenericMapping` tables (ReactOS mirrors the real kernel):

```c
/* Type        GenericAll              TypeInfo.ValidAccessMask */
/* Type obj    0x000F0001 = STANDARD |0x1 */     OBJECT_TYPE_ALL_ACCESS = STANDARD_RIGHTS_REQUIRED | OBJECT_TYPE_CREATE /* =0x000F0001 */
/* Directory {GENERIC... }              */      DIRECTORY_ALL_ACCESS = STANDARD_RIGHTS_REQUIRED | 0xF  (then SYNCHRONIZE stripped)
/* File      {FILE_GENERIC_READ/WRITE/EXEC, FILE_ALL_ACCESS} */ FILE_ALL_ACCESS = STANDARD_RIGHTS_REQUIRED | SYNCHRONIZE | 0x1FF
/* Process   {GENERIC... }              */      PROCESS_ALL_ACCESS = STANDARD_RIGHTS_REQUIRED | SYNCHRONIZE | 0xFFFF
/* Thread    {GENERIC... }              */      THREAD_ALL_ACCESS  = STANDARD_RIGHTS_REQUIRED | SYNCHRONIZE | 0x3FF
/* Token     {TOKEN_READ/WRITE/EXEC, TOKEN_ALL_ACCESS} */ TOKEN_ALL_ACCESS = STANDARD_RIGHTS_REQUIRED | TOKEN_ASSIGN_PRIMARY|TOKEN_DUPLICATE|TOKEN_IMPERSONATE|TOKEN_QUERY|...|TOKEN_ADJUST_SESSIONID
/* Section   {STANDARD|SECTION_MAP_READ/WRITE/EXECUTE, SECTION_ALL_ACCESS} */ SECTION_ALL_ACCESS = STANDARD_RIGHTS_REQUIRED| SECTION_QUERY|SECTION_MAP_WRITE|SECTION_MAP_READ|SECTION_MAP_EXECUTE|SECTION_MAP_EXECUTE_EXPLICIT
/* Event/Mutant/Timer */ {STANDARD|type bits, ALL_ACCESS}; SYNCHRONIZE present on exec, SYNCHRONIZE stripped from Directory ValidAccessMask.
```

Constants (`sdk/include/xdk/setypes.h`, `xdk/obtypes.h`, `xdk/iotypes.h`, `ndk/pstypes.h`,
`cmtypes.h`):

```c
/* Standard access */
#define STANDARD_RIGHTS_REQUIRED      0x000F0000L
#define READ_CONTROL                  0x00020000L
#define WRITE_DAC                     0x00040000L
#define WRITE_OWNER                   0x00080000L
#define ACCESS_SYSTEM_SECURITY        0x01000000L
#define SYNCHRONIZE                   0x00100000L
#define MAXIMUM_ALLOWED               0x02000000L
#define GENERIC_READ                  0x80000000L
#define GENERIC_WRITE                 0x40000000L
#define GENERIC_EXECUTE               0x20000000L
#define GENERIC_ALL                   0x10000000L
/* Directory */
#define DIRECTORY_QUERY               0x0001
#define DIRECTORY_TRAVERSE            0x0002
#define DIRECTORY_CREATE_OBJECT       0x0004
#define DIRECTORY_CREATE_SUBDIRECTORY 0x0008
#define DIRECTORY_ALL_ACCESS (STANDARD_RIGHTS_REQUIRED | 0xF)
/* Process (ps/types.h) */
#define PROCESS_VM_OPERATION 0x0008; PROCESS_VM_READ 0x0010; PROCESS_VM_WRITE 0x0020;
#define PROCESS_DUP_HANDLE   0x0040; PROCESS_QUERY_INFORMATION 0x0400;
#define PROCESS_ALL_ACCESS   (STANDARD_RIGHTS_REQUIRED | SYNCHRONIZE | 0xFFFF)
/* Thread */
#define THREAD_QUERY_INFORMATION 0x0040; THREAD_GET_CONTEXT 0x0008; THREAD_SET_CONTEXT 0x0010;
#define THREAD_TERMINATE 0x0001; THREAD_SUSPEND_RESUME 0x0002; THREAD_ALERT 0x0004
#define THREAD_ALL_ACCESS (STANDARD_RIGHTS_REQUIRED | SYNCHRONIZE | 0x3FF)
/* File */
#define FILE_READ_DATA 1; FILE_WRITE_DATA 2; FILE_APPEND_DATA 4; FILE_READ_ATTRIBUTES 0x80; FILE_WRITE_ATTRIBUTES 0x100
#define FILE_GENERIC_READ  (STANDARD_RIGHTS_READ|FILE_READ_DATA|FILE_READ_ATTRIBUTES|FILE_READ_CONTROL|SYNCHRONIZE)
#define FILE_ALL_ACCESS    (STANDARD_RIGHTS_REQUIRED|SYNCHRONIZE|0x1FF)
/* Key */
#define KEY_QUERY_VALUE 1; KEY_SET_VALUE 2; KEY_CREATE_SUB_KEY 4; KEY_NOTIFY 16; KEY_CREATE_LINK 32
#define KEY_READ  0x20019; KEY_WRITE 0x20006; KEY_ALL_ACCESS 0xf003f
/* Token */
#define TOKEN_ASSIGN_PRIMARY   0x0001; TOKEN_DUPLICATE 0x0002; TOKEN_IMPERSONATE 0x0004; TOKEN_QUERY 0x0008
#define TOKEN_ADJUST_PRIVILEGES 0x20; TOKEN_ADJUST_GROUPS 0x40; TOKEN_ADJUST_DEFAULT 0x80
#define TOKEN_READ  (STANDARD_RIGHTS_READ | TOKEN_QUERY)
#define TOKEN_ALL_ACCESS_P (STANDARD_RIGHTS_REQUIRED|TOKEN_ASSIGN_PRIMARY|TOKEN_DUPLICATE|TOKEN_IMPERSONATE|TOKEN_QUERY|TOKEN_ADJUST_PRIVILEGES|TOKEN_ADJUST_GROUPS|TOKEN_ADJUST_DEFAULT)
```

### 1.6 Object Attributes (the path passed in)

```c
typedef struct _OBJECT_ATTRIBUTES {
    ULONG           Length;
    HANDLE          RootDirectory;        /* optional parent dir handle       */
    PUNICODE_STRING ObjectName;           /* e.g. L"\Driver\Foo"              */
    ULONG           Attributes;           /* OBJ_* bitmask below              */
    PVOID           SecurityDescriptor;
    PVOID           SecurityQualityOfService; /* for named pipes / impersonation */
} OBJECT_ATTRIBUTES, *POBJECT_ATTRIBUTES, *PCOBJECT_ATTRIBUTES;

#define InitializeObjectAttributes(p,n,a,r,s) { \
  (p)->Length = sizeof(OBJECT_ATTRIBUTES); (p)->RootDirectory = r; \
  (p)->Attributes = a; (p)->ObjectName = n; (p)->SecurityDescriptor = s; \
  (p)->SecurityQualityOfService = NULL; }

#define OBJ_HANDLE_TAGBITS        0x00000003L
#define OBJ_INHERIT               0x00000002L
#define OBJ_PERMANENT             0x00000010L   /* survives when HandleCount -> 0  */
#define OBJ_EXCLUSIVE             0x00000020L   /* one opener only                */
#define OBJ_CASE_INSENSITIVE      0x00000040L
#define OBJ_OPENIF                0x00000080L
#define OBJ_OPENLINK              0x00000100L
#define OBJ_KERNEL_HANDLE         0x00000200L
#define OBJ_FORCE_ACCESS_CHECK    0x00000400L
#define OBJ_VALID_ATTRIBUTES      0x000007F2L
#define OBJ_PROTECT_CLOSE         0x00000001L   /* win32 side: prevent NtClose */
#define OBJ_AUDIT_OBJECT_CLOSE    0x00000004L   /* win32 side: enable close audit*/
```

`ObOpenByKeyName` (obhandle.c in ReactOS) is *not* a public kernel routine — the
public path is the user `NtOpenFile`/`NtOpenKey` which build an `OBJECT_ATTRIBUTES`
with `ObjectName` + optional `RootDirectory` handle and call `ObpLookupObjectName`.

---

## 2. The access check pipeline: handle → SD → SRM

### 2.1 Call chain

```
NtOpenFile / NtOpenKey / NtCreate*  → ObpCreateHandle / ObCheckObjectAccess
NtClose / NtQuery* / NtSet*         → ObReferenceObjectByHandle  → SeAccessCheck
                                         ^ (handle exists? type ok?)     ^ (token vs SD)
```

`ObReferenceObjectByHandle(Handle, DesiredAccess, ObjectType, AccessMode, &Obj, &Info)` (obref.c:493):
resolves the handle entry; **it itself does the bitmask gate**
`!(~GrantedAccess & DesiredAccess)`. In UserMode this returns `STATUS_ACCESS_DENIED`;
kernel-mode is allowed through (this is why drivers can "elevate"). Only if it
passes does the *object body* get returned — and the *creation* path (`ObpIncrementHandleCount`,
obhandle.c:811, called from `NtOpenFile`) additionally runs `ObCheckObjectAccess` →
`SeAccessCheck` against the live SD. So there are **two** check sites:
(a) handle-granted-access bitmask (cheap), (b) full SD check at *open/create* time.
A capability layer should mirror both: gate on GrantedAccess for every *use*, and
re-check the SD only when minting a new authority (duplicating/opening).

### 2.2 SeAccessCheck (wdm.h)

`BOOLEAN SeAccessCheck(SecurityDescriptor, SubjectContext, SubjectContextLocked,
DesiredAccess, PreviouslyGrantedAccess, &Privileges, GenericMapping, AccessMode,
&GrantedAccess, &AccessStatus)` (accesschk.c:1994). Returns TRUE/FALSE; the caller
must use the out `AccessStatus` (the WDK explicitly says *do not* hardcode
STATUS_ACCESS_DENIED) — ReactOS copies this in comments.

Kernel-mode short-circuit (accesschk.c:2023): if `AccessMode == KernelMode`,
- `MAXIMUM_ALLOWED` ⇒ `*GrantedAccess = GenericAll | (DesiredAccess & ~MAXIMUM_ALLOWED) | PreviouslyGrantedAccess`, return `STATUS_SUCCESS`;
- else `*GrantedAccess = DesiredAccess | PreviouslyGrantedAccess`, success. **No SD read.**

User-mode path:
1. NULL SD ⇒ `STATUS_ACCESS_DENIED` (auto-fail).
2. Impersonation validity: `ClientToken != NULL && ImpersonationLevel < SecurityImpersonation` ⇒
   `STATUS_BAD_IMPERSONATION_LEVEL`.
3. `SeLockSubjectContext` (acquire token locks — `SECURITY_SUBJECT_CONTEXT {ClientToken, ImpersonationLevel, PrimaryToken, ProcessAuditId}`).
4. **Owner shortcut**: if `DesiredAccess & (WRITE_DAC|READ_CONTROL|MAXIMUM_ALLOWED)` and the caller *is* the object owner
   (`SepTokenIsOwner`) ⇒ those rights are pre-granted (READ_CONTROL/WRITE_DAC) and removed from the DACL walk.
5. `SePrivilegePolicyCheck` strips `ACCESS_SYSTEM_SECURITY` (needs `SeSecurityPrivilege`)
   and `WRITE_OWNER` (needs `SeTakeOwnershipPrivilege`) from `RemainingAccess` and folds them
   into `GrantedAccess`. `ACCESS_SYSTEM_SECURITY` *without* `SeSecurityPrivilege` ⇒ immediate
   `STATUS_PRIVILEGE_NOT_HELD` (priv.c `SePrivilegePolicyCheck`: returns `STATUS_PRIVILEGE_NOT_HELD` on the security-privilege failure). Note: missing `SeTakeOwnershipPrivilege` does **not** itself return that code — it merely stops adding WRITE_OWNER, and the residual falls through to the DACL (so a non-owner with no WRITE_DAC ends at `STATUS_ACCESS_DENIED`).
6. If `RemainingAccess == 0` ⇒ `STATUS_SUCCESS` (all requested rights were privilege-backed).
7. `RtlGetDaclSecurityDescriptor(&Present,&Dacl,&Defaulted)`:
   - `!Present` (no DACL) ⇒ **grant everything** (`PreviouslyGrantedAccess |= RemainingAccess`); `MAXIMUM_ALLOWED` resolves to `GenericAll`. This is the "null DACL = full access" rule.
   - `Dacl->AceCount == 0` (empty DACL ⇒ deny) ⇒ `STATUS_ACCESS_DENIED` (unless `MAXIMUM_ALLOWED` and previously granted >0, then success — the only exception to the empty-DACL deny).
8. Walk the DACL with `SepAnalyzeAcesFromDacl`. Ordering rules implemented in the walker
   (accesschk.c:460 `SepDenyAccessObjectTypeList`/`SepAllowAccessObjectTypeList`,
   `SepAnalyzeAcesFromDacl`):
   - DENY ACEs are evaluated first and accumulate `DeniedAccessRights`; an ACE whose SID is in the token (with deny-only/restricted handling) strips those bits.
   - ALLOW ACEs accumulate `GrantedAccessRights = (Access & ~DeniedAccessRights)`.
   - **Deny wins over allow** — the standard NT rule; ReactOS's `SepAnalyzeAcesFromDacl` computes
     `GrantedAccessRights |= (Access & ~DeniedAccessRights)` so a later allow can't resurrect a denied bit.
   - Object-type ACEs (`ACCESS_ALLOWED_OBJECT_ACE_TYPE` 0x5 / `ACCESS_DENIED_OBJECT_ACE_TYPE` 0x6) are matched only when the caller supplied an `OBJECT_TYPE_LIST` hierarchy (level 0..4, `winnt.h` `OBJECT_TYPE_LIST {WORD Level; WORD Sbz; GUID *ObjectType}` — only meaningful for AD/directory-service objects).
   - **Two-pass for restricted tokens**: if `SeTokenIsRestricted(Token)`, the DACL is walked a *second* time against the token's *restricting SIDs* (the `IsTokenRestricted` branch in `SepAccessCheckWorker`); access is granted **only if both passes** yield the requested rights. (MS: "the system performs two access checks … Access is granted only if both access checks allow" — restricted-tokens doc.)
9. After the DACL walk, residual `RemainingAccessRights != 0` ⇒ `PreviouslyGrantedAccess=0`, `STATUS_ACCESS_DENIED`.

Then — ReactOS omits it, **Windows** additionally runs the **Mandatory Integrity Check**
(see §2.3) which is applied *in the kernel* (not usermode) and can *carve granted access
down* (e.g. NO_WRITE_UP). ReactOS has **no MIC implementation** (none of `SeTestMandatoryIntegrityControl`,
`TOKEN_MANDATORY_LABEL`, `SYSTEM_MANDATORY_LABEL_ACE_TYPE` appear in `ntoskrnl/se`), so a
faithful port must add this layer itself.

`SeFastTraverseCheck` (accesschk.c:2138) is the *fast path* used during name parsing
for the `DIRECTORY_TRAVERSE` check (obname.c:695) — it short-circuits the full
`SeAccessCheck` by scanning only for a `SeWorldSid` (`S-1-1-0`, Everyone) ALLOW ACE
covering `DesiredAccess`; if found, traverse is permitted *only* for a
non-restricted token; otherwise it falls through to the full check.

### 2.3 Security descriptor & MIC (mandatory integrity)

`SECURITY_DESCRIPTOR` (winnt.h) is the `ObpGetHeaderForSd`-cached structure
(`sd.c`/`obsdcach.c`). The kernel keeps a process-wide cache of SDs keyed by
`(SID, Flags)`; `ObGetObjectSecurity` returns the cached, self-relative SD
(`sdk/include/xdk/winnt.h` `SECURITY_DESCRIPTOR`). An object with no explicit SD
(`SecurityDescriptor == NULL`) is treated as **unprotected** and the caller is
granted `GenericAll & ValidAccessMask` (sd.c `ObGetObjectSecurity`).

**Mandatory Integrity Control** (Windows Vista+), MS-DOC
`learn.microsoft.com/.../mandatory-integrity-control`, evaluated before the DACL:

- The **subject** integrity level is the SID in the access token that carries
  `SE_GROUP_INTEGRITY` (0x20), with `SE_GROUP_INTEGRITY_ENABLED` (0x40) meaning it
  is active. `TOKEN_MANDATORY_LABEL {SID_AND_ATTRIBUTES Label}` holds it; queried via
  `NtQueryInformationToken(TokenIntegrityLevel)`.
- The **object** integrity level is the `SYSTEM_MANDATORY_LABEL_ACE` (AceType 0x11)
  in the object's **SACL**. Its `SidStart` is a `SECURITY_MANDATORY_LABEL_AUTHORITY {0,0,0,0,0,16}` SID whose RID is the object IL.
- Integrity SIDs (RID of the label SID, the 4th subauth):
  `SECURITY_MANDATORY_UNTRUSTED_RID 0x0000`, `LOW_RID 0x1000`,
  `MEDIUM_RID 0x2000` (default for unlabeled objects), `HIGH_RID 0x3000`,
  `SYSTEM_RID 0x4000`. String form `S-1-16-NNNN`.
- `SYSTEM_MANDATORY_LABEL_ACE_TYPE` Mask is the **lower-IL policy**:
  `SYSTEM_MANDATORY_LABEL_NO_WRITE_UP 0x1` (default on every object), `NO_READ_UP 0x2`,
  `NO_EXECUTE_UP 0x4`. Evaluation: if `TokenIL < ObjectIL`, the requested access
  (WRITE_, READ_, EXECUTE_ respectively) is *carved out* of the granted set; if
  after carving *nothing* remains and the access is a write to a higher-IL object,
  the result is `STATUS_ACCESS_DENIED` (in real Windows, via `SeSatisfiesSecurityDescriptor`/
  `SeTestMandatoryIntegrityControl` inside `SeAccessCheck`).

Two token-level mandatory policy flags (`TOKEN_MANDATORY_POLICY`):
`TOKEN_MANDATORY_NO_WRITE_UP` (default — subject cannot write up to a higher-IL object)
and `TOKEN_MANDATORY_NEW_PROCESS_MIN` (child gets min(parent IL, image IL)).
AppContainer is a **Low** IL (0x1000) process by default.

### 2.4 Privileges & the token

`SeSinglePrivilegeCheck(Luid, PreviousMode)` (priv.c:744) is the per-call entry: it
captures the subject context, builds a 1-element `PRIVILEGE_SET {PrivilegeCount=1,
Control=PRIVILEGE_SET_ALL_NECESSARY, Privilege[0]={Luid, SE_PRIVILEGE_ENABLED}}`,
and calls `SePrivilegeCheck` → `SepPrivilegeCheck(Token, [Luid], 1, PRIVILEGE_SET_ALL_NECESSARY, PreviousMode)`.
The enabledness test is `Attributes & SE_PRIVILEGE_ENABLED` (0x00000002) with
`SE_PRIVILEGE_ENABLED_BY_DEFAULT` (0x00000001) for auto-enabled-by-default privs.
Privilege LUIDs (`sdk/include/xdk/setypes.h`):
`SE_CREATE_TOKEN_PRIVILEGE 2`, `SE_TCB_PRIVILEGE 7` (`SeTcbPrivilege`),
`SE_ASSIGNPRIMARYTOKEN_PRIVILEGE`, `SE_INCREASE_QUOTA_PRIVILEGE`,
`SE_DEBUG_PRIVILEGE 20`, `SE_SECURITY_PRIVILEGE` (for ACCESS_SYSTEM_SECURITY),
`SE_TAKE_OWNERSHIP_PRIVILEGE` (for WRITE_OWNER), `SE_CREATE_GLOBAL_PRIVILEGE`,
`SE_BACKUP/RESTORE_PRIVILEGE`. Privileges are **not** access rights on the handle;
they gate *system-global* operations and the `ACCESS_SYSTEM_SECURITY`/`WRITE_OWNER`
sidecar of an access check.

---

## 3. NTSTATUS denial conventions (the precise codes)

These are the actual codes returned from the ReactOS call sites — which match
the documented Windows contract:

| Code | Hex | Returned when | Source site |
|---|---|---|---|
| `STATUS_SUCCESS` | 0x00000000 | access granted / handle valid | all |
| `STATUS_INVALID_HANDLE` | 0xC0000008 | handle not in table; pseudo-handle from UserMode | `ObReferenceObjectByHandle` (obref.c:642 `<0` branch); `ObpReferenceProcessObjectByHandle` NULL-entry |
| `STATUS_OBJECT_TYPE_MISMATCH` | 0xC0000024 | `ObjectType != Header->Type` | obref.c:655 |
| `STATUS_ACCESS_DENIED` | 0xC0000022 | UserMode + `(~GrantedAccess & DesiredAccess) != 0`; or DACL/owner/mandatory deny; empty DACL | obref.c:598 (`ObpReferenceProcessObjectByHandle`), `SeAccessCheck` DACL path, `ObpIncrementHandleCount` (exclusive) |
| `STATUS_PRIVILEGE_NOT_HELD` | 0xC0000061 | `ACCESS_SYSTEM_SECURITY` requested without `SeSecurityPrivilege` (does **not** fire for WRITE_OWNER) | `SePrivilegePolicyCheck` (priv.c:280) |
| `STATUS_OBJECT_NAME_INVALID` | 0xC0000033 | empty path component | obname.c:752 `ComponentName.Length==0` |
| `STATUS_OBJECT_PATH_NOT_FOUND` | 0xC000003A | intermediate component absent | obname.c:762 |
| `STATUS_OBJECT_PATH_SYNTAX_BAD` | 0xC000003B | name doesn't begin with `\` (without root) | obname.c:486 |
| `STATUS_OBJECT_NAME_NOT_FOUND` | 0xC0000034 | leaf absent (no insert), or reparse exhausted | obname.c:774, 510 |
| `STATUS_HANDLE_NOT_CLOSABLE` | 0xC0000235 | `OkayToCloseProcedure` returned FALSE | ObpCloseHandleTableEntry (obhandle.c:735) |
| `STATUS_UNSUCCESSFUL` | 0xC0000001 | object re-opened past 0 handles with only a CloseProcedure | `ObpIncrementHandleCount` (obhandle.c:935) |
| `STATUS_PROCESS_IS_TERMINATING` | 0xC000010A | target handle table gone | ObDuplicateObject |
| `STATUS_INSUFFICIENT_RESOURCES` / `STATUS_NO_MEMORY` | 0xC000009A / 0xC0000017 | pool/hash-table exhaustion | ObpCreateHandle |

**Key implementer distinction.** Do **not** invent a `STATUS_OBJECT_HANDLE_NOT_GRANTED_ACCESS`;
the public NTSTATUS contract has no such value and ReactOS returns the plain
`STATUS_ACCESS_DENIED` for any GrantedAccess-shortfall in UserMode. If a future
closed-NT header adds it, it will be surfaced via the returned `AccessStatus`
out-param of `SeAccessCheck` — the WDK rule is: on `SeAccessCheck` failure, return
the caller's `AccessStatus`, never hardcode the code. This is exactly why a
capability layer must thread `AccessStatus` through its deny path instead of
collapsing every denial to a single enum.

---

## 4. DesiredAccess vs GrantedAccess: creating handles with reduced rights

A handle is minted with exactly `GrantedAccess = PreviouslyGrantedAccess &
ValidAccessMask` (obhandle.c `ObpCreateHandle` line 1623-1629):

```c
GrantedAccess = AccessState->RemainingDesiredAccess |
                AccessState->PreviouslyGrantedAccess;
GrantedAccess &= (ObjectType->TypeInfo.ValidAccessMask | ACCESS_SYSTEM_SECURITY);
AccessState->PreviouslyGrantedAccess = GrantedAccess;
NewEntry.GrantedAccess = GrantedAccess;
```

`PreviouslyGrantedAccess` accumulates across nested opens. The handle therefore
**never holds more rights than the SD allowed at open time**, and those bits are
baked into `HANDLE_TABLE_ENTRY.GrantedAccess`. The handle never gets *more* rights
than the object allows.

`ObReferenceObjectByHandle` then *re-checks* the caller's `DesiredAccess <=
GrantedAccess` (obref.c:599 `!(~GrantedAccess & DesiredAccess)`). So an operation
that opens a handle for `KEY_READ` cannot later pass `KEY_SET_VALUE` and succeed:
the second argument is compared against the *handle's* granted access, **not** the
object's full rights.

`NtDuplicateObject` (obhandle.c:2207) is where reduced rights are engineered. With
`DUPLICATE_SAME_ACCESS` clear, `DesiredAccess` is taken from the caller:

```c
if (Options & DUPLICATE_SAME_ACCESS) DesiredAccess = SourceAccess; /* from handle */
if (DesiredAccess & GENERIC_ACCESS) RtlMapGenericMask(&DesiredAccess, &ObjectType->TypeInfo.GenericMapping);
TargetAccess = DesiredAccess & (ObjectType->TypeInfo.ValidAccessMask | ACCESS_SYSTEM_SECURITY);
NewEntry.GrantedAccess = TargetAccess;
/* if the new handle wants rights the source did NOT have -> re-check the SD */
if (TargetAccess & ~SourceAccess) {
    if (SecurityProcedure != SeDefaultObjectMethod) Status = STATUS_ACCESS_DENIED; /* cannot elevate */
    else { SeCreateAccessState(...); Status = ObCheckObjectAccess(...) (full SeAccessCheck vs SD) }
}
```

Semantics the layer needs verbatim:
- **Reducing rights on a duplicate is always allowed** (no SD re-check): you cannot
  gain a right you don't already hold, but you can always narrow. `TargetAccess & ~SourceAccess == 0`.
- **Expanding rights is denied unless the current token also passes a full SD check**
  against the object. Kernel-mode duplicates that try to add `ACCESS_SYSTEM_SECURITY`
  are blocked (`SeDefaultObjectMethod` path still runs SeAccessCheck in UserMode-equivalent
  ProbeMode). So a handle opened as `KEY_READ` cannot be duplicated as `KEY_ALL_ACCESS`
  unless the duplicator's own SD check passes.
- `DUPLICATE_CLOSE_SOURCE` (0x1): closes the source handle *after* (regardless of
  failure). `DUPLICATE_SAME_ATTRIBUTES` (0x4) and `DUPLICATE_SAME_ACCESS` (0x2).
- The Win32 wrapper `DuplicateHandle` (handleapi) adds `OBJ_INHERIT`/`OBJ_PROTECT_CLOSE`
  translation; the NT path itself knows only the bit flags above.

This is precisely the **capability-style attenuation** NT gives you: a handle is an
unforgeable token of a fixed rights subset, and `NtDuplicateObject` is the *only*
reducing transform — there is no "drop individual bits on an existing handle"
primitive.

---

## 5. Revocation: what NT reclaims vs. what it cannot express

### 5.1 What actually happens on close / exit / delete

`NtClose` → `ObpCloseHandle` (obhandle.c:1730) → `ObpCloseHandleTableEntry`.

`ObpCloseHandleTableEntry` (obhandle.c:685):
1. Optional `OkayToCloseProcedure` (per-type) can veto → `STATUS_HANDLE_NOT_CLOSABLE`
   (obhandle.c:735). If `ObpAccessProtectCloseBit` is set and `AccessMode != KernelMode`
   and `IgnoreHandleProtection==FALSE`, the close is **vetoed** (obhandle.c:748) — this is
   the single revocation-adjacent feature: an opener can make its handle **non-closeable**
   from user mode (the Win32 `SetHandleInformation(..., HANDLE_FLAG_PROTECT_FROM_CLOSE)`
   → `OBJ_PROTECT_CLOSE` → `ObpAccessProtectCloseBit`). Only kernel mode can then close it.
2. `ObpDecrementHandleCount` (obhandle.c `ObpDecrementHandleCount`/decrement path):
   `InterlockedDecrementSizeT(&Header->HandleCount)`; if it hits 0 and the type
   `DeleteProcedure` is set, it queues the object to `ObpReaperList`
   (`ExQueueWorkItem(&ObpReaperWorkItem, CriticalWorkQueue)`).
3. The handle-table entry is freed (`ExFreeHandle`).
4. The reaper thread (`ObpReapObject`, oblife.c:225) calls `ObpDeleteObject(&Entry->Body, TRUE)`.

`ObpDeleteObject` (oblife.c:147):
- removes from `Type->TypeList` (`RemoveEntryList(&CreatorInfo->TypeList)`),
- frees `ObjectNameInfo->Name.Buffer`,
- calls `Type->TypeInfo.SecurityProcedure(..., DeleteSecurityDescriptor, &Header->SecurityDescriptor)`
  (so the SD is reclaimed),
- calls `Type->TypeInfo.DeleteProcedure(Object)` if present,
- `ObpDeallocateObject(Object)` frees the body.

`ObDereferenceObject`/`ObDereferenceObjectEx` (obref.c) decrements `PointerCount`;
when `PointerCount` reaches 0 *and* `HandleCount` is already 0, the same reaper path
fires (`NewCount == 0 => ObpDeferObjectDeletion` queues to `ObpReaperList`).

### 5.2 Process termination

`PsLookupProcessByProcessId` + `PsExitProcess` walks `Process->ObjectTable` and
calls `ObpCloseHandle` on **every** entry (`ObpCloseHandleTable` iteration), then
`ObDestroyHandleTable`. So killing a process reclaims all *its* handles but does
**not** touch aliases held by other processes.

### 5.3 The revocation gap (concrete)

Classic NT has **no per-object, from-all-holders revocable primitive**. Specifically:

- There is no kernel routine to enumerate "all handles to this object" and invalidate
  them. `OBJECT_HEADER.HandleCount` is a count, **not** a list — the handle table is
  *per-process* and keyed by handle value, not by object. ReactOS (and Windows) store
  no reverse index from object → handle(s) (no `ObReferenceObjectByPointer`-style
  reverse link). You cannot walk "all openers".
- `ObpDeleteObject` runs only at refcount 0; a live handle (even with `GrantedAccess==0`)
  keeps the object alive and the handle remains usable until explicitly closed. Revoking
  by clearing `GrantedAccess` on a handle entry is not a supported operation — the
  table entry is read-only between open and close.
- `OBJ_PROTECT_CLOSE` (§5.1) protects *close*, not *access*; it hardens against
  accidental `NtClose`, not against authority removal.
- `NtMakeTemporaryObject`/`NtMakePermanentObject` toggle only the
  `OB_FLAG_PERMANENT` (`OBJ_PERMANENT`) bit (lifespan-vs-handlecount-0); they do not
  revoke access.
- Protected Process / PPL (`PsProtected` / `SeILSigningPolicy`) prevents *opening*
  handles, again not revocation of existing ones.

**Therefore NT is capability-*style* (handles are unforgeable, rights-attached,
attenuatable by duplication) but NOT capability-*safe* with respect to revocation**: a
"revocate all holders" operation (the seL4 `TCB_REVOKE`/`ObRetype`-equivalent) requires
walking every process handle table (O(processes × handle-slots)), which Windows does
only for the one victim on exit — there is no single syscall that atomically invalidates
all references to an object across processes. This is the gap the wubu_cap
`handle_revoke_by_slot / revoke_handle` model closes by *adding* an audience check that
survives the handle record.

---

## 6. NT analogues of capability authority (Win10/11)

### 6.1 Restricted tokens — two-factor SD checks
`CreateRestrictedToken` (sec_authz `Restricted Tokens` doc, also
`learn.microsoft.com/.../restricted-tokens`) produces a token that:
- can drop privileges (PrivilegesRemoved),
- marks SIDs `SE_GROUP_USE_FOR_DENY_ONLY` (deny-only: the SID is still checked against
  **deny** ACEs but **not** against allow ACEs),
- adds a **restricting SID** list.

The SR M then does a **two-pass** `SeAccessCheck`: the primary SID set **AND** the
restricting SID set must each independently grant the requested access
(`SeTokenIsRestricted(Token)` is the ReactOS two-pass toggle in `SepAccessCheckWorker`;
MS: "Access is granted only if both access checks allow"). A restricted token thus
behaves like a *narrowed capability* — it can never exceed what the restrictive policy allows,
even if a DACL would otherwise allow it.

### 6.2 AppContainer / LowBox — capability SIDs on the token
AppContainer (Win8+) puts a **Package SID** (`SECURITY_APP_PACKAGE_AUTHORITY {0,0,0,0,0,15}`,
RID derived from the package name) plus one or more **capability SIDs**
(`SECURITY_CAPABILITY_BASE_RID 0x3`; capability RIDs like `INTERNET_CLIENT_CAPABILITY_…`)
on the token, and runs at **Low IL** (0x1000). Access to a resource requires the
object's DACL to grant access to *both* the user/group SIDs **and** the package/
capability SIDs (the intersection), **and** the MIC check (Low ≤ object IL) must pass.
`NtCreateLowBoxToken`/`CreateAppContainerProfile`/`DeriveCapabilitySidsFromName`
construct these. `SECURITY_CAPABILITY_APP_RID 0x400`, `SECURITY_BUILTIN_PACKAGE_ANY_PACKAGE 1`,
`SECURITY_CAPABILITY_RID_COUNT 5`. This is the closest NT analogue to a delegated,
rights-bounded capability set: the capability SID *is* the authority token, but it is
bound to a **process token**, not to an individual handle — i.e. it is ambient authority
shared by all handles of that process, exactly the property a per-handle cap model
removes.

### 6.3 Token-mandated limits vs. handle caps
| Concern | NT mechanism | Capability analogue |
|---|---|---|
| unforgeable authority token | handle value (index into per-proc table, kernel-validated) | yes — a handle is unforgeable in UserMode |
| rights attachment | `GRANTED_ACCESS` on `HANDLE_TABLE_ENTRY`, checked each use | yes — `handle.GrantedAccess ⊇ DesiredAccess` |
| attenuation | `NtDuplicateObject` with reduced `DesiredAccess` | yes — the only shrink op |
| **revocation-from-all-holders** | **none** (§5.3) | **no** — NT lacks this |
| delegation across processes | `NtDuplicateObject` (needs `PROCESS_DUP_HANDLE` 0x40 on both procs + SD re-check to expand) | partial — cross-proc dup exists |
| mandatory lowering | MIC / AppContainer Low IL | partial — system-mandated, not per-handle |
| restricted/least privilege | restricted token (deny-only + restricting SIDs) / AppContainer package caps | partial — ambient, per-token not per-handle |

---

## Source map

Implementation files (ReactOS `reactos/reactos`, commit `71ee7547`):
- `ntoskrnl/ob/obhandle.c` — `ObpCreateHandle`, `ObpIncrementHandleCount`,
  `ObpCloseHandle`, `ObpCloseHandleTableEntry`, `ObpDuplicateObject` (handle-create/close/dup gates).
- `ntoskrnl/ob/obref.c` — `ObReferenceObjectByHandle` (the handle→object gate + bitmask),
  `ObpDeferObjectDeletion`.
- `ntoskrnl/ob/obname.c` — `ObpLookupObjectName` (UNICODE_STRING tokenizer + reparse loop).
- `ntoskrnl/ob/obdir.c` — `ObpLookupEntryDirectory` (hash fold `% 37`).
- `ntoskrnl/ob/obsecure.c` — `ObCheckObjectAccess`, `ObCheckCreateObjectAccess`,
  `ObpCheckTraverseAccess`, `ObAssignSecurity`.
- `ntoskrnl/ob/oblife.c` — `ObpDeleteObject`, `ObpReapObject` (reclamation).
- `ntoskrnl/se/accesschk.c` — `SeAccessCheck`, `SepAccessCheckWorker`,
  `SepAnalyzeAcesFromDacl`, `SeFastTraverseCheck` (deny-wins, two-pass restricted).
- `ntoskrnl/se/priv.c` — `SePrivilegePolicyCheck`, `SeSinglePrivilegeCheck`,
  `SePrivilegeCheck` (`STATUS_PRIVILEGE_NOT_HELD`).
- `ntoskrnl/se/semgr.c` — `SeDefaultObjectMethod` (SecurityProcedure dispatch).
- Headers: `sdk/include/ndk/obtypes.h` (`OBJECT_HEADER`, `_OBJECT_DIRECTORY`,
  `DIRECTORY_*`), `sdk/include/ndk/extypes.h` (`_HANDLE_TABLE[_ENTRY]`),
  `sdk/include/ndk/setypes.h` (`ACE_HEADER`, ACE types, `SECURITY_SUBJECT_CONTEXT`,
  `ACCESS_STATE`, privilege LUIDs, SID attribute flags, integrity SIDs),
  `sdk/include/xdk/ntdef.template.h` (`OBJECT_ATTRIBUTES`, `OBJ_*`),
  `sdk/include/xdk/obtypes.h` (`DIRECTORY_*`/`DUPLICATE_*`),
  `sdk/include/xdk/iotypes.h` (`FILE_GENERIC_*`), `sdk/include/ndk/pstypes.h`
  (`PROCESS_*`/`THREAD_*` masks). Generic-mapping tables (identity for the
  mapping layer): `ntoskrnl/se/token.c` (`SepTokenMapping`), `ntoskrnl/ps/psmgr.c`
  (`PspProcessMapping`/`PspThreadMapping`, `GrantedAccess` defaults at obinit.c:326),
  `ntoskrnl/io/iomgr/iomgr.c` (`IopFileMapping`), `ntoskrnl/mm/section.c`
  (`MmpSectionMapping`), `ntoskrnl/ex/event|mutant|timer|keyedevt.c`.

Published Microsoft contract:
- `ObReferenceObjectByHandle` — WDK: `learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/nf-wdm-obreferenceobjectbyhandle`
- `SeAccessCheck` — WDK: `learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/nf-wdm-seaccesscheck`
- MIC: `learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control`
- `TOKEN_MANDATORY_LABEL`: `learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-token_mandatory_label`
- `SYSTEM_MANDATORY_LABEL_ACE`: `learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-system_mandatory_label_ace`
- Restricted tokens: `learn.microsoft.com/en-us/windows/win32/secauthz/restricted-tokens`
- AppContainer: `learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer`,
  constants `learn.microsoft.com/en-us/windows/win32/secauthz/app-container-sid-constants`
- `NtDuplicateObject` (ntdoc mirror of WDK): `ntdoc.m417z.com/ntduplicateobject`
- DACL ordering/ACE semantics: `learn.microsoft.com/en-us/windows/win32/secauthz/how-dacls-control-access-to-an-object`
- NTSTATUS values: MS-ERREF `learn.microsoft.com/en-us/openspecs/windows_protocols/ms-erref/596a1078-e883-4972-9bbc-49e60bebca55`
  (cross-checked against `sdk/include/psdk/ntstatus.h`; 0xC0000717 = `STATUS_NO_UNICODE_TRANSLATION`,
  so there is no distinct "handle-not-granted" code in the public contract).
- Conceptual background: Russinovich/Solomon/Ionescu, *Windows Internals* 7th ed.,
  Ch. 3 (process/thread tokens & privileges), Ch. 9–10 (Object Manager + SRM). ReactOS
  source (above) is the authoritative reverse-engineered stand-in for the closed kernel
  internals; where ReactOS omits a feature (MIC), the Microsoft docs fill the gap.
