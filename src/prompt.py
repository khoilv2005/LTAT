import os
import json
import tokens
import random
from tqdm import tqdm

METHOD_ALIASES = {
    '0-shot': 'base',
    '1-shot': 'one-shot',
    'general-info': 'prompt-eng',
    # Paper terminology. Prompt JSONs store the manual domain-knowledge
    # template as info-manual.
    'expertise': 'info-manual',
}

TASK_ALIASES = {
    'sbrp': 'SBRP',
}

def normalize_task_name(task):
    return TASK_ALIASES.get(task, task)

def normalize_method_name(method):
    return METHOD_ALIASES.get(method, method)


def resolve_data_file(root, task, dataset, split):
    task = normalize_task_name(task)
    candidates = []
    if split == 'test':
        candidates.append(os.path.join(root, task, dataset + '-test.json'))
    elif split == 'probe':
        candidates.append(os.path.join(root, task, dataset + '-probe.json'))
    elif split == 'train':
        candidates.extend([
            os.path.join(root, task, dataset + '-train.json'),
            os.path.join(root, task, dataset + '-training.json'),
            os.path.join(root, task, dataset + '-train-part-1.json'),
        ])
    elif split == 'vali':
        candidates.append(os.path.join(root, task, dataset + '-validation.json'))
    elif split == 'remain':
        candidates.append(os.path.join(root, task, dataset + '-remain.json'))
    else:
        raise ValueError(f"Unknown split: {split}")

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(f"No {split} file found for {task}/{dataset}. Tried: {candidates}")

def select_prompt_template(prompt_templates, method):
    if method == 'self-heuristic':
        return []
    if method in prompt_templates:
        return prompt_templates[method]
    if method == 'code-only' and 'code-only-invalidator' in prompt_templates:
        return prompt_templates['code-only-invalidator']
    raise KeyError(f"illegal method: {method}. Available: {list(prompt_templates.keys())}")

def build_self_heuristic_prompt_item(system_prompt, item_text, question):
    return [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': item_text + '\n\n' + question},
    ]

def extract_heuristics(root, task, dataset, method='self-heuristic', n_samples_per_class=5, variant=None):
    """
    Round 1 of self-heuristic: Extract classification rules from training examples.

    This function selects diverse samples from each class and prompts the model
    to derive concise classification rules based on the examples.

    Args:
        root: Data root directory
        task: Task name (e.g., 'cvss')
        dataset: Dataset name (e.g., 'AV')
        method: Currently only 'self-heuristic'
        n_samples_per_class: Number of examples per class to include
        variant: Optional improvement variant id. When variant in {'v1','v7'},
                 APCA patches are kept up to 2000 chars instead of 150.

    Returns:
        dict with 'heuristics' (str) containing the extracted rules
    """
    task = normalize_task_name(task)
    method = normalize_method_name(method)
    probe_file = os.path.join(root, task, dataset + '-probe.json')
    train_files = [
        os.path.join(root, task, dataset + '-train.json'),
        os.path.join(root, task, dataset + '-training.json'),
        os.path.join(root, task, dataset + '-train-part-1.json'),
    ]

    # CRITICAL: Only use probe or training data for heuristics extraction
    # NEVER fall back to test file - this would cause data leakage
    #
    # Special case for SBRP Chromium: prioritize train over probe for more samples
    if dataset == 'Chromium' and task == 'SBRP':
        train_file = next((path for path in train_files if os.path.exists(path)), None)
        if train_file:
            data_file = train_file
        elif os.path.exists(probe_file):
            data_file = probe_file
        else:
            raise FileNotFoundError(f"No training or probe data found for {task}/{dataset}")
    elif os.path.exists(probe_file):
        data_file = probe_file
    elif any(os.path.exists(path) for path in train_files):
        train_file = next(path for path in train_files if os.path.exists(path))
        data_file = train_file
    else:
        # If neither probe nor training file exists, we CANNOT use test data
        # Doing so would leak test information into the heuristics extraction
        raise FileNotFoundError(
            f"CRITICAL: No training or probe data found for {task}/{dataset}. "
            f"Cannot use test data for heuristics extraction (data leakage prevention)."
        )

    with open(data_file) as f:
        data = json.load(f)

    if dataset in data:
        data = data[dataset]

    # Detect task type based on data structure
    sample = list(data.values())[0]
    if 'bug_report' in sample:
        task_type = 'SBRP'
    elif 'function' in sample:
        task_type = 'CVSS'
    elif 'patch' in sample or 'patch_code' in sample or 'patch_description' in sample:
        task_type = 'APCA'
    else:
        task_type = 'UNKNOWN'

    # Group samples by ground_truth
    class_samples = {}
    for id_ in data:
        gt = str(data[id_].get('ground_truth', ''))
        if gt not in class_samples:
            class_samples[gt] = []
        content = data[id_].get(
            'function',
            data[id_].get('bug_report', data[id_].get('patch', data[id_].get('patch_code', '')))
        )
        description = data[id_].get(
            'description',
            data[id_].get('bug_report', data[id_].get('patch_description', content))
        )
        class_samples[gt].append({
            'id': id_,
            'function': content,
            'description': description,
            'ground_truth': gt
        })

    # Class labels based on task type
    if task_type == 'CVSS':
        if dataset == 'AV':
            class_names = {
                '0': 'Not Related',
                '1': 'Network',
                '2': 'Adjacent Network',
                '3': 'Physical'
            }
        elif dataset in ['AC', 'PR']:
            class_names = {
                '0': 'Not High',
                '1': 'High'
            }
        elif dataset == 'UI':
            class_names = {
                '0': 'Not Required',
                '1': 'Required'
            }
        else:
            class_names = {str(i): f'Class {i}' for i in range(10)}
        task_desc = f"CVSS v3.1 {dataset} metric"
        example_label = "function"
    else:  # SBRP
        if task_type == 'APCA':
            class_names = {
                '0': 'Incorrect Patch',
                '1': 'Correct Patch',
                'Correct': 'Correct Patch',
                'Incorrect': 'Incorrect Patch',
            }
            task_desc = "Patch Correctness Assessment (APCA)"
            example_label = "patch"
        else:
            class_names = {
                '0': 'Non-Security Bug',
                '1': 'Security Bug'
            }
            task_desc = "Security Bug Report Prediction (SBRP)"
            example_label = "bug report"

    # Cap at n_samples_per_class for each class (don't min-sample across classes)
    # Class nào có ít hơn thì lấy hết, class nào có nhiều hơn thì lấy n_samples_per_class
    n_to_take = n_samples_per_class

    # V1/V5/V7: keep APCA patches longer so the model sees actual diff content
    apca_full_patch = task_type == 'APCA' and variant in ('v1', 'v5', 'v7')
    apca_patch_cap = 2000 if apca_full_patch else 150

    # Build examples string for the prompt
    examples_str = []
    for gt, samples in sorted(class_samples.items(), key=lambda x: x[0]):
        label = class_names.get(gt, f'Class {gt}')
        examples_str.append(f"\n[{label} (Class {gt})]:")
        # Take up to n_samples_per_class from each class
        for sample in samples[:n_to_take]:
            if task_type == 'APCA':
                content = sample['function'] if sample['function'] else sample['description']
                content = content[:apca_patch_cap]
                examples_str.append(f"  - Patch:\n```\n{content}\n```")
            else:
                content = sample['function'][:150] if sample['function'] else sample['description'][:150]
                if task_type == 'SBRP':
                    examples_str.append(f"  - Bug Report: {content}...")
                else:
                    examples_str.append(f"  - Function: {sample['function']}")
                    examples_str.append(f"    Description: {sample['description'][:100]}...")

    examples_text = '\n'.join(examples_str)

    # Create the heuristics extraction prompt
    if task_type == 'SBRP':
        heuristics_prompt = f"""You are a software security expert. I am building a bug report classification system to determine whether a bug report describes a security vulnerability (Security Bug) or a regular bug (Non-Security Bug).

Below are some examples of bug reports and their corresponding security/non-security labels:
{examples_text}

Your task: Based on your knowledge and the examples above, briefly summarize the "Identifying Characteristics" (including bug types, vulnerability patterns, keywords, and severity indicators) for each class.

**IMPORTANT**:
- Return the rule for EACH class, in the format:
  **Class X (Label)**: [brief description, 2-3 sentences]
- NO additional explanation needed, just return the rule summary.
- Focus on distinctive keywords and patterns that help differentiate between security and non-security bugs.

Let's begin:"""
    elif task_type == 'APCA':
        heuristics_prompt = f"""You are a software engineering expert. I am building a patch correctness assessment system to determine whether a patch correctly fixes the intended bug (Correct Patch) or is incorrect/incomplete (Incorrect Patch).

Below are some examples of patches and their correctness labels:
{examples_text}

Your task: Based on your knowledge and the examples above, briefly summarize the "Identifying Characteristics" for each class, including code-change patterns, bug-fix intent, suspicious incomplete fixes, and signals of overfitting or unrelated changes.

**IMPORTANT**:
- Return the rule for EACH class, in the format:
  **Class X (Label)**: [brief description, 2-3 sentences]
- NO additional explanation needed, just return the rule summary.
- Focus on patterns that help differentiate correct and incorrect patches.

Let's begin:"""
    else:
        heuristics_prompt = f"""You are a software security expert. I am building a vulnerability severity assessment system based on CVSS v3.1, specifically the {dataset} metric.

Below are some examples of source code functions and their corresponding {dataset} labels:
{examples_text}

Your task: Based on your knowledge and the examples above, briefly summarize the "Identifying Characteristics" (including function types, common keywords, and logic patterns) for each {dataset} class.

**IMPORTANT**:
- Return the rule for EACH class, in the format:
  **Class X (Label)**: [brief description, 2-3 sentences]
- NO additional explanation needed, just return the rule summary.
- Focus on distinctive keywords and patterns that help differentiate between classes.

Let's begin:"""

    return {
        'heuristics': heuristics_prompt,
        'class_samples': class_samples,
        'class_names': class_names,
        'task_type': task_type
    }


def generate_self_heuristic_system_prompt(dataset, heuristics_text, cot_instruction=True, task_type='CVSS', variant=None, class_prior_text=None):
    """
    Build the system prompt for Round 2 (classification) by injecting extracted heuristics.

    Args:
        dataset: Dataset name (e.g., 'AV')
        heuristics_text: The extracted rules from Round 1
        cot_instruction: Whether to add step-by-step reasoning instruction
        task_type: 'CVSS' or 'SBRP'
        variant: Optional improvement variant id. When variant in {'v3','v7'},
                 APCA system prompt is debiased (no "prefer safer option").
        class_prior_text: Optional dataset-specific class distribution string
                 used in V3/V5/V7 APCA prompts. When None, defaults to the
                 Invalidator-style "22% Correct / 78% Incorrect" message.

    Returns:
        str: The system prompt with injected heuristics
    """
    if task_type == 'SBRP':
        categories = "(A) Non-Security Bug, (B) Security Bug"
        system_base = f"""You are Frederick, an elite AI cybersecurity expert specializing in bug report classification for security vulnerability detection.

To ensure extreme accuracy, you MUST strictly follow this domain knowledge when making your decision:

{heuristics_text}

CLASSIFICATION OPTIONS:
{categories}

Remember: You must heavily penalize the classification unless there is CLEAR evidence of security relevance. When in doubt, prefer the safer option."""
    elif task_type == 'APCA':
        categories = "(A) Correct Patch, (B) Incorrect Patch"
        if variant in ('v3', 'v5', 'v7'):
            # V3/V5/V7: debiased version. The original prompt indirectly biases
            # the model toward "Incorrect" by emphasizing skepticism. Replace
            # the trailing instruction with a balance reminder and an explicit
            # class distribution note so the model assesses each patch on its
            # own merits.
            #
            # V5: also inject manual domain expertise loaded from
            # data/APCA/APCA_invalidator-manual-expertise.md. The expertise
            # text must be passed in via the heuristics_text argument
            # already (the caller is responsible for combining manual + learned
            # heuristics into a single text block).
            prior_line = class_prior_text or (
                "The dataset contains both Correct and Incorrect patches "
                "(roughly 22% Correct, 78% Incorrect on the test set, "
                "but treat priors as informational only)."
            )
            system_base = f"""You are Frederick, an elite AI software security expert specializing in patch correctness assessment.

Use the following domain knowledge as guidance when making your decision:

{heuristics_text}

CLASSIFICATION OPTIONS:
{categories}

Important context:
- {prior_line}
- Tool-generated patches (from APR tools such as kPAR, jGenProg, AVATAR, Cardumen, RSRepair, Nopol) appear in BOTH classes; do not penalize a patch just because it looks tool-generated.
- A minimal-looking diff can still be a Correct fix if it semantically resolves the bug; a verbose diff can still be an Incorrect fix if it overfits.

Remember: classify based strictly on the evidence in the patch; do not bias toward either class."""
        else:
            system_base = f"""You are Frederick, an elite AI software security expert specializing in patch correctness assessment.

To ensure extreme accuracy, you MUST strictly follow this domain knowledge when making your decision:

{heuristics_text}

CLASSIFICATION OPTIONS:
{categories}

Remember: Judge whether the patch actually fixes the intended bug, not whether the diff merely looks plausible."""
    else:
        if dataset == 'AV':
            categories = "(A) Network, (B) Adjacent Network, (C) Physical, (D) Not Related"
        elif dataset == 'AC':
            categories = "(A) Not High, (B) High"
        elif dataset == 'PR':
            categories = "(A) Not High, (B) High"
        elif dataset == 'UI':
            categories = "(A) Not Required, (B) Required"
        else:
            categories = "(A) Option A, (B) Option B"

        if task_type == 'CVSS' and dataset == 'UI' and variant in ('cvss-ui-v1', 'cvss-ui-v2'):
            if variant == 'cvss-ui-v2':
                ui_rule = """Important dataset-calibrated CVSS UI rule:
- Choose (B) Required when the function appears reachable through a user-facing kernel interface or a user-triggered operation: syscall, ioctl, read/write handler, mount/remount, mmap/VMA, debugfs/procfs/sysfs write, file operation, user pointer (`__user`), `udata`, userspace buffer copy, memory-region registration, quota/file metadata write, or filesystem operation that services user-controlled files.
- Choose (A) Not Required when the function is hardware/internal plumbing: probe/enumerate/init/remove, irq/interrupt, register read/write, protocol housekeeping, pure hash/tree/list/math conversion, internal lock/state helper, background worker cleanup, or helper code with no user-facing entry point.
- Do not choose Required for a keyword alone. Prefer Required when multiple cues point to a user-facing entry point or when the description explicitly mentions user data, user pointer, ioctl, debugfs/sysfs/procfs write, mount, mmap, file write/read, or userspace buffer handling.

Remember: balance precision and recall. Avoid labeling pure internal helpers as Required, but do not require an explicit click/open/browser-style victim action for this dataset."""
            else:
                ui_rule = """Important CVSS UI rule:
- Choose (B) Required only when successful exploitation requires a human user, other than the attacker, to perform an action such as opening a crafted file, visiting a malicious page, clicking a link, loading content, or otherwise interacting with attacker-controlled data.
- Choose (A) Not Required when the vulnerable function can be reached by the attacker directly through a request, packet, syscall, device operation, background processing, kernel-internal path, or already-triggered automated flow without a victim user's additional action.
- Do not classify as Required merely because the function name or description contains "user", "userdata", "udata", filesystem, mmap, ioctl, write, read, VMA, page, or file. Those words may describe attacker-controlled input or kernel/user-space memory, not a separate victim interaction step.

Remember: prefer (A) Not Required unless there is explicit evidence of an extra victim-user action required for exploitation."""
            system_base = f"""You are Frederick, an elite AI cybersecurity expert specializing in CVSS v3.1 User Interaction (UI) assessment.

Use the following domain knowledge as guidance when making your decision:

{heuristics_text}

CLASSIFICATION OPTIONS:
{categories}

{ui_rule}"""
        else:
            system_base = f"""You are Frederick, an elite AI cybersecurity expert specializing in vulnerability severity evaluation based on CVSS v3.1 standards.

To ensure extreme accuracy, you MUST strictly follow this domain knowledge when making your decision:

{heuristics_text}

CLASSIFICATION OPTIONS:
{categories}

Remember: You must heavily penalize the classification unless there is CLEAR evidence. When in doubt, prefer the safer option."""

    if cot_instruction:
        system_base += "\n\nLet's think step-by-step to reach the right conclusion."

    return system_base


def generate_prompt(root, task, dataset, method, max_tokens = 8000, TEST = 'vali', testNum = 1, extracted_heuristics=None, variant=None):
    task = normalize_task_name(task)
    method = normalize_method_name(method)

    data_file = resolve_data_file(root, task, dataset, TEST)
    
    prompt_file = os.path.join(root, task, dataset+'-prompt.json')
    if not os.path.exists(prompt_file):
        prompt_file = os.path.join(root, task, task+'-prompt.json')
    with open(prompt_file) as f:
        prompt = json.load(f)

    with open(data_file) as f:
        data = json.load(f)

    if dataset in data:
        data = data[dataset]
    else:
        print('illegal dataset!')
        exit()

    prompt = select_prompt_template(prompt, method)
    
    prompts = []
    prompt_item_num = 0
    for id in tqdm(data):
        if prompt_item_num >= testNum:
            break
        prompt_item = prompt[:-1]
        
        if dataset=='title_itape':
            clonze = data[id]['bug_report']
            if method=='summary':
                nshot_file = os.path.join(root, task, dataset+'-nshot.json')
                with open(nshot_file) as f:
                    nshot_data = json.load(f)[dataset]
                for nshot_id in nshot_data:
                    nshot_clonze = '\n'.join(['Bug report: '+nshot_data[nshot_id]['bug_report']])
                    ground_truth = nshot_data[nshot_id]['ground_truth']
                    prompt_item.append({'role':'user', 'content': nshot_clonze})
                    prompt_item.append({'role':'assistant', 'content': 'Category: '+ground_truth})
                clonze = ''
                prompt_user_2_content = prompt[-1]['content'].format(clonze)
                prompt_item.append({'role':'user', 'content':prompt_user_2_content})
                id = 'summary'
                ground_truth = ''
                prompts.append({'id':id, 'prompt':prompt_item, 'ground_truth': ground_truth})
                break
        
        elif dataset=='Chromium':
            if method=='self-heuristic':
                # Self-heuristic: inject extracted heuristics into system prompt
                if extracted_heuristics and 'system_prompt' in extracted_heuristics:
                    system_with_heuristics = extracted_heuristics['system_prompt']
                    clonze = data[id]['bug_report']
                    prompt_item = [
                        {'role': 'system', 'content': system_with_heuristics},
                        {'role': 'user', 'content': 'Bug Report:\n' + clonze + '\n\nBased on the expert knowledge provided, classify whether this is a Security Bug or Non-Security Bug. After reasoning, output your final answer EXACTLY in this format:\n**Answer: (X) Label**'}
                    ]
                    ground_truth = data[id]['ground_truth']
                    prompts.append({'id': id, 'prompt': prompt_item, 'ground_truth': ground_truth})
                    prompt_item_num += 1
                    continue
            elif method=='summary':
                nshot_file = os.path.join(root, task, dataset+'-nshot.json')
                with open(nshot_file) as f:
                    nshot_data = json.load(f)[dataset]
                # nshot_message = []
                for nshot_id in nshot_data:
                    nshot_clonze = '\n'.join(['Bug report: '+nshot_data[nshot_id]['bug_report']])
                    key_list = ["non-security bug report", "security bug report"]
                    ground_truth = key_list[int(nshot_data[nshot_id]['ground_truth'])]
                    prompt_item.append({'role':'user', 'content': nshot_clonze})
                    prompt_item.append({'role':'assistant', 'content': 'Category: '+ground_truth})
                clonze = ''
                prompt_user_2_content = prompt[-1]['content'].format(clonze)
                prompt_item.append({'role':'user', 'content':prompt_user_2_content})
                id = 'summary'
                ground_truth = ''
                prompts.append({'id':id, 'prompt':prompt_item, 'ground_truth': ground_truth})
                break
            else:
                clonze = data[id]['bug_report']

        elif dataset in ['Ambari', 'Camel', 'Derby', 'Wicket']:
            if method == 'self-heuristic':
                # Self-heuristic: inject extracted heuristics into system prompt
                if extracted_heuristics and 'system_prompt' in extracted_heuristics:
                    system_with_heuristics = extracted_heuristics['system_prompt']
                    clonze = data[id]['bug_report']
                    prompt_item = [
                        {'role': 'system', 'content': system_with_heuristics},
                        {'role': 'user', 'content': 'Bug Report:\n' + clonze + '\n\nBased on the expert knowledge provided, classify whether this is a Security Bug or Non-Security Bug. After reasoning, output your final answer EXACTLY in this format:\n**Answer: (X) Label**'}
                    ]
                    ground_truth = data[id]['ground_truth']
                    prompts.append({'id': id, 'prompt': prompt_item, 'ground_truth': ground_truth})
                    prompt_item_num += 1
                    continue
            clonze = data[id]['bug_report']

        elif dataset=='stable_patchnet':
            if method=='summary':
                nshot_file = os.path.join(root, task, dataset+'-nshot.json')
                with open(nshot_file) as f:
                    nshot_data = json.load(f)[dataset]
                # nshot_message = []
                for nshot_id in nshot_data:
                    nshot_clonze = 'Patch: '+ nshot_data[nshot_id]['patch']
                    if nshot_data[nshot_id]['ground_truth']=='true':
                        ground_truth = 'ACK'
                    else:
                        ground_truth = 'NAK'
                    prompt_item.append({'role':'user', 'content': nshot_clonze})
                    prompt_item.append({'role':'assistant', 'content': 'Category: '+ground_truth})
                clonze = ''
                prompt_user_2_content = prompt[-1]['content'].format(clonze)
                prompt_item.append({'role':'user', 'content':prompt_user_2_content})
                id = 'summary'
                ground_truth = ''
                prompts.append({'id':id, 'prompt':prompt_item, 'ground_truth': ground_truth})
                break
            elif method=='few-shot':
                clonze = '\n'.join([data[id]['title'], data[id]['message_xtrailer'], data[id]['diff']])
            else:
                clonze = data[id]['patch']
        
        elif dataset=='APCA_quatrain':
            if method=='self-heuristic':
                if extracted_heuristics and 'system_prompt' in extracted_heuristics:
                    system_with_heuristics = extracted_heuristics['system_prompt']
                    patch_text = data[id].get('patch_code') or data[id].get('patch_description', '')
                    prompt_item = build_self_heuristic_prompt_item(
                        system_with_heuristics,
                        'Patch:\n' + patch_text,
                        'Based on the expert knowledge provided, classify whether this is a Correct Patch or Incorrect Patch. After reasoning, output your final answer EXACTLY in this format:\n**Answer: (X) Label**'
                    )
                    ground_truth = data[id]['ground_truth']
                    prompts.append({'id': id, 'prompt': prompt_item, 'ground_truth': ground_truth})
                    prompt_item_num += 1
                    continue
            if method=='info-manual':
                bug_description = data[id]['bug_description']
                token_test_message = {'role':'user', 'content':bug_description}        
                if tokens.num_tokens_from_messages([token_test_message])>max_tokens//2:
                    print('bug report processing ({} tokens): {}'.format(max_tokens//2, id))
                    bug_description = tokens.message_process(token_test_message, max_tokens//2)['content']
                clonze = '\n'.join([
                    'Bug report: ', 
                    data[id]['bug_summary'], 
                    bug_description,
                    'Patch: ', 
                    data[id]['patch_description'], 
                    # data[id]['patch_code']
                    ])
            elif method=='info-gpt':
                bug_description = data[id]['bug_description']
                patch_description = data[id]['patch_description']
                token_test_message = {'role':'user', 'content':bug_description}        
                if tokens.num_tokens_from_messages([token_test_message])>max_tokens//2:
                    print('bug report processing ({} tokens): {}'.format(max_tokens//2, id))
                    bug_description = tokens.message_process(token_test_message, max_tokens//2)['content']
                clonze = '\n'.join([
                    'Bug report: ', 
                    data[id]['bug_summary'], 
                    bug_description,
                    'Patch: ', 
                    patch_description, 
                    # data[id]['patch_code']
                    ])
            elif method=='info-code':
                bug_description = data[id]['bug_description']
                patch_description = data[id]['patch_description_gpt']
                token_test_message = {'role':'user', 'content':bug_description}        
                if tokens.num_tokens_from_messages([token_test_message])>max_tokens//2:
                    print('bug report processing ({} tokens): {}'.format(max_tokens//2, id))
                    bug_description = tokens.message_process(token_test_message, max_tokens//2)['content']
                clonze = '\n'.join([
                    'Bug report: ', 
                    data[id]['bug_summary'], 
                    bug_description,
                    'Patch: ', 
                    patch_description, 
                    data[id]['patch_code']
                    ])
            elif method=='code-only':
                clonze = 'Patch:\n' + data[id]['patch_code']
            elif method=='summary':
                nshot_file = os.path.join(root, task, dataset+'-nshot.json')
                with open(nshot_file) as f:
                    nshot_data = json.load(f)[dataset]
                # nshot_message = []
                for nshot_id in nshot_data:
                    bug_description = nshot_data[nshot_id]['bug_summary']
                    patch = nshot_data[nshot_id]['patch_description']
                    nshot_clonze = '\n'.join([
                        'Bug report: ', bug_description,
                        'Patch: ', patch])
                    if nshot_data[nshot_id]['ground_truth']=='1':
                        ground_truth = 'CoF'
                    else:
                        ground_truth = 'NCF'
                    prompt_item.append({'role':'user', 'content': nshot_clonze})
                    prompt_item.append({'role':'assistant', 'content': 'Category: '+ground_truth})
                clonze = ''
                prompt_user_2_content = prompt[-1]['content'].format(clonze)
                prompt_item.append({'role':'user', 'content':prompt_user_2_content})
                id = 'summary'
                ground_truth = ''
                prompts.append({'id':id, 'prompt':prompt_item, 'ground_truth': ground_truth})
                break
            else:
                clonze = '\n'.join([
                    'Bug report: '+ data[id]['bug_summary'], 
                    data[id]['bug_description'],
                    'Patch: ' + data[id]['patch_description']])
        elif dataset=='APCA_panther':
            if method=='self-heuristic':
                if extracted_heuristics and 'system_prompt' in extracted_heuristics:
                    system_with_heuristics = extracted_heuristics['system_prompt']
                    if variant in ('v4', 'v5', 'v7'):
                        question = (
                            "Analyze this patch in three explicit steps before answering:\n"
                            "Step 1 (Bug intent): From the file paths, function names, and surrounding context lines, infer what bug the original code likely has.\n"
                            "Step 2 (Patch effect): Describe what the diff actually changes semantically (added checks, removed branches, modified conditions, etc.), not just textually.\n"
                            "Step 3 (Verdict): Decide whether the change in Step 2 plausibly resolves the bug inferred in Step 1, considering side effects.\n"
                            "After completing the three steps, output your final answer EXACTLY in this format on its own line:\n"
                            "**Answer: (X) Label**"
                        )
                    else:
                        question = (
                            'Based on the expert knowledge provided, classify whether this is a Correct Patch or Incorrect Patch. '
                            'After reasoning, output your final answer EXACTLY in this format:\n**Answer: (X) Label**'
                        )
                    prompt_item = build_self_heuristic_prompt_item(
                        system_with_heuristics,
                        'Patch:\n' + data[id]['patch'],
                        question,
                    )
                    ground_truth = data[id]['ground_truth']
                    prompts.append({'id': id, 'prompt': prompt_item, 'ground_truth': ground_truth})
                    prompt_item_num += 1
                    continue
            if method=='summary':
                nshot_file = os.path.join(root, task, dataset+'-nshot.json')
                with open(nshot_file) as f:
                    nshot_data = json.load(f)[dataset]
                for nshot_id in nshot_data:
                    patch = nshot_data[nshot_id]['patch']
                    nshot_clonze = 'Patch:\n'+patch
                    if nshot_data[nshot_id]['ground_truth']=='Correct':
                        ground_truth = 'CoF'
                    else:
                        ground_truth = 'NCF'
                    prompt_item.append({'role':'user', 'content': nshot_clonze})
                    prompt_item.append({'role':'assistant', 'content': 'Category: '+ground_truth})
                clonze = ''
                prompt_user_2_content = prompt[-1]['content'].format(clonze)
                prompt_item.append({'role':'user', 'content':prompt_user_2_content})
                id = 'summary'
                ground_truth = ''
                prompts.append({'id':id, 'prompt':prompt_item, 'ground_truth': ground_truth})
                break
            else:
                clonze = 'Patch:\n' + data[id]['patch']
        elif dataset=='APCA_invalidator':
            if method=='self-heuristic':
                if extracted_heuristics and 'system_prompt' in extracted_heuristics:
                    system_with_heuristics = extracted_heuristics['system_prompt']
                    if variant in ('v4', 'v5', 'v7'):
                        # V4/V5/V7: three-step reasoning instructed in the user
                        # message. Final answer line is preserved so that
                        # eval.py::extract_prediction can still parse it.
                        question = (
                            "Analyze this patch in three explicit steps before answering:\n"
                            "Step 1 (Bug intent): From the file paths, function names, and surrounding context lines, infer what bug the original code likely has.\n"
                            "Step 2 (Patch effect): Describe what the diff actually changes semantically (added checks, removed branches, modified conditions, etc.), not just textually.\n"
                            "Step 3 (Verdict): Decide whether the change in Step 2 plausibly resolves the bug inferred in Step 1, considering side effects.\n"
                            "After completing the three steps, output your final answer EXACTLY in this format on its own line:\n"
                            "**Answer: (X) Label**"
                        )
                    else:
                        question = (
                            'Based on the expert knowledge provided, classify whether this is a Correct Patch or Incorrect Patch. '
                            'After reasoning, output your final answer EXACTLY in this format:\n**Answer: (X) Label**'
                        )
                    prompt_item = build_self_heuristic_prompt_item(
                        system_with_heuristics,
                        'Patch:\n' + data[id]['patch'],
                        question,
                    )
                    ground_truth = data[id]['ground_truth']
                    prompts.append({'id': id, 'prompt': prompt_item, 'ground_truth': ground_truth})
                    prompt_item_num += 1
                    continue
            if method=='summary':
                nshot_file = os.path.join(root, task, dataset+'-nshot.json')
                with open(nshot_file) as f:
                    nshot_data = json.load(f)[dataset]
                for nshot_id in nshot_data:
                    patch = nshot_data[nshot_id]['patch']
                    nshot_clonze = 'Patch:\n'+patch
                    if nshot_data[nshot_id]['ground_truth']=='Correct':
                        ground_truth = 'CoF'
                    else:
                        ground_truth = 'NCF'
                    prompt_item.append({'role':'user', 'content': nshot_clonze})
                    prompt_item.append({'role':'assistant', 'content': 'Category: '+ground_truth})
                clonze = ''
                prompt_user_2_content = prompt[-1]['content'].format(clonze)
                prompt_item.append({'role':'user', 'content':prompt_user_2_content})
                id = 'summary'
                ground_truth = ''
                prompts.append({'id':id, 'prompt':prompt_item, 'ground_truth': ground_truth})
                break
            else:
                clonze = 'Patch:\n' + data[id]['patch']
        
        elif task=='cvss':
            if method=='manual-info':
                clonze = '\n'.join(['Function: '+data[id]['function'],
                                    data[id]['description']])
            elif method=='summary':
                nshot_file = os.path.join(root, task, dataset+'-nshot.json')
                with open(nshot_file) as f:
                    nshot_data = json.load(f)[dataset]
                suffle_temp = list(nshot_data.items())
                random.seed(0)
                random.shuffle(suffle_temp)
                nshot_data = dict(suffle_temp)
                # nshot_message = []
                for nshot_id in nshot_data:
                    nshot_clonze = '\n'.join(['Function: '+nshot_data[nshot_id]['function'],
                                    nshot_data[nshot_id]['description']])
                    if dataset=="AV":
                        key_list = ["Not Related", "Network", "Adjacent Network", "Physical"]
                    elif dataset=="AC":
                        key_list = ["Not High", "High"]
                    elif dataset=="PR":
                        key_list = ["Not High", "High"]
                    elif dataset=="UI":
                        key_list = ["Not Required", "Required"]
                    ground_truth = key_list[int(nshot_data[nshot_id]['ground_truth'])]
                    prompt_item.append({'role':'user', 'content': nshot_clonze})
                    prompt_item.append({'role':'assistant', 'content': 'Category: '+ground_truth})
                    if tokens.num_tokens_from_messages(prompt_item)>7500:
                        print(len(prompt_item)/2)
                        break
                clonze = ''
                prompt_user_2_content = prompt[-1]['content'].format(clonze)
                prompt_item.append({'role':'user', 'content':prompt_user_2_content})
                id = 'summary'
                ground_truth = ''
                prompts.append({'id':id, 'prompt':prompt_item, 'ground_truth': ground_truth})
                break
            elif method=='self-heuristic':
                # Self-heuristic: inject extracted heuristics into system prompt
                if extracted_heuristics and 'system_prompt' in extracted_heuristics:
                    # Use custom system prompt with heuristics
                    system_with_heuristics = extracted_heuristics['system_prompt']
                    clonze = '\n'.join(['Function: '+data[id]['function'],
                                        'Function description: '+data[id]['description']])
                    if dataset == 'UI' and variant in ('cvss-ui-v1', 'cvss-ui-v2'):
                        if variant == 'cvss-ui-v2':
                            question = (
                                "Analyze this function for the CVSS UI label in three steps:\n"
                                "Step 1 (User-facing cues): List cues such as syscall/ioctl/read/write/mount/mmap/debugfs/sysfs/procfs/user pointer/udata/userspace buffer/filesystem user operation.\n"
                                "Step 2 (Internal-only cues): List cues such as probe/init/irq/register/hardware/protocol housekeeping/hash/tree/math/internal helper/background cleanup.\n"
                                "Step 3 (Verdict): Choose Required if Step 1 has stronger evidence; choose Not Required if Step 2 dominates or there is no clear user-facing entry point.\n"
                                "After completing the three steps, output your final answer EXACTLY in this format on its own line:\n"
                                "**Answer: (X) Label**"
                            )
                        else:
                            question = (
                                "Analyze this function for the CVSS v3.1 User Interaction metric in three steps:\n"
                                "Step 1 (Reachability): Identify whether the function is reached directly by an attacker-controlled request/input path, or only after an additional victim-user action.\n"
                                "Step 2 (Interaction evidence): List the concrete words in the function name/description that prove a separate victim user must act. If the evidence is only generic terms such as user, udata, file, ioctl, mmap, read, write, page, or VMA, say that this is not enough by itself.\n"
                                "Step 3 (Verdict): Choose Required only if Step 2 found explicit victim-user action evidence; otherwise choose Not Required.\n"
                                "After completing the three steps, output your final answer EXACTLY in this format on its own line:\n"
                                "**Answer: (X) Label**"
                            )
                    else:
                        question = (
                            "Based on the expert knowledge provided, classify the function. "
                            "After reasoning, output your final answer EXACTLY in this format:\n"
                            "**Answer: (X) Label**"
                        )
                    # Build prompt with custom system message
                    prompt_item = [
                        {'role': 'system', 'content': system_with_heuristics},
                        {'role': 'user', 'content': 'I will give you a function context. Classify it based on the expert knowledge provided.\n\n' + clonze + '\n\n' + question}
                    ]
                    ground_truth = data[id]['ground_truth']
                    prompts.append({'id': id, 'prompt': prompt_item, 'ground_truth': ground_truth})
                    prompt_item_num += 1
                    continue
                else:
                    # Fallback to base if no heuristics provided
                    clonze = '\n'.join(['Function: '+data[id]['function'],
                                        'Function description: '+data[id]['description']])
            else:
                clonze = '\n'.join(['Function: '+data[id]['function'],
                                    'Function description: '+data[id]['description']])
        
        elif dataset=='vulfix_extractfix':
            if method=='info-manual':
                clonze = data[id]['info-manual']
            else:
                clonze = data[id]['base']

        if method == 'self-heuristic':
            raise ValueError("self-heuristic requires extracted_heuristics with a system_prompt")

        if dataset=='vulfix_extractfix' or method=='summary':
            ground_truth = ''
        else:
            ground_truth = data[id]['ground_truth']
        prompt_user_2_content = prompt[-1]['content'].format(clonze)
        prompt_user_2 = {'role':'user', 'content':prompt_user_2_content}        
        if tokens.num_tokens_from_messages([prompt_user_2])>max_tokens:
            print('message processing ({} tokens): {}'.format(max_tokens, id))
            prompt_user_2 = tokens.message_process(prompt_user_2, max_tokens)
        prompt_item.append(prompt_user_2)

        prompts.append({'id':id, 'prompt':prompt_item, 'ground_truth': ground_truth})
        prompt_item_num += 1

    print(len(prompts))
    return prompts
