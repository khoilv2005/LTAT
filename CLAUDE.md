# CLAUDE.md

## Project Overview

This is a research repository evaluating ChatGPT's capabilities on **vulnerability management** tasks. Published at USENIX Security 2024.

Paper: "Exploring ChatGPT's Capabilities on Vulnerability Management" by Liu et al.

## Repository Structure

```
/
├── src/                    # Source code for evaluation
│   ├── request.py         # API calls to ChatGPT, async processing, rate limiting
│   ├── prompt.py          # Prompt generation from templates
│   ├── tokens.py          # Token counting utilities
│   └── vulfix/            # Vulnerability fix evaluation
│       ├── combine.py     # Combine ChatGPT response with original code
│       ├── collect.py     # Collect responses
│       ├── config.py      # Configuration
│       ├── getroot.py     # Find scenario configs
│       └── mark.py        # Marking utilities
├── data/                  # Datasets and prompt templates for 6 tasks
│   ├── title/            # Bug report title generation
│   ├── SBRP/             # Security bug report prediction
│   ├── cvss/             # Vulnerability severity evaluation (AV, AC, PR, UI)
│   ├── vulfix/           # Vulnerability repair
│   ├── APCA/             # Patch correctness assessment (panther, quatrain, invalidator)
│   └── stable/           # Stable patch classification (patchnet)
```

## Key Technologies

- **OpenAI API** (GPT-3.5-turbo, GPT-4) for vulnerability analysis
- **tiktoken** for token counting
- **aiohttp** for async API calls
- **asyncio** for concurrent request handling
- **numpy, tqdm** for processing

## 6 Vulnerability Management Tasks

1. **Bug Report Title Generation** - Generate titles from bug reports
2. **Security Bug Report Prediction (SBRP)** - Classify security vs non-security bugs
3. **CVSS Scoring** - Evaluate severity metrics (AV, AC, PR, UI)
4. **Vulnerability Fix (VulFix)** - Repair vulnerable code
5. **Patch Correctness Assessment (APCA)** - Assess if patches are correct (CoF/NCF)
6. **Stable Patch Classification** - Classify stable patches

## Datasets Used in Paper (Table 1 from paper)

| Task | Dataset | Test Samples | Description |
|------|---------|------------:|-------------|
| **SBRP** | Ambari | 500 | Apache Ambari (web-based) |
| | Camel | 500 | Apache Camel (integration framework) |
| | Chromium | 20,970 | Chromium browser |
| | Derby | 500 | Apache Derby (database) |
| | Wicket | 500 | Apache Wicket (web framework) |
| **Title** | iTape | 33,438 | Bug report title generation |
| **CVSS** | AV | 487 | Attack Vector |
| | AC | 373 | Attack Complexity |
| | PR | 414 | Privileges Required |
| | UI | 359 | User Interaction |
| **APCA** | Panther | 208 | Patch correctness |
| | Quatrain | 995 | Patch correctness |
| | Invalidator | 139 | Patch correctness |
| **VulFix** | VulFix | 19 | Vulnerability repair (19 samples only) |
| **Stable** | PatchNet | 10,895 | Stable patch classification |

## Important Patterns

- Datasets use `-test.json`, `-train.json`, `-probe.json`, `-validation.json` suffixes
- Prompt templates stored in `*-prompt.json` files
- `generate_prompt()` in `src/prompt.py` handles all 6 task prompt formats
- `request.py` handles async API calls with rate limiting and retry logic
- `combine.py` merges generated fix code with original source files

## Citation

```
@inproceedings{299549,
    author = {Peiyu Liu et al.},
    title = {Exploring ChatGPT's Capabilities on Vulnerability Management},
    booktitle = {33rd USENIX Security Symposium (USENIX Security 24)},
    year = {2024},
    pages = {811--828}
}
```

## Quick Start Commands

```bash
# Set API key
export MINIMAX_API_KEY="your_key"

# Run a quick test (e.g., 10 samples)
python run.py --task SBRP --dataset Ambari --method base --TEST test --testNum 10

# Evaluate results
python eval.py --result_file results/SBRP_Ambari_base_test.json --task SBRP --dataset Ambari

# Run full test (testNum=0 means all samples)
python run.py --task SBRP --dataset Ambari --method base --TEST test --testNum 0
```
