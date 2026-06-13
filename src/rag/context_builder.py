from .utils import apca_feature_summary

def build_stable_context(retrieved, example_max_chars=900, context_max_chars=6000):
    sections = []
    for label in ("ACK", "NAK"):
        rows = retrieved.get(label, [])
        if not rows:
            continue
        lines = [f"Similar {label} examples from train/probe:"]
        for rank, (doc, score) in enumerate(rows, start=1):
            item = doc.item
            title = _clean(item.get("title", ""))
            message = _clean(item.get("message_xtrailer", "") or item.get("message", ""))
            files = _clean(item.get("file", ""))
            diff = _clean(item.get("diff", ""))
            body = (
                f"[{rank}] label={label} score={score:.4f}\n"
                f"Title: {title}\n"
                f"Files: {files}\n"
                f"Message: {message}\n"
                f"Diff excerpt:\n{diff}"
            )
            lines.append(body[:example_max_chars])
        sections.append("\n\n".join(lines))

    context = "\n\n---\n\n".join(sections)
    return context[:context_max_chars]


def build_sbrp_context(retrieved, example_max_chars=900, context_max_chars=6000, context_strategy="score-aware", strong_margin=0.08, close_margin=0.03):
    sections = []
    plan = _context_plan(retrieved, ("SBR", "NBR"), context_strategy, strong_margin=strong_margin, close_margin=close_margin)
    score_note = _score_note(retrieved, ("SBR", "NBR"))
    if score_note:
        sections.append(score_note)
    for label, keep in plan:
        rows = retrieved.get(label, [])[:keep]
        if not rows:
            continue
        lines = [f"Similar {label} bug reports from train/probe:"]
        for rank, (doc, score) in enumerate(rows, start=1):
            report = _clean(doc.item.get("bug_report", ""))
            body = f"[{rank}] label={label} score={score:.4f}\nBug report:\n{report}"
            lines.append(body[:example_max_chars])
        sections.append("\n\n".join(lines))

    context = "\n\n---\n\n".join(sections)
    return context[:context_max_chars]


def build_apca_context(retrieved, example_max_chars=900, context_max_chars=6000, context_strategy="score-aware", include_features=True, strong_margin=0.08, close_margin=0.03):
    sections = []
    plan = _context_plan(retrieved, ("CoF", "NCF"), context_strategy, strong_margin=strong_margin, close_margin=close_margin)
    score_note = _score_note(retrieved, ("CoF", "NCF"))
    if score_note:
        sections.append(score_note)
    for label, keep in plan:
        rows = retrieved.get(label, [])[:keep]
        if not rows:
            continue
        label_text = "correct patch" if label == "CoF" else "incorrect patch"
        lines = [f"Similar {label} ({label_text}) examples from train/probe:"]
        for rank, (doc, score) in enumerate(rows, start=1):
            item = doc.item
            bug_summary = _clean(item.get("bug_summary", ""))
            bug_description = _clean(item.get("bug_description", ""))
            patch_description = _clean(item.get("patch_description", ""))
            patch = _clean(item.get("patch") or item.get("patch_code") or "")
            features = apca_feature_summary(item) if include_features else ""
            body_parts = [
                f"[{rank}] label={label} score={score:.4f}",
                f"Bug summary: {bug_summary}" if bug_summary else "",
                f"Bug description: {bug_description}" if bug_description else "",
                f"Patch description: {patch_description}" if patch_description else "",
                f"Static features: {features}" if features else "",
                f"Patch excerpt:\n{patch}" if patch else "",
            ]
            body = "\n".join(part for part in body_parts if part)
            lines.append(body[:example_max_chars])
        sections.append("\n\n".join(lines))

    context = "\n\n---\n\n".join(sections)
    return context[:context_max_chars]


def build_cvss_context(retrieved, dataset, current_input="", example_max_chars=900, context_max_chars=6000, context_strategy="score-aware", strong_margin=0.06, close_margin=0.02):
    sections = []
    labels = _cvss_labels(dataset)
    anchor_label, anchor_reason = _cvss_anchor_label(dataset, current_input)
    if anchor_label is not None:
        plan = _anchor_aware_plan(retrieved, labels, anchor_label)
        sections.append(f"Dataset-calibrated anchor: prefer label {anchor_label} ({_cvss_label_name(dataset, anchor_label)}) because {anchor_reason}.")
    else:
        plan = _context_plan(retrieved, labels, context_strategy, strong_margin=strong_margin, close_margin=close_margin)
    score_note = _score_note(retrieved, labels)
    if score_note:
        sections.append(score_note)
    for label, keep in plan:
        rows = retrieved.get(label, [])[:keep]
        if not rows:
            continue
        lines = [f"Similar CVSS {dataset} examples with label {label} ({_cvss_label_name(dataset, label)}):"]
        for rank, (doc, score) in enumerate(rows, start=1):
            item = doc.item
            function = _clean(item.get("function", ""))
            description = _clean(item.get("description", ""))
            body = (
                f"[{rank}] label={label} score={score:.4f}\n"
                f"Function: {function}\n"
                f"Description: {description}"
            )
            lines.append(body[:example_max_chars])
        sections.append("\n\n".join(lines))

    context = "\n\n---\n\n".join(sections)
    return context[:context_max_chars]

def build_vulfix_context(retrieved, example_max_chars=1200, context_max_chars=6000):
    rows = retrieved.get("FIX", [])
    lines = ["Similar vulnerable-code repair examples from probe:"]
    for rank, (doc, score) in enumerate(rows, start=1):
        item = doc.item
        vulnerable = _clean(item.get("base", ""))
        repaired = _clean(item.get("info-manual", ""))
        body = (
            f"[{rank}] id={doc.doc_id} score={score:.4f}\n"
            f"Vulnerable prefix:\n{vulnerable}\n\n"
            f"Secure completion / repaired pattern:\n{repaired}"
        )
        lines.append(body[:example_max_chars])
    return "\n\n---\n\n".join(lines)[:context_max_chars]

def build_title_context(retrieved, example_max_chars=900, context_max_chars=6000):
    rows = retrieved.get("TITLE", [])
    lines = ["Similar bug report title examples from train/probe:"]
    for rank, (doc, score) in enumerate(rows, start=1):
        item = doc.item
        report = _clean(item.get("bug_report", ""))
        title = _clean(item.get("ground_truth", ""))
        body = (
            f"[{rank}] score={score:.4f}\n"
            f"Bug report:\n{report}\n"
            f"Title: {title}"
        )
        lines.append(body[:example_max_chars])
    return "\n\n---\n\n".join(lines)[:context_max_chars]

def _cvss_labels(dataset):
    if dataset == "AV":
        return ["0", "1", "2", "3"]
    return ["0", "1"]

def _cvss_label_name(dataset, label):
    names = {
        "AV": {
            "0": "Not Related",
            "1": "Network",
            "2": "Adjacent Network",
            "3": "Physical",
        },
        "AC": {"0": "Not High", "1": "High"},
        "PR": {"0": "Not High", "1": "High"},
        "UI": {"0": "Not Required", "1": "Required"},
    }
    return names.get(dataset, {}).get(str(label), str(label))

def _clean(value):
    return str(value or "").strip()

def _avg_score(rows):
    if not rows:
        return 0.0
    return sum(score for _, score in rows) / len(rows)

def _score_aware_plan(retrieved, labels, strong_margin=0.08, close_margin=0.03):
    scores = {label: _avg_score(retrieved.get(label, [])) for label in labels}
    ordered = sorted(labels, key=lambda label: scores.get(label, 0.0), reverse=True)
    if not ordered:
        return []

    best = ordered[0]
    second_score = scores.get(ordered[1], 0.0) if len(ordered) > 1 else 0.0
    margin = scores.get(best, 0.0) - second_score
    max_rows = max((len(retrieved.get(label, [])) for label in labels), default=0)
    if max_rows <= 0:
        return [(label, 0) for label in labels]

    if margin >= strong_margin:
        counts = {label: 1 for label in labels}
        counts[best] = max_rows
    elif margin >= close_margin:
        counts = {label: min(2, max_rows) for label in labels}
        counts[best] = max_rows
    else:
        counts = {label: min(2, max_rows) for label in labels}

    # Put the strongest retrieved side first, but keep all labels visible.
    return [(label, counts[label]) for label in ordered]

def _context_plan(retrieved, labels, context_strategy, strong_margin=0.08, close_margin=0.03):
    if context_strategy == "label-balanced":
        return _label_balanced_plan(retrieved, labels)
    return _score_aware_plan(
        retrieved,
        labels,
        strong_margin=strong_margin,
        close_margin=close_margin,
    )

def _label_balanced_plan(retrieved, labels):
    max_rows = max((len(retrieved.get(label, [])) for label in labels), default=0)
    return [(label, max_rows) for label in labels]

def _score_note(retrieved, labels):
    parts = []
    for label in labels:
        rows = retrieved.get(label, [])
        if not rows:
            continue
        parts.append(f"{label} avg_score={_avg_score(rows):.4f} top_score={rows[0][1]:.4f}")
    if not parts:
        return ""
    return "Retrieval score summary: " + "; ".join(parts)

def _anchor_aware_plan(retrieved, labels, anchor_label):
    max_rows = max((len(retrieved.get(label, [])) for label in labels), default=0)
    if max_rows <= 0:
        return [(label, 0) for label in labels]
    ordered = [anchor_label] + [label for label in labels if label != anchor_label]
    counts = {label: 1 for label in labels}
    counts[anchor_label] = max_rows
    return [(label, counts[label]) for label in ordered]

def _cvss_anchor_label(dataset, current_input):
    text = str(current_input or "").lower()
    if dataset == "AV":
        adjacent = [
            "wireless", "wifi", "wi-fi", "80211", "ieee80211", "bluetooth",
            "nfc", "near field", "nl80211", "wiphy", "wlan", "mac80211",
        ]
        network = [
            "tcp", "udp", "socket", "skb", "packet", "route", "ipv4", "ipv6",
            "ethernet", "net device", "network device", "rx", "tx",
        ]
        physical = [
            "driver", "device", "hardware", "usb", "sound", "snd_", "clock",
            "runtime pm", "power management", "scsi", "pci", "crypto", "sensor",
            "firmware", "phy", "interface", "card", "controller",
        ]
        if any(word in text for word in adjacent):
            return "2", "wireless/NFC/Bluetooth/local-link subsystem terms map to Adjacent Network in this dataset"
        if any(word in text for word in network):
            return "1", "network packet/socket/net-device terms map to Network in this dataset"
        if any(word in text for word in physical):
            return "3", "driver/device/hardware/USB/sound/clock terms map to Physical in this dataset"
        return None, ""

    if dataset == "AC":
        high = [
            "lock", "mutex", "semaphore", "sema", "timeout", "timing", "race",
            "atomic", "held", "serialized", "serialised", "state", "context",
            "hardware access", "hw access", "sleep", "wait", "deadlock",
        ]
        if any(word in text for word in high):
            return "1", "lock/mutex/semaphore/timeout/state/hardware-access terms map to High in this dataset"
        return None, ""

    if dataset == "PR":
        high = [
            "permission", "permissions", "access", "allowed", "security",
            "capability", "credential", "cred", "suid", "dumpable", "priv",
            "privilege", "keyctl", "inode", "proc", "audit", "policy",
            "lsm", "selinux", "xperm", "acl",
        ]
        if any(word in text for word in high):
            return "1", "permission/access/security/capability/inode/keyctl/proc terms map to High in this dataset"
        return None, ""

    if dataset == "UI":
        required = [
            "udata", "user data", "userspace", "user space", "sysfs", "mount",
            "umount", "submount", "write", "read", "ioctl", "mmap", "file",
            "path", "query", "open", "page", "socket option", "copy from user",
        ]
        if any(word in text for word in required):
            return "1", "user-data/filesystem/mount/read/write/ioctl/path/query terms map to Required in this dataset"
        return None, ""

    return None, ""
