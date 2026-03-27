import os
import json
import tokens
import random
from tqdm import tqdm


def extract_heuristics(root, task, dataset, method='self-heuristic', n_samples_per_class=5):
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

    Returns:
        dict with 'heuristics' (str) containing the extracted rules
    """
    probe_file = os.path.join(root, task, dataset + '-probe.json')
    test_file = os.path.join(root, task, dataset + '-test.json')

    # Try probe first, fall back to test
    data_file = probe_file if os.path.exists(probe_file) else test_file
    if not os.path.exists(data_file):
        print(f"No probe or test file found for {task}/{dataset}")
        return {'heuristics': ''}

    with open(data_file) as f:
        data = json.load(f)

    if dataset in data:
        data = data[dataset]

    # Group samples by ground_truth
    class_samples = {}
    for id_ in data:
        gt = str(data[id_].get('ground_truth', ''))
        if gt not in class_samples:
            class_samples[gt] = []
        class_samples[gt].append({
            'id': id_,
            'function': data[id_].get('function', ''),
            'description': data[id_].get('description', ''),
            'ground_truth': gt
        })

    # CVSS AV class labels
    if dataset == 'AV':
        class_names = {
            '0': 'Not Related',
            '1': 'Network',
            '2': 'Adjacent Network',
            '3': 'Physical'
        }
    elif dataset in ['AC', 'PR', 'UI']:
        class_names = {
            '0': 'Not High',
            '1': 'High'
        }
    else:
        class_names = {str(i): f'Class {i}' for i in range(10)}

    # Build examples string for the prompt
    examples_str = []
    for gt, samples in sorted(class_samples.items(), key=lambda x: x[0]):
        label = class_names.get(gt, f'Class {gt}')
        examples_str.append(f"\n[{label} (Class {gt})]:")
        # Take up to n_samples_per_class
        for sample in samples[:n_samples_per_class]:
            examples_str.append(f"  - Function: {sample['function']}")
            examples_str.append(f"    Description: {sample['description'][:100]}...")

    examples_text = '\n'.join(examples_str)

    # Create the heuristics extraction prompt
    heuristics_prompt = f"""Bạn là một chuyên gia phân tích bảo mật phần mềm. Tôi đang xây dựng một hệ thống đánh giá mức độ nghiêm trọng của lỗ hổng dựa trên chuẩn CVSS v3.1, cụ thể là metric {dataset}.

Dưới đây là một số ví dụ về các hàm mã nguồn và nhãn {dataset} tương ứng của chúng:
{examples_text}

Nhiệm vụ của bạn: Dựa trên kiến thức của bạn và các ví dụ trên, hãy tóm tắt ngắn gọn và sắc bén "Đặc điểm nhận diện" (bao gồm chức năng, từ khóa thường gặp, pattern logic) cho từng loại {dataset}.

**QUAN TRỌNG**:
- Trả về MỖI QUY LUẬT cho từng class, theo format:
  **Class X (Label)**: [đặc điểm ngắn gọn, 2-3 câu]
- KHÔNG cần giải thích thêm, chỉ trả về phần tóm tắt quy luật.
- Tập trung vào các từ khóa và pattern đặc trưng giúp phân biệt các class.

Hãy bắt đầu:"""

    return {
        'heuristics': heuristics_prompt,
        'class_samples': class_samples,
        'class_names': class_names
    }


def generate_self_heuristic_system_prompt(dataset, heuristics_text, cot_instruction=True):
    """
    Build the system prompt for Round 2 (classification) by injecting extracted heuristics.

    Args:
        dataset: Dataset name (e.g., 'AV')
        heuristics_text: The extracted rules from Round 1
        cot_instruction: Whether to add step-by-step reasoning instruction

    Returns:
        str: The system prompt with injected heuristics
    """
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

    system_base = f"""You are Frederick, an elite AI cybersecurity expert specializing in vulnerability severity evaluation based on CVSS v3.1 standards.

To ensure extreme accuracy, you MUST strictly follow this domain knowledge when making your decision:

{heuristics_text}

CLASSIFICATION OPTIONS:
{categories}

Remember: You must heavily penalize the classification unless there is CLEAR evidence. When in doubt, prefer the safer option."""

    if cot_instruction:
        system_base += "\n\nLet's think step-by-step to reach the right conclusion."

    return system_base


def generate_prompt(root, task, dataset, method, max_tokens = 8000, TEST = 'vali', testNum = 1, extracted_heuristics=None):
    if TEST=='test':
        data_file = os.path.join(root, task, dataset+'-test.json')
    elif TEST=='vali':
        data_file = os.path.join(root, task, dataset+'-validation.json')
    elif TEST=='remain':
        data_file = os.path.join(root, task, dataset+'-remain.json')
    else:
        print('please input the right TEST!')
        exit()
    
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

    # Special handling for self-heuristic method (bypasses prompt template)
    if method == 'self-heuristic':
        # For self-heuristic, we build prompts manually using extracted_heuristics
        # Skip the normal prompt template loading
        prompt = []
    elif method in prompt:
        prompt = prompt[method]
    else:
        print('illegal method!')
        print(prompt.keys())
        exit()
    
    prompts = []
    prompt_item_num = 0
    for id in tqdm(data):
        if prompt_item_num>testNum:
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
            if method=='summary':
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
                    # Build prompt with custom system message
                    prompt_item = [
                        {'role': 'system', 'content': system_with_heuristics},
                        {'role': 'user', 'content': 'I will give you a function context. Classify it based on the expert knowledge provided.\n\n' + clonze + '\n\nBased on the expert knowledge provided, classify the function. After reasoning, output your final answer EXACTLY in this format:\n**Answer: (X) Label**'}
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