# M07 Disposable-Volume Recovery Harness

Status: **unelevated dry-run source implemented and statically verified; not executed against a volume or child process**

This document defines a fail-closed recovery test for the Windows local-NTFS
report publication path in
`Tools/verify_redmmo_content_storage_restore.py`. It does not authorize disk
creation, formatting, attachment, process termination, VM power-off, project
copying, restore verification, or cleanup.

The current publisher has this order:

1. create an exclusive write-through staging file relative to a retained parent;
2. write the payload and flush that file;
3. validate the staging-file identity;
4. rename it without replacement through the retained parent;
5. flush the same file handle after the rename;
6. validate the final path and set an in-process `committed` flag.

That flag is process memory. An exact final file after a terminated worker is
therefore not enough to claim a committed operation. Only an authenticated
`COMPLETE` acknowledgement followed by a clean worker exit, plus a fresh-process
scan of the exact final file and namespace, may classify a case as `committed`.

The machine-readable contract is
`docs/M07_DISPOSABLE_VOLUME_RECOVERY_HARNESS_PLAN.json`.

## Safety boundary

The harness must have three separately reviewable programs:

- an unelevated controller that authenticates the plan, owns the worker, records
  a nonce-bound checkpoint transcript, and publishes evidence;
- an unelevated one-case worker that calls the production
  `write_report_atomic` path with a tiny synthetic payload;
- an optional privileged provisioning broker that owns only the VHDX
  create/attach/mount and exact-handle detach lifecycle.

The first implementation now provides the authenticated controller-side dry-run
validator, deterministic checkpoint/classification contract, production
publication hooks, and a private one-case worker body. Worker execution remains
hard-disabled: no child process, volume observation, write trace, recovery scan,
or interruption has run. It must not create, initialize, format, attach, detach,
offline, delete, or power-cycle any disk. The optional broker and any live worker
execution are later, separately authorized implementation slices.

Every run and every case is single-use. The controller must refuse reuse,
overwrite, reparse points, network namespaces, ambiguous device identity, an
unavailable write trace, or any path outside the allowlist. No worker may write
under the repository, user profile, vendor staging, packaged-build,
diagnostics, or user-temporary roots. Worker current directory, temporary
directory, Python bytecode cache, payload, and report must all resolve inside
the disposable volume.

The control ledger is outside the disposable volume at the exact run-specific
path declared by the signed plan. Failed case volumes and ledgers are preserved
by default. Cleanup is a later explicit operation and may act only on the
recorded image, mount, and native identities after exact detachment has been
verified. Broad recursive deletion is forbidden.

## Disposable VHDX lifecycle design

The future provisioning broker uses one fresh, standalone, fixed-size VHDX per
case. It must:

1. create a previously absent image beneath
   `D:/RedMMOTitanWindowsData/DisposableRecoveryHarness/{run_id}`;
2. use an explicit security descriptor and attach with
   `ATTACH_VIRTUAL_DISK_FLAG_NO_DRIVE_LETTER`, without permanent lifetime;
3. retain the creating virtual-disk handle and obtain the physical device path
   from that exact handle with `GetVirtualDiskPhysicalPath`;
4. compare pre/post disk inventories and require exactly one new device linked
   to the image and its recorded virtual-disk identity;
5. initialize or format only that newly created blank device after all identity
   checks pass; a disk number by itself is never authority;
6. mount the NTFS volume at a pre-created, empty, GUID-named directory and
   record the image path, virtual-disk identifier, device path, disk unique ID,
   partition GUID, volume GUID, mount path, NTFS serial, capacity, label, and
   run nonce in an external ownership ledger;
7. keep the handle alive through the case, then remove the exact access path,
   detach through the exact handle, and verify the image is no longer attached;
8. preserve the image and ledger by default.

The image backing file must be local, outside Windows, not EFS encrypted or
compressed, and not accessed through a loopback or mapped share. Fixed
allocation is chosen for predictable capacity. The broker must abort if host
free space cannot cover the bounded image plus the configured reserve.

The unprivileged controller reauthenticates the complete identity chain before
each case:

`run id -> image path -> virtual-disk id -> physical device path -> disk unique
id -> partition guid -> volume guid -> mount path -> NTFS serial`.

It also proves that the disposable volume identity differs from the Windows,
user-profile, repository, diagnostics, manifest, protected-map, and
control-ledger volumes.

## Deterministic process-interruption tier

Tier A arms one checkpoint at a time through a private inherited pipe. The
worker reports the run nonce, case nonce, PID, production call identity, and
checkpoint. The controller may terminate only its one recorded direct child
after receiving the exact nonce-bound checkpoint. Timeouts refuse the case;
they are not timing-based injection.

The ordered checkpoints are:

1. `before_temp_create`
2. `after_temp_create`
3. `mid_payload_write`
4. `after_payload_write_before_preflush`
5. `after_preflush_before_rename`
6. `after_rename_before_postflush`
7. `after_postflush_before_final_validation`
8. `after_final_validation_before_return`
9. `after_return_before_complete_ack`
10. `after_complete_ack_before_clean_exit`
11. `normal_success`

After the worker has exited, recovery inspection occurs in a new process. For
a provisioned VHDX case, the broker performs a normal detach and read-only
remount before the scan. This is useful for recovery-path testing, but it may
flush host state and is not a power-loss simulation.

Expected classifications are:

- before creation: no final and no staging -> `interrupted_clean`;
- after creation and before rename: no final and exactly one expected staging
  artifact -> `interrupted_recoverable_stage`;
- after rename without both a valid `COMPLETE` acknowledgement and clean exit:
  exact final and no staging -> `interrupted_valid_final_uncommitted`;
- normal success: exact final, no staging, authenticated `COMPLETE`, and clean
  exit zero -> `committed`;
- corrupt or partial bytes, both names, extra names, identity drift, wrong
  acknowledgement, wrong exit, output overwrite, or any outside write ->
  `failed_unsafe_state`.

Recovery may recognize an exact final as `recovered_valid_final`, but it must
never rewrite its historical classification to `committed`. Corrupt or
identity-mismatched cases remain preserved for inspection.

## Acceptance and evidence

The static contract tests must verify plan shape, allowlists, privilege
separation, identity chaining, checkpoint ordering, outcome rules, cleanup
limits, and claim limits. A later Tier A execution requires:

- a new disposable local-NTFS volume for every case;
- deterministic checkpoint transcripts rather than sleeps;
- pre/post write tracing with zero writes outside the declared case and ledger;
- source, plan, volume-contract, payload, final, and ledger SHA-256 values;
- full native file and volume identities;
- read-only recovery scan results and filesystem scan results;
- unchanged protected hashes, source-manifest digest, and worktree snapshot;
- explicit booleans for process termination, clean remount, abrupt power loss,
  and physical-media durability.

Tier B is a separate future gate: run inside a disposable VM with no host share
and have the host hard-power the guest off. It can provide virtualized abrupt
interruption evidence only. Tier C is a separately authorized physical power
test on dedicated hardware.

Neither Tier A nor Tier B proves physical-media durability. VHDX metadata
logging, NTFS recovery, write-through file opens, and file-handle flushes do not
prove that every controller, device, or hardware cache honored the request.

## Primary platform references

- [CreateVirtualDisk](https://learn.microsoft.com/en-us/windows/win32/api/virtdisk/nf-virtdisk-createvirtualdisk)
- [AttachVirtualDisk](https://learn.microsoft.com/en-us/windows/win32/api/virtdisk/nf-virtdisk-attachvirtualdisk)
- [Attach flags](https://learn.microsoft.com/en-us/windows/win32/api/virtdisk/ne-virtdisk-attach_virtual_disk_flag)
- [GetVirtualDiskPhysicalPath](https://learn.microsoft.com/en-us/windows/win32/api/virtdisk/nf-virtdisk-getvirtualdiskphysicalpath)
- [DetachVirtualDisk](https://learn.microsoft.com/en-us/windows/win32/api/virtdisk/nf-virtdisk-detachvirtualdisk)
- [SetVolumeMountPoint](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setvolumemountpointw)
- [Test-VHD](https://learn.microsoft.com/en-us/powershell/module/hyper-v/test-vhd?view=windowsserver2025-ps)
- [Repair-Volume](https://learn.microsoft.com/en-us/powershell/module/storage/repair-volume?view=windowsserver2025-ps)
- [Windows file caching](https://learn.microsoft.com/en-us/windows/win32/fileio/file-caching)
- [Stop-VM](https://learn.microsoft.com/en-us/powershell/module/hyper-v/stop-vm?view=windowsserver2025-ps)
