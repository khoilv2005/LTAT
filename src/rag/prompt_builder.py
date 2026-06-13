STABLE_RULES = """Linux -stable decision rules:
- ACK if the patch fixes a concrete real bug and the change is small, targeted, and backportable.
- Stable-worthy bugs include regressions, build failures, oops/crashes, hangs, data corruption, races/deadlocks, NULL/error-path bugs, incorrect return-value checks, resource leaks, off-by-one errors, broken hardware/driver behavior, broken user-visible behavior, and small correctness fixes.
- NAK if the patch is mainly feature work, refactoring, cleanup, rename-only, comments/docs/formatting/whitespace, cosmetic change, broad redesign, new API, optional optimization, test-only change, or risky/invasive work without a clear stable bug-fix benefit.
- Do not ACK merely because a patch improves code quality.
- Do not NAK merely because the bug is not security/crash; correctness and error-path fixes can be stable-worthy when concrete."""


def build_stable_rag_prompt(patch_text, retrieved_context):
    system_prompt = (
        "You are Frederick, an expert Linux kernel stable-release patch reviewer. "
        "Use retrieved evidence as supporting context, but make the final decision "
        "from the current patch. Retrieved examples may be similar but are not proof."
    )

    user_prompt = f"""{STABLE_RULES}

Retrieved evidence:
{retrieved_context}

Current Linux kernel patch:
```
{patch_text}
```

Decide whether the current patch should be accepted in Linux -stable releases.

Use this priority:
1. Prefer ACK for a concrete bug fix with direct, targeted code changes.
2. Prefer NAK for feature/refactor/cleanup/style/new API/optimization/test-only changes without a concrete bug being fixed.
3. If retrieved examples conflict, explain which side is more similar to the current patch.

Output your final answer EXACTLY in this format on its own line:
**Answer: (A) ACK**
or
**Answer: (B) NAK**"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


SBRP_RULES = """Security bug report decision rules:
- SBR means the report describes a vulnerability or security impact in a software system.
- NBR means the report describes a normal bug, usability issue, feature request, test failure, performance issue, crash, or reliability issue without a clear security/vulnerability impact.
- In this benchmark, concrete null pointer, memory leak, out-of-memory, permission, access-control, authentication, SSL/TLS, XSS, injection, use-after-free, out-of-bounds, buffer overflow, information exposure, privilege/security boundary, or remote-code-execution reports are strong SBR evidence when tied to a real product bug.
- Do not classify as NBR merely because the report uses ordinary bug-report wording. First extract the concrete security-relevant evidence from the current report.
- Choose NBR for UI/UX, feature, performance, flaky test, compatibility, install, localization, documentation, generic crash, or generic reliability only when no concrete security-relevant evidence is present."""


def build_sbrp_rag_prompt(bug_report, retrieved_context, prompt_style="evidence-first"):
    system_prompt = (
        "You are Frederick, an expert security bug report analyst. "
        "Use retrieved reports as supporting evidence, but classify the current report from its own text. "
        "Retrieved labels are examples, not proof."
    )

    if prompt_style == "standard":
        analysis_block = """Decide whether the current bug report is a security bug report.

Use the retrieved evidence only as supporting examples. Do not copy a retrieved label unless the current report has matching evidence."""
    else:
        analysis_block = """Decide whether the current bug report is a security bug report.

Analyze in this order:
Step 1 (current evidence): list security-relevant evidence in the current report, especially null pointer, memory leak/OOM, access control, permission, authentication, SSL/TLS, XSS, injection, memory safety, exposure, or exploitability terms. If none exists, say none.
Step 2 (retrieval comparison): compare the current report to the retrieved examples. Use the retrieval score summary to identify which label side is more similar, but do not copy labels blindly.
Step 3 (decision): choose SBR when Step 1 has concrete security-relevant evidence or the current report matches high-scoring SBR examples better; choose NBR only when security evidence is absent or weaker than NBR evidence."""

    user_prompt = f"""{SBRP_RULES}

Retrieved evidence:
{retrieved_context}

Current bug report:
```
{bug_report}
```

{analysis_block}

Output your final answer EXACTLY in this format on its own line:
Final answer: SBR
or
Final answer: NBR"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

APCA_RULES = """Patch correctness decision rules:
- CoF means the patch correctly fixes the intended bug without introducing a new bug.
- NCF means the patch is incorrect, incomplete, overfitted to tests, unrelated to the bug, too broad, dead-code-like, or likely introduces side effects.
- Choose CoF when the patch has a coherent bug intent and the changed condition, return value, guard, exception, or computation directly implements that fix.
- Choose NCF when there is clear evidence of an arbitrary constant/condition, removed essential logic, unrelated change, dead code, test-specific masking, or behavior-breaking side effect.
- Do not classify a patch as NCF merely because it is small, unfamiliar, generated by APR, or changes only one condition/guard. Many correct patches are small guards, boundary checks, comparisons, exception fixes, return-value fixes, or null checks.
- Choose NCF only when the current patch itself shows concrete incorrectness such as unrelated code, removed essential logic, arbitrary constants, dead code, test-specific masking, or behavior-breaking side effects.
- Use Static patch features to compare the current patch with retrieved examples by semantic edit type: guard, condition, return, boundary, exception, deletion, call add/delete, hunk count, source tool, and project.
- Source/tool metadata is calibration evidence, not ground truth. Developer source supports plausibility only when the edit is semantically coherent. APR-tool source requires stricter checking for overfitting, but does not imply NCF by itself.
- Retrieved examples are only analogies. Prefer the current patch semantics over retrieved labels."""

def build_apca_rag_prompt(current_input, retrieved_context, include_static_features=True, prompt_style="evidence-first"):
    system_prompt = (
        "You are Frederick, an expert automated program repair and patch correctness reviewer. "
        "Decide from the current patch semantics. Retrieved examples are only supporting analogies."
    )

    rules = APCA_RULES
    if not include_static_features:
        rules = "\n".join(
            line
            for line in APCA_RULES.splitlines()
            if "Static patch features" not in line
            and "Source/tool metadata" not in line
            and "static features" not in line.lower()
        )

    if prompt_style == "standard":
        analysis_block = """Decide whether the patch is correct. Use retrieved examples only as analogies and prioritize the current patch semantics."""
    else:
        first_step = (
            "Step 1 (feature extraction): read the Static patch features and identify edit type, source/tool, project, hunk count, added/deleted logic, condition/return/boundary changes, and magic constants."
            if include_static_features
            else "Step 1 (patch reading): identify the edited file, changed lines, added/deleted logic, condition/return/boundary changes, and magic constants directly from the diff."
        )
        comparison_step = (
            "Step 4 (retrieval comparison): compare to retrieved CoF and NCF examples with similar static features and scores; examples with different edit type/tool/project should get less weight."
            if include_static_features
            else "Step 4 (retrieval comparison): compare to retrieved CoF and NCF examples with similar diff edits and scores; examples with different edit intent should get less weight."
        )
        analysis_block = f"""Analyze in this order:
{first_step}
Step 2 (current patch evidence): identify whether the current patch directly addresses the bug with a guard, condition change, return/exception fix, bounds check, null check, or computation fix.
Step 3 (incorrectness evidence): identify concrete evidence of unrelated change, removed essential logic, arbitrary constant, dead code, overfitting, or side effects. If absent, say absent.
{comparison_step}
Step 5 (decision): output the final answer."""

    user_prompt = f"""{rules}

Retrieved evidence:
{retrieved_context}

Current patch assessment input:
```
{current_input}
```

{analysis_block}

Output your final answer EXACTLY in one of these formats:
**Answer: (A) CoF**
or
**Answer: (B) NCF**

Then give at most 3 short bullet reasons. Do not write long reasoning beyond the four steps."""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

def build_cvss_rag_prompt(dataset, current_input, retrieved_context, prompt_style="evidence-first"):
    system_prompt = (
        "You are Frederick, an expert vulnerability severity analyst using CVSS v3.1. "
        "Use retrieved examples as calibration evidence, but classify the current function "
        "from its own function name and description. When benchmark-calibrated retrieved "
        "examples and anchors conflict with textbook CVSS wording, follow the dataset's "
        "observed labeling style."
    )

    categories = _cvss_categories(dataset)
    rules = _cvss_rules(dataset)

    if prompt_style == "standard":
        analysis_block = f"""Classify the current function for CVSS {dataset}.

Use retrieved examples as calibration evidence, but choose the final label from the current function name and description."""
    else:
        analysis_block = f"""Classify the current function for CVSS {dataset}.

Analyze in this order:
Step 1 (current function evidence): extract metric-specific evidence from the function name and description.
Step 2 (dataset calibration): use the Dataset-calibrated anchor and retrieved examples to identify how this benchmark labels similar functions.
Step 3 (retrieval comparison): compare against retrieved label groups using the retrieval score summary. Give more weight to examples sharing the same anchor terms as the current function.
Step 4 (decision): choose the label supported by current evidence plus the benchmark-calibrated retrieved examples, not by textbook wording alone."""

    user_prompt = f"""{rules}

Retrieved evidence:
{retrieved_context}

Current function:
```
{current_input}
```

{analysis_block}

Output your final answer EXACTLY in this format on its own line:
{_cvss_answer_formats(dataset)}"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Classification options: {categories}\n\n{user_prompt}"},
    ]

def build_vulfix_rag_prompt(current_input, retrieved_context):
    system_prompt = (
        "You are Frederick, an expert secure C/C++ vulnerability repair engineer. "
        "Use retrieved repair examples as pattern hints only. Produce a secure completion "
        "for the current vulnerable program."
    )

    user_prompt = f"""Vulnerability repair rules:
- Preserve the original program intent and API.
- Add bounds checks, null checks, length validation, allocation checks, and error handling when needed.
- Do not remove required functionality just to avoid the vulnerability.
- Do not include explanations, markdown fences, or prose in the final output.

Retrieved repair examples:
{retrieved_context}

Current vulnerable program prefix:
```
{current_input}
```

Complete the vulnerable program with secure code.

Output only repaired code / code continuation. No explanation."""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

def build_title_rag_prompt(bug_report, retrieved_context):
    system_prompt = (
        "You are Frederick, an expert software issue triager. "
        "Generate concise bug report titles. Use retrieved examples only as style and terminology hints."
    )

    user_prompt = f"""Title generation rules:
- Output one short sentence or phrase.
- Preserve the main failing component, symptom, and condition.
- Do not add facts not present in the bug report.
- Do not include quotes, markdown, prefixes, bullets, or explanation.
- Use lowercase style when natural, matching dataset examples.

Retrieved examples:
{retrieved_context}

Current bug report:
```
{bug_report}
```

Generate the title only."""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

def _cvss_categories(dataset):
    if dataset == "AV":
        return "(A) Network, (B) Adjacent Network, (C) Physical, (D) Not Related"
    if dataset == "UI":
        return "(A) Not Required, (B) Required"
    return "(A) Not High, (B) High"

def _cvss_answer_formats(dataset):
    if dataset == "AV":
        return "\n".join(
            [
                "**Answer: (A) Network**",
                "or **Answer: (B) Adjacent Network**",
                "or **Answer: (C) Physical**",
                "or **Answer: (D) Not Related**",
            ]
        )
    if dataset == "UI":
        return "**Answer: (A) Not Required**\nor\n**Answer: (B) Required**"
    return "**Answer: (A) Not High**\nor\n**Answer: (B) High**"

def _cvss_rules(dataset):
    if dataset == "AV":
        return """CVSS Attack Vector (AV) rules:
- Network: exploitable remotely across routable network paths or network protocol input.
- Adjacent Network: exploitable from same shared network segment, local subnet, Bluetooth, local link, or adjacent network boundary.
- Physical: requires physical interaction with the vulnerable component/device. In this dataset, driver/device/hardware/sound/scsi/clock/power-management/runtime-PM helpers often align with Physical when the function is about a local device component rather than a network path.
- Not Related: function context does not indicate AV-relevant attack reachability."""
    if dataset == "AC":
        return """CVSS Attack Complexity (AC) rules:
- High: exploitation requires special race conditions, uncommon state, precise timing, non-default configuration, or hard-to-satisfy environmental conditions.
- High evidence includes lock-held requirements, serialized operations, special internal state, ordering/timing assumptions, or hard-to-reach environmental setup.
- Not High: exploitation path is straightforward once attacker can reach the vulnerable function."""
    if dataset == "PR":
        return """CVSS Privileges Required (PR) rules:
- High: exploitation requires administrative/root/high privilege or prior privileged access.
- High evidence includes permission checks, access status, audit/security policy, dumpable/suid/credential handling, privileged device control, or explicit access-control wording.
- Not High: no privilege, low privilege, regular user access, or no clear evidence of high privilege."""
    if dataset == "UI":
        return """CVSS User Interaction (UI) rules:
- Required: exploitation requires a user or victim action, or the function is a user-facing/user-triggered operation in this dataset's labeling scheme.
- Not Required: exploit can proceed without a separate user action, or function is internal/hardware/protocol/background helper.
- Do not choose Required from the word user alone; weigh function role and description."""
    return "CVSS metric rules: choose the option best supported by function name and description."
