from dataclasses import dataclass

from .utils import (
    apca_item_text,
    cvss_item_text,
    load_apca_split,
    load_cvss_split,
    load_sbrp_split,
    load_stable_split,
    load_title_split,
    load_vulfix_split,
    sbrp_item_text,
    stable_item_text,
    title_item_text,
    vulfix_item_text,
)


@dataclass(frozen=True)
class RagDocument:
    doc_id: str
    task: str
    dataset: str
    split: str
    label: str
    text: str
    item: dict


def build_stable_documents(data_root, dataset="stable_patchnet", splits=None):
    splits = splits or ["train-part-1", "train-part-2", "probe"]
    docs = []
    for split in splits:
        for item in load_stable_split(data_root, dataset, split):
            label = "ACK" if str(item.get("ground_truth", "")).lower() in ("true", "1", "ack") else "NAK"
            docs.append(
                RagDocument(
                    doc_id=str(item.get("id")),
                    task="stable",
                    dataset=dataset,
                    split=split,
                    label=label,
                    text=stable_item_text(item),
                    item=item,
                )
            )
    return docs


def build_sbrp_documents(data_root, dataset, splits=None):
    splits = splits or ["train", "probe"]
    docs = []
    for split in splits:
        for item in load_sbrp_split(data_root, dataset, split, missing_ok=True):
            label = "SBR" if str(item.get("ground_truth", "")).strip() == "1" else "NBR"
            docs.append(
                RagDocument(
                    doc_id=str(item.get("id")),
                    task="SBRP",
                    dataset=dataset,
                    split=split,
                    label=label,
                    text=sbrp_item_text(item),
                    item=item,
                )
            )
    return docs

def build_apca_documents(data_root, dataset, splits=None):
    splits = splits or ["train", "probe"]
    docs = []
    for split in splits:
        for item in load_apca_split(data_root, dataset, split, missing_ok=True):
            label = _apca_label(item.get("ground_truth", ""))
            docs.append(
                RagDocument(
                    doc_id=str(item.get("id") or item.get("patch_id")),
                    task="APCA",
                    dataset=dataset,
                    split=split,
                    label=label,
                    text=apca_item_text(item),
                    item=item,
                )
            )
    return docs

def build_cvss_documents(data_root, dataset, splits=None):
    splits = splits or ["probe"]
    docs = []
    for split in splits:
        for item in load_cvss_split(data_root, dataset, split, missing_ok=True):
            label = str(item.get("ground_truth", "")).strip()
            docs.append(
                RagDocument(
                    doc_id=str(item.get("id") or item.get("function")),
                    task="cvss",
                    dataset=dataset,
                    split=split,
                    label=label,
                    text=cvss_item_text(item),
                    item=item,
                )
            )
    return docs

def build_vulfix_documents(data_root, dataset, splits=None):
    splits = splits or ["probe"]
    docs = []
    for split in splits:
        for item in load_vulfix_split(data_root, dataset, split, missing_ok=True):
            docs.append(
                RagDocument(
                    doc_id=str(item.get("id")),
                    task="vulfix",
                    dataset=dataset,
                    split=split,
                    label="FIX",
                    text=vulfix_item_text(item),
                    item=item,
                )
            )
    return docs

def build_title_documents(data_root, dataset="title_itape", splits=None):
    splits = splits or ["train-part-1", "train-part-2", "probe"]
    docs = []
    for split in splits:
        for item in load_title_split(data_root, dataset, split, missing_ok=True):
            docs.append(
                RagDocument(
                    doc_id=str(item.get("id")),
                    task="title",
                    dataset=dataset,
                    split=split,
                    label="TITLE",
                    text=title_item_text(item),
                    item=item,
                )
            )
    return docs

def _apca_label(value):
    lower = str(value).strip().lower()
    if lower in ("1", "true", "correct", "cof", "correct patch"):
        return "CoF"
    return "NCF"
