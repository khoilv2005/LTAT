# Dataset Statistics

Counted from all JSON dataset files under `data/`, excluding `*-prompt.json`.

## Title

| Dataset | Split | Samples |
|---|---:|---:|
| title_itape | train-part-1 | 62,334 |
| title_itape | train-part-2 | 62,333 |
| title_itape | test | 33,438 |
| title_itape | probe | 1,000 |
| title_itape | total | 159,105 |

## SBRP

| Dataset | Split | Samples |
|---|---:|---:|
| Ambari | train | 500 |
| Ambari | test | 500 |
| Ambari | total | 1,000 |
| Camel | train | 500 |
| Camel | test | 500 |
| Camel | total | 1,000 |
| Chromium | train | 20,970 |
| Chromium | test | 20,970 |
| Chromium | probe | 1,000 |
| Chromium | total | 42,940 |
| Derby | train | 500 |
| Derby | test | 500 |
| Derby | total | 1,000 |
| Wicket | train | 500 |
| Wicket | test | 500 |
| Wicket | total | 1,000 |

## CVSS

| Dataset | Split | Samples |
|---|---:|---:|
| AV | test | 487 |
| AV | probe | 111 |
| AV | total | 598 |
| AC | test | 373 |
| AC | probe | 83 |
| AC | total | 456 |
| PR | test | 414 |
| PR | probe | 96 |
| PR | total | 510 |
| UI | test | 359 |
| UI | probe | 84 |
| UI | total | 443 |

## Stable Patch Classification

| Dataset | Split | Samples |
|---|---:|---:|
| stable_patchnet | train-part-1 | 21,793 |
| stable_patchnet | train-part-2 | 21,791 |
| stable_patchnet | test | 10,895 |
| stable_patchnet | probe | 1,000 |
| stable_patchnet | total | 55,479 |

## APCA

| Dataset | Split | Samples |
|---|---:|---:|
| APCA_quatrain | train | 8,111 |
| APCA_quatrain | test | 995 |
| APCA_quatrain | probe | 811 |
| APCA_quatrain | total | 9,917 |
| APCA_panther | train | 1,939 |
| APCA_panther | test | 208 |
| APCA_panther | probe | 193 |
| APCA_panther | total | 2,340 |
| APCA_invalidator | train | 746 |
| APCA_invalidator | test | 139 |
| APCA_invalidator | probe | 74 |
| APCA_invalidator | total | 959 |

## Vulnerability Repair

| Dataset | Split | Samples |
|---|---:|---:|
| vulfix_extractfix | test | 12 |
| vulfix_extractfix | probe | 7 |
| vulfix_extractfix | total | 19 |

## Grand Total

| Scope | Samples |
|---|---:|
| All datasets | 276,766 |

Task	Input đưa vào ChatGPT	Output cần lấy	Prompt tốt theo paper
1. Bug report summarization	bug report	title/summary	few-shot với gpt-4
2. Security bug report identification	bug report	SBR/NBR	expertise với gpt-4
3. Vulnerability severity evaluation	function + description	CVSS metric label AV/AC/PR/UI	self-heuristic với gpt-4
4. Vulnerability repair	vulnerable code snippet + error/vuln info	repaired code	expertise với gpt-4
5. Patch correctness assessment	patch/code/description tùy dataset	correct/incorrect patch	code-only hoặc self-heuristic, tùy dataset
6. Stable patch classification	patch description + code snippet	stable/non-stable	expertise với gpt-4
