import json
import os
import re
from pathlib import Path


TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+|\d+")


def tokenize(text):
    return [token.lower() for token in TOKEN_RE.findall(str(text or "")) if len(token) > 1]


def load_simple_yaml(path):
    """Load the small YAML subset used by configs/rag.yaml without PyYAML."""
    root = {}
    current_section = None
    current_list = None

    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        if line.startswith("- "):
            if current_list is None:
                raise ValueError(f"List item without list parent: {raw_line}")
            value = _parse_scalar(line[2:].strip())
            current_list.append(value)
            continue

        if ":" not in line:
            raise ValueError(f"Unsupported YAML line: {raw_line}")

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if indent == 0:
            root[key] = {}
            current_section = root[key]
            current_list = None
            continue

        if current_section is None:
            raise ValueError(f"Nested key without section: {raw_line}")

        if value == "":
            current_section[key] = []
            current_list = current_section[key]
        else:
            current_section[key] = _parse_scalar(value)
            current_list = None

    return root


def _parse_scalar(value):
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower == "null":
        return None
    try:
        return int(value)
    except ValueError:
        return value.strip('"').strip("'")


def load_stable_split(data_root, dataset, split):
    data_root = Path(data_root)
    if split == "train-part-1":
        path = data_root / "stable" / f"{dataset}-train-part-1.json"
    elif split == "train-part-2":
        path = data_root / "stable" / f"{dataset}-train-part-2.json"
    else:
        path = data_root / "stable" / f"{dataset}-{split}.json"

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload[dataset]
    if isinstance(rows, dict):
        return list(rows.values())
    return rows


def load_sbrp_split(data_root, dataset, split, missing_ok=False):
    path = Path(data_root) / "SBRP" / f"{dataset}-{split}.json"
    if missing_ok and not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload[dataset]
    if isinstance(rows, dict):
        return list(rows.values())
    return rows

def load_apca_split(data_root, dataset, split, missing_ok=False):
    path = Path(data_root) / "APCA" / f"{dataset}-{split}.json"
    if missing_ok and not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload[dataset]
    if isinstance(rows, dict):
        items = []
        for key, value in rows.items():
            item = dict(value)
            item.setdefault("id", str(item.get("patch_id") or key))
            items.append(item)
        return items
    return rows

def load_cvss_split(data_root, dataset, split, missing_ok=False):
    path = Path(data_root) / "cvss" / f"{dataset}-{split}.json"
    if missing_ok and not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload[dataset]
    if isinstance(rows, dict):
        items = []
        for key, value in rows.items():
            item = dict(value)
            item.setdefault("id", str(key))
            items.append(item)
        return items
    return rows

def load_vulfix_split(data_root, dataset, split, missing_ok=False):
    path = Path(data_root) / "vulfix" / f"{dataset}-{split}.json"
    if missing_ok and not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload[dataset]
    if isinstance(rows, dict):
        items = []
        for key, value in rows.items():
            item = dict(value)
            item.setdefault("id", str(key))
            items.append(item)
        return items
    return rows

def load_title_split(data_root, dataset, split, missing_ok=False):
    data_root = Path(data_root)
    if split == "train-part-1":
        path = data_root / "title" / f"{dataset}-train-part-1.json"
    elif split == "train-part-2":
        path = data_root / "title" / f"{dataset}-train-part-2.json"
    else:
        path = data_root / "title" / f"{dataset}-{split}.json"
    if missing_ok and not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload[dataset]
    if isinstance(rows, dict):
        items = []
        for key, value in rows.items():
            item = dict(value)
            item.setdefault("id", str(item.get("id") or key))
            items.append(item)
        return items
    return rows


def stable_item_text(item):
    diff = str(item.get("diff", ""))
    parts = [
        item.get("title", ""),
        item.get("message_xtrailer", "") or item.get("message", ""),
        item.get("file", ""),
        diff[:2500],
    ]
    return "\n".join(str(part) for part in parts if part)


def stable_query_text(item):
    diff = str(item.get("diff", ""))
    return "\n".join(
        part
        for part in [
            item.get("title", ""),
            item.get("message_xtrailer", "") or item.get("message", ""),
            item.get("file", ""),
            diff[:1500],
        ]
        if part
    )


def sbrp_item_text(item):
    return _sbrp_retrieval_text(item.get("bug_report", ""))


def sbrp_query_text(item):
    return _sbrp_retrieval_text(item.get("bug_report", ""))


def apca_item_text(item):
    patch = str(item.get("patch") or item.get("patch_code") or "")
    parts = [
        item.get("bug_summary", ""),
        str(item.get("bug_description", ""))[:1200],
        item.get("patch_description", ""),
        apca_feature_summary(item),
        _semantic_patch_excerpt(patch, max_chars=2500),
    ]
    return "\n".join(str(part) for part in parts if part)


def apca_query_text(item):
    patch = str(item.get("patch") or item.get("patch_code") or "")
    parts = [
        item.get("bug_summary", ""),
        str(item.get("bug_description", ""))[:1000],
        item.get("patch_description", ""),
        apca_feature_summary(item),
        _semantic_patch_excerpt(patch, max_chars=1500),
    ]
    return "\n".join(str(part) for part in parts if part)


def apca_prompt_input(item):
    patch = str(item.get("patch") or item.get("patch_code") or "")
    feature_summary = "Static patch features:\n" + apca_feature_summary(item)
    if item.get("bug_summary") or item.get("bug_description") or item.get("patch_description"):
        parts = [
            "Bug summary: " + str(item.get("bug_summary", "")) if item.get("bug_summary") else "",
            "Bug description:\n" + str(item.get("bug_description", "")) if item.get("bug_description") else "",
            "Patch description:\n" + str(item.get("patch_description", "")) if item.get("patch_description") else "",
            feature_summary,
            "Patch:\n" + patch,
        ]
        return "\n".join(part for part in parts if part)
    return feature_summary + "\n\nPatch:\n" + patch

def cvss_item_text(item):
    function = str(item.get("function", ""))
    description = str(item.get("description", ""))
    return "\n".join(
        part
        for part in [
            "Function: " + function,
            "Subsystem hints: " + _cvss_subsystem_hints(function + " " + description),
            "Description: " + _compact_text(description, max_chars=1200),
        ]
        if part
    )

def cvss_query_text(item):
    return cvss_item_text(item)

def cvss_prompt_input(item):
    return cvss_item_text(item)

def vulfix_item_text(item):
    code = str(item.get("info-manual") or item.get("base") or "")
    return code[:4000]

def vulfix_query_text(item):
    code = str(item.get("info-manual") or item.get("base") or "")
    return code[:2500]

def vulfix_prompt_input(item):
    return str(item.get("info-manual") or item.get("base") or "")

def title_item_text(item):
    return "\n".join(
        part
        for part in [
            str(item.get("ground_truth", "")),
            str(item.get("bug_report", ""))[:2500],
        ]
        if part
    )

def title_query_text(item):
    return str(item.get("bug_report", ""))[:2500]

def title_prompt_input(item):
    return str(item.get("bug_report", ""))


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def _compact_text(text, max_chars=1200):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:max_chars]

def _keyword_windows(text, keywords, window=220, max_chars=900):
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    lowered = raw.lower()
    chunks = []
    for keyword in keywords:
        pos = lowered.find(keyword)
        if pos < 0:
            continue
        start = max(0, pos - window // 2)
        end = min(len(raw), pos + len(keyword) + window // 2)
        chunks.append(raw[start:end])
        if sum(len(chunk) for chunk in chunks) >= max_chars:
            break
    return " ... ".join(chunks)[:max_chars]

def _sbrp_retrieval_text(report):
    report = str(report or "")
    title = report.splitlines()[0] if report.splitlines() else report[:250]
    keywords = [
        "nullpointer", "null pointer", "npe", "memory leak", "out of memory", "oom",
        "accesscontrol", "access control", "permission", "auth", "authentication",
        "authorization", "ssl", "tls", "xss", "cross-site", "injection", "csrf",
        "overflow", "use-after-free", "out-of-bounds", "privilege", "exposure",
        "leak", "security", "vulnerability", "exploit",
    ]
    windows = _keyword_windows(report, keywords)
    head = _compact_text(report, max_chars=700)
    parts = [
        f"Title/head: {title}",
        f"Security keyword windows: {windows}" if windows else "",
        f"Report excerpt: {head}",
    ]
    return "\n".join(part for part in parts if part)

def apca_feature_summary(item):
    patch = str(item.get("patch") or item.get("patch_code") or "")
    patch_id = str(item.get("id") or item.get("patch_id") or "")
    lower = patch.lower()
    added = _changed_lines(patch, "+")
    removed = _changed_lines(patch, "-")
    added_text = "\n".join(added)
    removed_text = "\n".join(removed)
    changed_text = added_text + "\n" + removed_text

    features = []
    checks = [
        ("source_tool=" + _apca_source_tool(patch_id), bool(_apca_source_tool(patch_id))),
        ("project=" + _apca_project_hint(item, patch), bool(_apca_project_hint(item, patch))),
        ("single_hunk", _hunk_count(patch) == 1),
        ("multi_hunk", _hunk_count(patch) > 1),
        ("adds_guard", bool(re.search(r"^\s*if\s*\(", added_text, re.MULTILINE))),
        ("adds_null_check", "null" in lower and bool(re.search(r"(==|!=)\s*null|null\s*(==|!=)", added_text, re.IGNORECASE))),
        ("changes_condition", bool(re.search(r"\b(if|while)\s*\(", removed_text)) and bool(re.search(r"\b(if|while)\s*\(", added_text))),
        ("changes_return", "return" in changed_text),
        ("changes_exception", bool(re.search(r"\b(throw|raise|exception)\b", changed_text, re.IGNORECASE))),
        ("changes_boundary", bool(re.search(r"(<=|>=|<|>|==|!=|&&|\|\|)", changed_text))),
        ("changes_arithmetic", bool(re.search(r"(\+|-|\*|/|%|\+\+|--)", changed_text))),
        ("removes_logic", bool(re.search(r"^\s*(if|while|for|return|throw|continue|break)\b", removed_text, re.MULTILINE))),
        ("deletes_call", bool(re.search(r"^\s*[A-Za-z_][A-Za-z0-9_\.]*\s*\(", removed_text, re.MULTILINE))),
        ("adds_call", bool(re.search(r"^\s*[A-Za-z_][A-Za-z0-9_\.]*\s*\(", added_text, re.MULTILINE))),
        ("uses_magic_constant", bool(re.search(r"\b(999|1000|10000|0\.0|1\.0|-1|Integer\.MAX_VALUE|Double\.NaN)\b", added_text))),
        ("touches_date_time", any(word in lower for word in ["date", "time", "calendar", "timezone", "duration"])),
        ("touches_type_system", any(word in lower for word in ["type", "jsdoc", "scope", "cast", "class"])),
        ("touches_math_numeric", any(word in lower for word in ["nan", "infinity", "fraction", "complex", "double", "float", "matrix"])),
    ]
    for name, present in checks:
        if present:
            features.append(name)
    added_lines = len(added)
    removed_lines = len(removed)
    features.append(f"hunks={_hunk_count(patch)}")
    features.append(f"added_lines={added_lines}")
    features.append(f"removed_lines={removed_lines}")
    features.append(f"net_lines={added_lines - removed_lines}")
    return "Patch semantic features: " + ", ".join(features)

def _changed_lines(patch, marker):
    lines = []
    for line in str(patch or "").splitlines():
        if not line.startswith(marker):
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        lines.append(line[1:].strip())
    return lines

def _hunk_count(patch):
    return len(re.findall(r"^@@", str(patch or ""), re.MULTILINE))

def _apca_source_tool(patch_id):
    patch_id = str(patch_id or "")
    known = [
        "Developer", "Arja", "TBar", "PraPR", "ConFix", "FixMiner", "PatchSim",
        "Hercules", "DynaMoth", "SimFix", "RSRepairA", "jMutRepair", "HDRepair",
        "GenProg", "Nopol", "Cardumen", "kPAR", "AVATAR",
    ]
    for tool in known:
        if re.search(rf"(^|[_#-]){re.escape(tool)}($|[_#-])", patch_id, re.IGNORECASE):
            return tool
    if "PatchNaturalnessYe" in patch_id:
        return "PatchNaturalnessYe"
    if "PatchNaturalness" in patch_id:
        return "PatchNaturalness"
    return ""

def _apca_project_hint(item, patch):
    patch_id = str(item.get("id") or item.get("patch_id") or "")
    file_path = str(item.get("file_path") or "")
    text = " ".join([patch_id, file_path, str(patch or "")[:500]])
    known = [
        "Lang", "Math", "Time", "Closure", "Chart", "Mockito", "Cli", "Codec",
        "Collections", "Compress", "Csv", "Gson", "Jackson", "Jsoup",
    ]
    for project in known:
        if re.search(rf"\b{re.escape(project)}[-_/]?\d*", text, re.IGNORECASE):
            return project
    return ""

def _semantic_patch_excerpt(patch, max_chars=1500):
    patch = str(patch or "")
    lines = []
    for line in patch.splitlines():
        if line.startswith("@@") or line.startswith("+") or line.startswith("-"):
            lines.append(line)
        if sum(len(item) + 1 for item in lines) >= max_chars:
            break
    excerpt = "\n".join(lines).strip()
    return excerpt[:max_chars] if excerpt else patch[:max_chars]

def _cvss_subsystem_hints(text):
    lower = str(text or "").lower()
    groups = {
        "physical_device": ["driver", "device", "hardware", "sound", "scsi", "clock", "runtime", "power", "pm_", "usb", "pci"],
        "network": ["net", "socket", "tcp", "udp", "packet", "route", "wireless", "ieee80211", "bluetooth"],
        "privilege": ["permission", "access", "audit", "credential", "suid", "dumpable", "capability", "security", "policy"],
        "complexity": ["lock", "race", "timing", "state", "serialized", "held", "atomic", "ordering"],
        "user_interaction": ["user", "open", "read", "write", "ioctl", "mmap", "page", "file"],
    }
    hints = [name for name, words in groups.items() if any(word in lower for word in words)]
    return ", ".join(hints) if hints else "none"
