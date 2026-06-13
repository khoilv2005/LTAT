"""Run RAG-augmented evaluations."""

import argparse
import asyncio
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SRC))

try:
    from dotenv import load_dotenv

    env_path = ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

from src.rag.context_builder import (
    build_apca_context,
    build_cvss_context,
    build_sbrp_context,
    build_stable_context,
    build_title_context,
    build_vulfix_context,
)
from src.rag.indexer import (
    RagDocument,
    build_apca_documents,
    build_cvss_documents,
    build_sbrp_documents,
    build_stable_documents,
    build_title_documents,
    build_vulfix_documents,
)
from src.rag.leakage_guard import exclude_same_id, validate_index_splits
from src.rag.prompt_builder import (
    build_apca_rag_prompt,
    build_cvss_rag_prompt,
    build_sbrp_rag_prompt,
    build_stable_rag_prompt,
    build_title_rag_prompt,
    build_vulfix_rag_prompt,
)
from src.rag.retriever import BM25Retriever, TfidfRetriever
from src.rag.utils import (
    apca_prompt_input,
    apca_query_text,
    cvss_prompt_input,
    cvss_query_text,
    load_apca_split,
    load_cvss_split,
    load_sbrp_split,
    load_simple_yaml,
    load_stable_split,
    load_title_split,
    load_vulfix_split,
    sbrp_query_text,
    stable_query_text,
    title_prompt_input,
    title_query_text,
    vulfix_prompt_input,
    vulfix_query_text,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Run RAG MVE for vulnerability management tasks")
    parser.add_argument("--task", default="stable", choices=["stable", "SBRP", "APCA", "cvss", "vulfix", "title"])
    parser.add_argument("--dataset", default="stable_patchnet")
    parser.add_argument("--TEST", default="test", choices=["test", "probe"])
    parser.add_argument("--testNum", type=int, default=1, help="0 means all")
    parser.add_argument("--start_index", type=int, default=0, help="zero-based offset into selected split")
    parser.add_argument("--config", default=str(ROOT / "configs" / "rag.yaml"))
    parser.add_argument("--data_root", default=str(ROOT / "data"))
    parser.add_argument("--result_root", default=str(ROOT / "results"))
    parser.add_argument("--result_file_name", default=None)
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--save_prompts", default=None)

    parser.add_argument("--top_k_per_label", type=int, default=None)
    parser.add_argument("--context_max_chars", type=int, default=None)
    parser.add_argument("--example_max_chars", type=int, default=None)
    parser.add_argument("--retrieval_max_query_terms", type=int, default=None)
    parser.add_argument("--retriever", default=None, choices=["bm25", "tfidf"],
                        help="Override retriever in configs/rag.yaml")
    parser.add_argument("--context_strategy", default="score-aware",
                        choices=["score-aware", "label-balanced"],
                        help="How to select retrieved label groups for prompt context")
    parser.add_argument("--retrieval_mode", default="label-balanced",
                        choices=["label-balanced", "vanilla-topk", "random-context"],
                        help="How examples are selected before context construction")
    parser.add_argument("--apca_representation", default="static-features",
                        choices=["static-features", "raw-diff"],
                        help="APCA retrieval/prompt representation for static-feature ablation")
    parser.add_argument("--prompt_style", default="evidence-first",
                        choices=["evidence-first", "standard"],
                        help="Prompt structure for evidence-first ablation")
    parser.add_argument("--strong_margin", type=float, default=None,
                        help="Override score-aware strong margin threshold")
    parser.add_argument("--close_margin", type=float, default=None,
                        help="Override score-aware close margin threshold")

    parser.add_argument("--api_url", default="https://api.openai.com/v1/chat/completions")
    parser.add_argument("--api_key", default=None)
    parser.add_argument("--model", default="gpt-4-0314")
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--max_token", type=int, default=8000)
    parser.add_argument("--response_max_token", type=int, default=256)
    parser.add_argument("--max_requests_per_minute", type=float, default=20)
    parser.add_argument("--max_tokens_per_minute", type=float, default=100000)
    parser.add_argument("--max_concurrent_requests", type=int, default=2)
    parser.add_argument("--max_attempts", type=int, default=10)
    parser.add_argument("--save_every", type=int, default=50)
    return parser.parse_args()


def _config(args):
    cfg = load_simple_yaml(args.config)
    rag = cfg.get("rag", {})
    if args.task == "stable":
        task_key = "stable"
    elif args.task == "SBRP":
        task_key = "sbrp"
    elif args.task == "APCA":
        task_key = "apca"
    elif args.task == "cvss":
        task_key = "cvss"
    elif args.task == "vulfix":
        task_key = "vulfix"
    elif args.task == "title":
        task_key = "title"
    else:
        raise ValueError(f"Unsupported task: {args.task}")
    return rag, cfg.get(task_key, {})


def build_stable_rag_prompts(args):
    rag_cfg, stable_cfg = _config(args)
    index_splits = stable_cfg.get("index_splits") or ["train-part-1", "train-part-2", "probe"]
    validate_index_splits(index_splits)

    top_k_per_label = args.top_k_per_label or int(rag_cfg.get("top_k_per_label", 3))
    context_max_chars = args.context_max_chars or int(rag_cfg.get("context_max_chars", 6000))
    example_max_chars = args.example_max_chars or int(rag_cfg.get("example_max_chars", 900))
    max_query_terms = args.retrieval_max_query_terms or int(rag_cfg.get("retrieval_max_query_terms", 80))

    retriever_name = _retriever_name(args, rag_cfg)
    print(f"Building RAG index for {args.dataset}: splits={index_splits} retriever={retriever_name}", flush=True)
    docs = build_stable_documents(args.data_root, args.dataset, index_splits)
    print(f"Indexed {len(docs)} documents", flush=True)

    retriever = _make_retriever(retriever_name).fit(docs)
    test_items = load_stable_split(args.data_root, args.dataset, args.TEST)
    if args.start_index and args.start_index > 0:
        test_items = test_items[args.start_index :]
    if args.testNum and args.testNum > 0:
        test_items = test_items[: args.testNum]

    prompts = []
    for idx, item in enumerate(test_items, start=1):
        retrieved = _select_retrieved(
            args,
            retriever,
            docs,
            stable_query_text(item),
            labels=["ACK", "NAK"],
            top_k_per_label=top_k_per_label,
            exclude_ids=exclude_same_id(item),
            max_query_terms=max_query_terms,
        )
        context = build_stable_context(
            retrieved,
            example_max_chars=example_max_chars,
            context_max_chars=context_max_chars,
        )
        messages = build_stable_rag_prompt(item.get("patch", ""), context)
        prompts.append(
            {
                "id": str(item.get("id")),
                "prompt": messages,
                "ground_truth": item.get("ground_truth"),
            }
        )
        if idx % 100 == 0 or idx == len(test_items):
            print(f"Generated stable RAG prompts {idx}/{len(test_items)}", flush=True)
    print(f"Generated {len(prompts)} RAG prompts", flush=True)
    return prompts


def build_sbrp_rag_prompts(args):
    rag_cfg, sbrp_cfg = _config(args)
    index_splits = sbrp_cfg.get("index_splits") or ["train", "probe"]
    validate_index_splits(index_splits)

    top_k_per_label = args.top_k_per_label or int(rag_cfg.get("top_k_per_label", 3))
    context_max_chars = args.context_max_chars or int(rag_cfg.get("context_max_chars", 6000))
    example_max_chars = args.example_max_chars or int(rag_cfg.get("example_max_chars", 900))
    max_query_terms = args.retrieval_max_query_terms or int(rag_cfg.get("retrieval_max_query_terms", 80))

    retriever_name = _retriever_name(args, rag_cfg)
    print(f"Building SBRP RAG index for {args.dataset}: splits={index_splits} retriever={retriever_name}", flush=True)
    docs = build_sbrp_documents(args.data_root, args.dataset, index_splits)
    print(f"Indexed {len(docs)} documents", flush=True)

    retriever = _make_retriever(retriever_name).fit(docs)
    test_items = load_sbrp_split(args.data_root, args.dataset, args.TEST)
    if args.start_index and args.start_index > 0:
        test_items = test_items[args.start_index :]
    if args.testNum and args.testNum > 0:
        test_items = test_items[: args.testNum]

    prompts = []
    for idx, item in enumerate(test_items, start=1):
        retrieved = _select_retrieved(
            args,
            retriever,
            docs,
            sbrp_query_text(item),
            labels=["SBR", "NBR"],
            top_k_per_label=top_k_per_label,
            exclude_ids=exclude_same_id(item),
            max_query_terms=max_query_terms,
        )
        context = build_sbrp_context(
            retrieved,
            example_max_chars=example_max_chars,
            context_max_chars=context_max_chars,
            context_strategy=args.context_strategy,
            strong_margin=args.strong_margin if args.strong_margin is not None else 0.08,
            close_margin=args.close_margin if args.close_margin is not None else 0.03,
        )
        messages = build_sbrp_rag_prompt(item.get("bug_report", ""), context, prompt_style=args.prompt_style)
        prompts.append(
            {
                "id": str(item.get("id")),
                "prompt": messages,
                "ground_truth": item.get("ground_truth"),
            }
        )
        if idx % 100 == 0 or idx == len(test_items):
            print(f"Generated SBRP RAG prompts {idx}/{len(test_items)}", flush=True)
    print(f"Generated {len(prompts)} RAG prompts", flush=True)
    return prompts


def build_apca_rag_prompts(args):
    rag_cfg, apca_cfg = _config(args)
    index_splits = apca_cfg.get("index_splits") or ["train", "probe"]
    validate_index_splits(index_splits)

    top_k_per_label = args.top_k_per_label or int(apca_cfg.get("top_k_per_label", rag_cfg.get("top_k_per_label", 3)))
    context_max_chars = args.context_max_chars or int(apca_cfg.get("context_max_chars", rag_cfg.get("context_max_chars", 6000)))
    example_max_chars = args.example_max_chars or int(apca_cfg.get("example_max_chars", rag_cfg.get("example_max_chars", 900)))
    max_query_terms = args.retrieval_max_query_terms or int(apca_cfg.get("retrieval_max_query_terms", rag_cfg.get("retrieval_max_query_terms", 80)))

    retriever_name = _retriever_name(args, rag_cfg)
    print(f"Building APCA RAG index for {args.dataset}: splits={index_splits} retriever={retriever_name}", flush=True)
    docs = build_apca_documents(args.data_root, args.dataset, index_splits)
    if args.apca_representation == "raw-diff":
        docs = _apca_raw_diff_docs(docs)
    print(f"Indexed {len(docs)} documents", flush=True)

    retriever = _make_retriever(retriever_name).fit(docs)
    test_items = load_apca_split(args.data_root, args.dataset, args.TEST)
    if args.start_index and args.start_index > 0:
        test_items = test_items[args.start_index :]
    if args.testNum and args.testNum > 0:
        test_items = test_items[: args.testNum]

    prompts = []
    for idx, item in enumerate(test_items, start=1):
        query_text = _apca_raw_diff_text(item) if args.apca_representation == "raw-diff" else apca_query_text(item)
        retrieved = _select_retrieved(
            args,
            retriever,
            docs,
            query_text,
            labels=["CoF", "NCF"],
            top_k_per_label=top_k_per_label,
            exclude_ids=exclude_same_id(item),
            max_query_terms=max_query_terms,
        )
        context = build_apca_context(
            retrieved,
            example_max_chars=example_max_chars,
            context_max_chars=context_max_chars,
            context_strategy=args.context_strategy,
            include_features=args.apca_representation != "raw-diff",
            strong_margin=args.strong_margin if args.strong_margin is not None else 0.08,
            close_margin=args.close_margin if args.close_margin is not None else 0.03,
        )
        current_input = _apca_raw_prompt_input(item) if args.apca_representation == "raw-diff" else apca_prompt_input(item)
        messages = build_apca_rag_prompt(
            current_input,
            context,
            include_static_features=args.apca_representation != "raw-diff",
            prompt_style=args.prompt_style,
        )
        prompts.append(
            {
                "id": str(item.get("id") or item.get("patch_id")),
                "prompt": messages,
                "ground_truth": item.get("ground_truth"),
            }
        )
        if idx % 100 == 0 or idx == len(test_items):
            print(f"Generated APCA RAG prompts {idx}/{len(test_items)}", flush=True)
    print(f"Generated {len(prompts)} RAG prompts", flush=True)
    return prompts


def build_cvss_rag_prompts(args):
    rag_cfg, cvss_cfg = _config(args)
    index_splits = cvss_cfg.get("index_splits") or ["probe"]
    validate_index_splits(index_splits)

    top_k_per_label = args.top_k_per_label or int(cvss_cfg.get("top_k_per_label", rag_cfg.get("top_k_per_label", 3)))
    context_max_chars = args.context_max_chars or int(cvss_cfg.get("context_max_chars", rag_cfg.get("context_max_chars", 5000)))
    example_max_chars = args.example_max_chars or int(cvss_cfg.get("example_max_chars", rag_cfg.get("example_max_chars", 700)))
    max_query_terms = args.retrieval_max_query_terms or int(cvss_cfg.get("retrieval_max_query_terms", rag_cfg.get("retrieval_max_query_terms", 80)))

    labels = ["0", "1", "2", "3"] if args.dataset == "AV" else ["0", "1"]
    retriever_name = _retriever_name(args, rag_cfg)
    print(f"Building CVSS RAG index for {args.dataset}: splits={index_splits} retriever={retriever_name}", flush=True)
    docs = build_cvss_documents(args.data_root, args.dataset, index_splits)
    print(f"Indexed {len(docs)} documents", flush=True)

    retriever = _make_retriever(retriever_name).fit(docs)
    test_items = load_cvss_split(args.data_root, args.dataset, args.TEST)
    if args.start_index and args.start_index > 0:
        test_items = test_items[args.start_index :]
    if args.testNum and args.testNum > 0:
        test_items = test_items[: args.testNum]

    prompts = []
    for idx, item in enumerate(test_items, start=1):
        retrieved = _select_retrieved(
            args,
            retriever,
            docs,
            cvss_query_text(item),
            labels=labels,
            top_k_per_label=top_k_per_label,
            exclude_ids=exclude_same_id(item),
            max_query_terms=max_query_terms,
        )
        current_input = cvss_prompt_input(item)
        context = build_cvss_context(
            retrieved,
            args.dataset,
            current_input=current_input,
            example_max_chars=example_max_chars,
            context_max_chars=context_max_chars,
            context_strategy=args.context_strategy,
            strong_margin=args.strong_margin if args.strong_margin is not None else 0.06,
            close_margin=args.close_margin if args.close_margin is not None else 0.02,
        )
        messages = build_cvss_rag_prompt(args.dataset, current_input, context, prompt_style=args.prompt_style)
        prompts.append(
            {
                "id": str(item.get("id") or item.get("function")),
                "prompt": messages,
                "ground_truth": item.get("ground_truth"),
            }
        )
        if idx % 100 == 0 or idx == len(test_items):
            print(f"Generated CVSS RAG prompts {idx}/{len(test_items)}", flush=True)
    print(f"Generated {len(prompts)} RAG prompts", flush=True)
    return prompts

def build_vulfix_rag_prompts(args):
    rag_cfg, vulfix_cfg = _config(args)
    index_splits = vulfix_cfg.get("index_splits") or ["probe"]
    validate_index_splits(index_splits)

    top_k_per_label = args.top_k_per_label or int(vulfix_cfg.get("top_k_per_label", 3))
    context_max_chars = args.context_max_chars or int(vulfix_cfg.get("context_max_chars", rag_cfg.get("context_max_chars", 6000)))
    example_max_chars = args.example_max_chars or int(vulfix_cfg.get("example_max_chars", 1200))
    max_query_terms = args.retrieval_max_query_terms or int(vulfix_cfg.get("retrieval_max_query_terms", rag_cfg.get("retrieval_max_query_terms", 80)))

    retriever_name = _retriever_name(args, rag_cfg)
    print(f"Building VulFix RAG index for {args.dataset}: splits={index_splits} retriever={retriever_name}", flush=True)
    docs = build_vulfix_documents(args.data_root, args.dataset, index_splits)
    print(f"Indexed {len(docs)} documents", flush=True)

    retriever = _make_retriever(retriever_name).fit(docs)
    test_items = load_vulfix_split(args.data_root, args.dataset, args.TEST)
    if args.start_index and args.start_index > 0:
        test_items = test_items[args.start_index :]
    if args.testNum and args.testNum > 0:
        test_items = test_items[: args.testNum]

    prompts = []
    for idx, item in enumerate(test_items, start=1):
        retrieved = retriever.search_label_balanced(
            vulfix_query_text(item),
            top_k_per_label=top_k_per_label,
            labels=["FIX"],
            exclude_ids=exclude_same_id(item),
            max_query_terms=max_query_terms,
        )
        context = build_vulfix_context(
            retrieved,
            example_max_chars=example_max_chars,
            context_max_chars=context_max_chars,
        )
        messages = build_vulfix_rag_prompt(vulfix_prompt_input(item), context)
        prompts.append(
            {
                "id": str(item.get("id")),
                "prompt": messages,
                "ground_truth": item.get("ground_truth", ""),
            }
        )
        if idx % 100 == 0 or idx == len(test_items):
            print(f"Generated VulFix RAG prompts {idx}/{len(test_items)}", flush=True)
    print(f"Generated {len(prompts)} RAG prompts", flush=True)
    return prompts

def build_title_rag_prompts(args):
    rag_cfg, title_cfg = _config(args)
    index_splits = title_cfg.get("index_splits") or ["train-part-1", "train-part-2", "probe"]
    validate_index_splits(index_splits)

    top_k = args.top_k_per_label or int(title_cfg.get("top_k", 5))
    context_max_chars = args.context_max_chars or int(title_cfg.get("context_max_chars", rag_cfg.get("context_max_chars", 6000)))
    example_max_chars = args.example_max_chars or int(title_cfg.get("example_max_chars", rag_cfg.get("example_max_chars", 900)))
    max_query_terms = args.retrieval_max_query_terms or int(title_cfg.get("retrieval_max_query_terms", rag_cfg.get("retrieval_max_query_terms", 80)))

    retriever_name = _retriever_name(args, rag_cfg)
    print(f"Building Title RAG index for {args.dataset}: splits={index_splits} retriever={retriever_name}", flush=True)
    docs = build_title_documents(args.data_root, args.dataset, index_splits)
    print(f"Indexed {len(docs)} documents", flush=True)

    retriever = _make_retriever(retriever_name).fit(docs)
    test_items = load_title_split(args.data_root, args.dataset, args.TEST)
    if args.start_index and args.start_index > 0:
        test_items = test_items[args.start_index :]
    if args.testNum and args.testNum > 0:
        test_items = test_items[: args.testNum]

    prompts = []
    for idx, item in enumerate(test_items, start=1):
        retrieved = {
            "TITLE": retriever.search(
                title_query_text(item),
                top_k=top_k,
                label="TITLE",
                exclude_ids=exclude_same_id(item),
                max_query_terms=max_query_terms,
            )
        }
        context = build_title_context(
            retrieved,
            example_max_chars=example_max_chars,
            context_max_chars=context_max_chars,
        )
        messages = build_title_rag_prompt(title_prompt_input(item), context)
        prompts.append(
            {
                "id": str(item.get("id")),
                "prompt": messages,
                "ground_truth": item.get("ground_truth"),
            }
        )
        if idx % 100 == 0 or idx == len(test_items):
            print(f"Generated Title RAG prompts {idx}/{len(test_items)}", flush=True)
    print(f"Generated {len(prompts)} RAG prompts", flush=True)
    return prompts

def build_prompts(args):
    if args.task == "stable":
        return build_stable_rag_prompts(args)
    if args.task == "SBRP":
        return build_sbrp_rag_prompts(args)
    if args.task == "APCA":
        return build_apca_rag_prompts(args)
    if args.task == "cvss":
        return build_cvss_rag_prompts(args)
    if args.task == "vulfix":
        return build_vulfix_rag_prompts(args)
    if args.task == "title":
        return build_title_rag_prompts(args)
    raise ValueError(f"Unsupported task: {args.task}")


def _make_retriever(name):
    if name == "bm25":
        return BM25Retriever()
    if name == "tfidf":
        return TfidfRetriever()
    raise ValueError(f"Unsupported retriever: {name}")

def _retriever_name(args, rag_cfg):
    return str(args.retriever or rag_cfg.get("retriever", "tfidf")).lower()

def _select_retrieved(args, retriever, docs, query, labels, top_k_per_label, exclude_ids, max_query_terms):
    if args.retrieval_mode == "label-balanced":
        return retriever.search_label_balanced(
            query,
            top_k_per_label=top_k_per_label,
            labels=labels,
            exclude_ids=exclude_ids,
            max_query_terms=max_query_terms,
        )

    if args.retrieval_mode == "vanilla-topk":
        total_k = top_k_per_label * len(labels)
        rows = retriever.search(
            query,
            top_k=total_k,
            label=None,
            exclude_ids=exclude_ids,
            max_query_terms=max_query_terms,
        )
        grouped = {label: [] for label in labels}
        for doc, score in rows:
            if doc.label in grouped:
                grouped[doc.label].append((doc, score))
        return grouped

    if args.retrieval_mode == "random-context":
        exclude_ids = {str(item) for item in (exclude_ids or set())}
        seed_value = f"{args.task}:{args.dataset}:{query[:256]}"
        rng = random.Random(seed_value)
        grouped = {label: [] for label in labels}
        for label in labels:
            candidates = [doc for doc in docs if doc.label == label and doc.doc_id not in exclude_ids]
            rng.shuffle(candidates)
            grouped[label] = [(doc, 0.0) for doc in candidates[:top_k_per_label]]
        return grouped

    raise ValueError(f"Unsupported retrieval_mode: {args.retrieval_mode}")

def _apca_raw_diff_text(item):
    return str(item.get("patch") or item.get("patch_code") or "")

def _apca_raw_prompt_input(item):
    return "Patch:\n" + _apca_raw_diff_text(item)

def _apca_raw_diff_docs(docs):
    return [
        RagDocument(
            doc_id=doc.doc_id,
            task=doc.task,
            dataset=doc.dataset,
            split=doc.split,
            label=doc.label,
            text=_apca_raw_diff_text(doc.item),
            item=doc.item,
        )
        for doc in docs
    ]


async def main():
    args = parse_args()
    prompts = build_prompts(args)

    if args.save_prompts:
        Path(args.save_prompts).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save_prompts).write_text(json.dumps(prompts, indent=2), encoding="utf-8")
        print(f"Saved prompts to {args.save_prompts}")

    if args.dry_run:
        if prompts:
            first = prompts[0]
            print(f"Dry run preview id={first['id']} ground_truth={first['ground_truth']}")
            for message in first["prompt"]:
                print(f"\n[{message['role']}]\n{message['content'][:2000]}")
        print("Dry run complete. No API calls made.")
        return

    result_name = args.result_file_name
    if not result_name:
        _, task_cfg = _config(args)
        if args.task == "stable":
            result_name = task_cfg.get("result_name") or f"{args.task}_{args.dataset}_rag-bm25_expertise_{args.TEST}"
        elif args.task == "SBRP":
            prefix = task_cfg.get("result_name_prefix", "SBRP_rag-bm25")
            result_name = f"{prefix}_{args.dataset}_expertise_{args.TEST}"
        else:
            prefix = task_cfg.get("result_name_prefix", "APCA_rag-bm25")
            result_name = f"{prefix}_{args.dataset}_{args.TEST}"

    from src import request

    await request.async_api_requests(
        max_requests_per_minute=args.max_requests_per_minute,
        max_tokens_per_minute=args.max_tokens_per_minute,
        request_url=args.api_url,
        api_key=args.api_key,
        root_path=args.data_root,
        result_file_path=args.result_root,
        result_file_name=result_name,
        task=args.task,
        dataset=args.dataset,
        model=args.model,
        testNum=len(prompts),
        method="rag-bm25",
        max_token=args.max_token,
        response_max_token=args.response_max_token,
        max_attempts=args.max_attempts,
        max_concurrent_requests=args.max_concurrent_requests,
        save_every=args.save_every,
        temperature=args.temperature,
        data=prompts,
    )


if __name__ == "__main__":
    asyncio.run(main())
