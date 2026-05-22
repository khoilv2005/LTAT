# Dataset-calibrated expertise for CVSS UI

This guidance is calibrated to the CVSS UI labels used by the vulnerability-management dataset. In this dataset, `Required` often corresponds to user-facing kernel entry points or user-triggered operations, not only browser-style victim clicks.

## Required signals

Treat these as evidence for **Required** when they describe the main function behavior:

1. Syscall, ioctl, read/write handler, debugfs/procfs/sysfs operation, mount/remount, mmap/VMA, file operation, quota write, or filesystem operation serving user-controlled files.
2. Explicit user-space data handling: `__user`, `udata`, user pointer, user buffer, userspace copy, `copy_to_user`, `copy_from_user`, user ptr validation.
3. User-visible resource management: create/destroy/alloc/free/register/deregister of objects exposed through RDMA, binder, tty, filesystem, block, or device APIs.
4. Functions that process filenames, dentries, paths, inodes, pages, extents, file offsets, memory regions, or mount options when the operation is tied to user file access.

## Not Required signals

Treat these as evidence for **Not Required** unless there is also a strong user-facing cue:

1. Hardware or driver plumbing: probe, enumerate, init, remove, irq/interrupt, register read/write, descriptor setup, DMA ring housekeeping, PHY/power operations.
2. Pure internal helpers: hash, tree/list walking, math/conversion, offset calculation, lock/state management, debug dump formatting, protocol housekeeping.
3. Background cleanup, worker-thread internals, cache shrinking, or consistency maintenance with no user-facing entry point in the description.
4. Test-only functions or self-test helpers.

## Calibration rules

- Do not require an explicit "victim clicked/opened" phrase; this dataset often labels user-facing kernel interfaces as Required.
- Do not classify Required from a single vague word like "user" if the phrase is only "user data" callback context.
- Prefer Required when multiple concrete cues appear: `ioctl` + `__user`, `debugfs` + `write`, `mmap` + `udata`, `mount` + options, file operation + user buffer.
- Prefer Not Required when the function is clearly internal hardware/system plumbing even if it is part of a larger subsystem that users can indirectly reach.
