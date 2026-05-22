# Manual expertise for CVSS v3.1 User Interaction (UI)

This guidance is for the CVSS v3.1 User Interaction metric, not for generic "user-space involvement".

## Definitions

- **Not Required (UI:N, Class 0)**: exploitation does not require any human user, other than the attacker, to perform an action. The attacker can trigger the vulnerable path directly through a request, packet, syscall, device operation, file operation they initiate, or an automated/background processing path.
- **Required (UI:R, Class 1)**: exploitation requires a separate victim user to take an action, such as opening a crafted file, clicking a malicious link, visiting a page, loading attacker-controlled media/content, accepting a prompt, or otherwise interacting with attacker-controlled data.

## Strong signals for Required

Treat these as evidence for Required only when the description shows a victim action is needed:

1. Opening or parsing a crafted document, archive, image, font, media file, certificate, email, or web page.
2. Browser, UI, desktop, viewer, editor, previewer, or client-side rendering paths that require the victim to load attacker-controlled content.
3. Human actions such as click, open, visit, browse, view, preview, mount removable media, import, accept, or install.
4. A local victim application must process data supplied by the attacker after the victim chooses to interact with it.

## Strong signals for Not Required

Treat these as evidence for Not Required unless the description also mentions a separate victim action:

1. Network packets, remote requests, RPC messages, ioctls, syscalls, device commands, driver operations, filesystem operations, kernel worker paths, interrupt handlers, timers, or automatic parsing triggered by the attacker.
2. Kernel functions involving `__user`, `udata`, `copy_to_user`, `copy_from_user`, userspace pointers, mmap, VMA, file descriptors, read, write, ioctl, or page faults. These indicate an attacker-controlled interface, but not necessarily a separate victim user's action.
3. Internal helpers, alloc/free/destroy functions, offset calculations, tree/list/hash operations, lock/state management, and conversions.
4. Mentions of "user data" or "userdata" when it means callback context or an opaque pointer, not a human user's interaction.

## Common mistakes to avoid

- Do not classify Required just because the function touches user-space memory.
- Do not classify Required just because the function is in a filesystem, mmap, ioctl, driver, or networking path.
- Do not classify Required just because exploitation is initiated by a local user or attacker. CVSS UI asks whether an additional victim user must participate.
- Do not treat "user", "udata", "userdata", or "user pointer" as enough evidence by itself.

## Decision procedure

1. Identify the trigger path: attacker-direct, automated/internal, or victim-action-driven.
2. Look for explicit victim actions: open, click, visit, view, load, import, preview, accept, install.
3. If explicit victim action evidence exists, choose Required.
4. Otherwise choose Not Required, even if the function handles user-space data or is reachable through syscalls/ioctls/filesystem operations.
