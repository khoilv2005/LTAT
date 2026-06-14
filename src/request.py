from email.mime import message
import os
import re
import json
import math
import time
import random
import logging
import tiktoken
import multiprocessing as mp
import numpy as np
import argparse
import aiohttp
import asyncio  # for running API calls concurrently
import subprocess
from dataclasses import dataclass, field  # for storing API inputs, outputs, and metadata
import shutil
import os

from tqdm import tqdm
from nltk.corpus import stopwords

import prompt

logger = logging.getLogger(__name__)
time_tag = time.strftime("%m%d%H%M", time.localtime())

def build_chat_request_payload(model, messages, temperature=0, choices=1, max_token=8000, request_url=""):
    """Build a provider-specific chat payload without changing result parsing."""
    request_url_lower = (request_url or "").lower()
    if "aiplatform.googleapis.com" in request_url_lower:
        system_parts = []
        contents = []
        for message in messages:
            role = message.get("role", "user")
            content = str(message.get("content", ""))
            if role == "system":
                system_parts.append({"text": content})
            else:
                vertex_role = "model" if role == "assistant" else "user"
                contents.append({"role": vertex_role, "parts": [{"text": content}]})
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "topP": 1,
                "maxOutputTokens": max_token,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}
        if choices and choices > 1:
            payload["generationConfig"]["candidateCount"] = choices
        return payload

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": 1,
        "stream": False,
    }

    if "ollama" in request_url_lower:
        payload["think"] = False
        payload["options"] = {"num_predict": min(max_token, 2048)}
    else:
        payload["max_tokens"] = max_token
        if choices and choices > 1:
            payload["n"] = choices

    return payload

def resolve_api_key(api_key, request_url=""):
    if api_key:
        return api_key

    request_url_lower = (request_url or "").lower()
    if "aiplatform.googleapis.com" in request_url_lower:
        for env_name in ["VERTEX_ACCESS_TOKEN", "GOOGLE_OAUTH_ACCESS_TOKEN"]:
            value = os.environ.get(env_name)
            if value:
                return value
        command = os.environ.get("VERTEX_ACCESS_TOKEN_COMMAND", "gcloud auth print-access-token")
        try:
            token = subprocess.check_output(command, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            if token:
                return token
        except Exception:
            pass

    env_candidates = []
    if "openai" in request_url_lower:
        env_candidates.append("OPENAI_API_KEY")
    elif "minimax" in request_url_lower:
        env_candidates.append("MINIMAX_API_KEY")
    elif "ollama" in request_url_lower:
        env_candidates.append("OLLAMA_API_KEY")

    env_candidates.extend(["OPENAI_API_KEY", "MINIMAX_API_KEY", "OLLAMA_API_KEY"])
    for env_name in env_candidates:
        value = os.environ.get(env_name)
        if value:
            return value

    raise ValueError(
        "API key not provided. Set OPENAI_API_KEY, MINIMAX_API_KEY, "
        "OLLAMA_API_KEY, VERTEX_ACCESS_TOKEN, or pass --api_key."
    )

def num_tokens_from_messages(messages, model="gpt-3.5-turbo-0301"):
    """Returns the number of tokens used by a list of messages."""
    # Check if model is known or uses cl100k_base encoding
    known_models = ['gpt-3.5-turbo', 'gpt-4', 'gpt-3.5-turbo-0301', 'gpt-4-0314']
    uses_cl100k = any(x in model.lower() for x in ['gpt-3.5', 'gpt-4', 'minimax', 'glm', 'ollama', 'nemotron', 'qwen', 'deepseek', 'gemini'])

    if not uses_cl100k and model not in known_models:
        raise NotImplementedError(f"""num_tokens_from_messages() is not implemented for model {model}. See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens.""")

    # Use cl100k_base for these models (same as GPT-3.5)
    encoding = tiktoken.get_encoding("cl100k_base")

    if model == "gpt-3.5-turbo":
        # print("Warning: gpt-3.5-turbo may change over time. Returning num tokens assuming gpt-3.5-turbo-0301.")
        return num_tokens_from_messages(messages, model="gpt-3.5-turbo-0301")
    elif model == "gpt-4":
        # print("Warning: gpt-4 may change over time. Returning num tokens assuming gpt-4-0314.")
        return num_tokens_from_messages(messages, model="gpt-4-0314")
    elif model == "gpt-3.5-turbo-0301":
        tokens_per_message = 4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
        tokens_per_name = -1  # if there's a name, the role is omitted
    elif model == "gpt-4-0314":
        tokens_per_message = 3
        tokens_per_name = 1
    elif 'gpt-3.5' in model:
        return num_tokens_from_messages(messages, model="gpt-3.5-turbo-0301")
    elif 'minimax' in model.lower() or 'glm' in model.lower() or 'ollama' in model.lower() or 'nemotron' in model.lower() or 'qwen' in model.lower() or 'deepseek' in model.lower() or 'gemini' in model.lower():
        # Ollama/glm/nemotron/qwen uses cl100k_base encoding, same as GPT-3.5
        tokens_per_message = 4
        tokens_per_name = -1
    else:
        raise NotImplementedError(f"""num_tokens_from_messages() is not implemented for model {model}. See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens.""")
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens

async def async_api_requests(
    max_requests_per_minute: float,
    max_tokens_per_minute: float,
    request_url: str,
    api_key: str = None,
    root_path:str = None,
    result_file_path: str = None,
    result_file_name: str = None,
    task: str = None,
    dataset: str = None,
    model: str ='glm-5.1:cloud',
    dataNum: int =0,
    testNum: int =1,
    method: str ='base',
    max_token: int =8000,
    response_max_token: int = None,
    max_attempts: int =10,
    max_concurrent_requests: int =2,
    save_every: int =50,
    temperature: float = 0,
    choices: int = 1,
    data = None,
    ):

    vertex_auth = "aiplatform.googleapis.com" in (request_url or "").lower() and not api_key
    api_key = resolve_api_key(api_key, request_url)
    """Processes API requests in parallel, throttling to stay under rate limits."""
    # constants
    seconds_to_pause_after_rate_limit_error = 60
    seconds_to_sleep_each_loop = 0.01  # 1 ms limits max throughput to 1,000 requests per second

    # infer API endpoint and construct request header
    request_header = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if vertex_auth:
        request_header["X-Refresh-Vertex-Token"] = "1"

    # initialize trackers
    queue_of_requests_to_retry = asyncio.Queue()
    status_tracker = StatusTracker()  # single instance to track a collection of variables
    write_lock = asyncio.Lock()
    next_request = None  # variable to hold the next request to call

    # initialize available capacity counts
    available_request_capacity = max_requests_per_minute
    available_token_capacity = max_tokens_per_minute
    last_update_time = time.time()

    # initialize flags
    not_finished = True
    
    # initialize file path
    if not os.path.exists(result_file_path):
        os.makedirs(result_file_path)
    results_json_file = os.path.join(result_file_path, result_file_name + ".json")

    """read results from json file"""
    print(results_json_file)
    results_list = load_results_file(results_json_file)
    results_list = [item for item in results_list if not is_error_result(item)]

    existing_ids = {str(item.get('id')) for item in results_list if isinstance(item, dict)}
    testNum = min(testNum, len(data))
    if existing_ids:
        data = data[:testNum]
        data = [item for item in data if str(item.get('id')) not in existing_ids]
        print(f"Skipping {len(existing_ids)} existing results; {len(data)} requests remaining")
        testNum = len(data)
        dataNum = 0

    if testNum == 0:
        print("No requests remaining; keeping existing results file unchanged")
        return

    """config logging file"""
    logging_level = 'WARNING'
    logging.basicConfig(format='%(asctime)s %(message)s', filename=os.path.join(result_file_path, result_file_name+".log"), encoding='utf-8', level=logging_level)
    logging.debug(f"Logging initialized at level {logging_level}")
    logging.debug(f"Initialization complete.")

    """call api"""
    # openai.api_key = api_key  # Not needed for Ollama
    testNum = min(testNum, len(data))
    global pbar
    pbar = tqdm(total = testNum-dataNum)
    timeout = aiohttp.ClientTimeout(total=300, connect=30, sock_connect=30, sock_read=240)
    session = aiohttp.ClientSession(timeout=timeout)
    while(True):
        if status_tracker.fatal_error:
            not_finished = False
            if next_request is not None:
                status_tracker.num_tasks_in_progress -= 1
                next_request = None

        # get next request (if one is not already waiting for capacity)
        if next_request is None:
            if status_tracker.fatal_error:
                pass
            elif not queue_of_requests_to_retry.empty(): 
                next_request = queue_of_requests_to_retry.get_nowait()
                logging.debug(f"Retrying request {next_request.request_id}: {next_request}")
            elif (not_finished):
                if dataNum<testNum:                    
                    request_id = data[dataNum]['id']
                    messages = data[dataNum]['prompt']
                    request_truth = data[dataNum]['ground_truth']
                    
                    request_json = build_chat_request_payload(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        choices=choices,
                        max_token=response_max_token or max_token,
                        request_url=request_url,
                    )
                    next_request = APIRequest(
                        request_id=request_id,
                        request_json=request_json,
                        request_truth=request_truth,
                        token_consumption=num_tokens_from_messages(messages, model),
                        attempts_left=max_attempts,
                        metadata=request_json.pop("metadata", None),
                        results_list=results_list,
                    )
                    status_tracker.num_tasks_started += 1
                    status_tracker.num_tasks_in_progress += 1
                    logging.debug(f"Reading request {next_request.request_id}: {next_request}")
                    dataNum += 1
                    
                else:
                    # if file runs out, set flag to stop reading it
                    logging.debug("Read file exhausted")
                    not_finished = False

        # update available capacity
        current_time = time.time()
        seconds_since_update = current_time - last_update_time
        available_request_capacity = min(
            available_request_capacity + max_requests_per_minute * seconds_since_update / 60.0,
            max_requests_per_minute,
        )
        available_token_capacity = min(
            available_token_capacity + max_tokens_per_minute * seconds_since_update / 60.0,
            max_tokens_per_minute,
        )
        last_update_time = current_time

        # if enough capacity available, call API
        if next_request:
            next_request_tokens = next_request.token_consumption
            if (
                available_request_capacity >= 1
                and available_token_capacity >= next_request_tokens
                and status_tracker.num_tasks_active < max_concurrent_requests
            ):
                # update counters
                available_request_capacity -= 1
                available_token_capacity -= next_request_tokens
                next_request.attempts_left -= 1
                status_tracker.num_tasks_active += 1

                # call API
                asyncio.create_task(
                    next_request.call_api(
                        request_url=request_url,
                        request_header=request_header,
                        retry_queue=queue_of_requests_to_retry,
                        save_filepath=results_json_file,
                        status_tracker=status_tracker,
                        write_lock=write_lock,
                        save_every=save_every,
                        session=session,
                    )
                )
                next_request = None  # reset next_request to empty

        # if all tasks are finished, break
        if status_tracker.num_tasks_in_progress == 0:
            break

        # main loop sleeps briefly so concurrent tasks can run
        await asyncio.sleep(seconds_to_sleep_each_loop)

        # if a rate limit error was hit recently, pause to cool down
        seconds_since_rate_limit_error = (time.time() - status_tracker.time_of_last_rate_limit_error)
        if seconds_since_rate_limit_error < seconds_to_pause_after_rate_limit_error:
            remaining_seconds_to_pause = (seconds_to_pause_after_rate_limit_error - seconds_since_rate_limit_error)
            await asyncio.sleep(remaining_seconds_to_pause)
            # ^e.g., if pause is 15 seconds and final limit was hit 5 seconds ago
            logging.warning(f"Pausing to cool down until {time.ctime(status_tracker.time_of_last_rate_limit_error + seconds_to_pause_after_rate_limit_error)}")

    await session.close()

    # after finishing, log final status
    write_file(results_list, results_json_file)
    logging.info(f"""Parallel processing complete. Results saved to {results_json_file}""")
    if status_tracker.num_tasks_failed > 0:
        logging.warning(f"{status_tracker.num_tasks_failed} / {status_tracker.num_tasks_started} requests failed. Errors logged to {results_json_file}.")
        raise RuntimeError(status_tracker.fatal_error_message or "Request failed after all retry attempts")
    if status_tracker.num_rate_limit_errors > 0:
        logging.warning(f"{status_tracker.num_rate_limit_errors} rate limit errors received. Consider running at a lower rate.")

@dataclass
class StatusTracker:
    """Stores metadata about the script's progress. Only one instance is created."""
    num_tasks_started: int = 0
    num_tasks_in_progress: int = 0  # script ends when this reaches 0
    num_tasks_succeeded: int = 0
    num_tasks_failed: int = 0
    num_rate_limit_errors: int = 0
    num_api_errors: int = 0  # excluding rate limit errors, counted above
    num_other_errors: int = 0
    time_of_last_rate_limit_error: int = 0  # used to cool off after hitting rate limits
    num_results_since_save: int = 0
    num_tasks_active: int = 0  # in-flight HTTP attempts, excludes queued retries
    fatal_error: bool = False
    fatal_error_message: str = ""

@dataclass
class APIRequest:
    """Stores an API request's inputs, outputs, and other metadata. Contains a method to make an API call."""

    request_id: int
    request_json: dict
    request_truth: str
    token_consumption: int
    attempts_left: int
    metadata: dict
    results_list: list
    result: list = field(default_factory=list)
    

    async def call_api(
        self,
        request_url: str,
        request_header: dict,
        retry_queue: asyncio.Queue,
        save_filepath: str,
        status_tracker: StatusTracker,
        write_lock: asyncio.Lock,
        save_every: int,
        session: aiohttp.ClientSession = None,
    ):
        """Calls the OpenAI API and saves results."""
        logging.info(f"Starting request #{self.request_id}")
        error = None
        response_data = {}
        try:
            post_header = dict(request_header)
            if post_header.pop("X-Refresh-Vertex-Token", None):
                post_header["Authorization"] = f"Bearer {resolve_api_key(None, request_url)}"
            if session is None:
                timeout = aiohttp.ClientTimeout(total=300, connect=30, sock_connect=30, sock_read=240)
                async with aiohttp.ClientSession(timeout=timeout) as owned_session:
                    async with owned_session.post(
                        url=request_url, headers=post_header, json=self.request_json
                    ) as http_response:
                        text = await http_response.text()
            else:
                async with session.post(
                    url=request_url, headers=post_header, json=self.request_json
                ) as http_response:
                    text = await http_response.text()

            # Handle NDJSON (streaming) responses
            try:
                response_data = json.loads(text)
            except json.JSONDecodeError:
                lines = text.strip().split('\n')
                response_data = json.loads(lines[0]) if lines else {}
            if "error" in response_data:
                error_obj = response_data["error"]
                error_message = error_obj.get("message", "") if isinstance(error_obj, dict) else str(error_obj)
                logging.warning(
                    f"Request {self.request_id} failed with error {error_obj}"
                )
                status_tracker.num_api_errors += 1
                error = response_data
                if (
                    "rate limit" in error_message.lower()
                    or "too many concurrent" in error_message.lower()
                    or "resource exhausted" in error_message.lower()
                    or response_data.get("status") == "RESOURCE_EXHAUSTED"
                    or response_data.get("code") == 429
                ):
                    status_tracker.time_of_last_rate_limit_error = time.time()
                    status_tracker.num_rate_limit_errors += 1
                    status_tracker.num_api_errors -= 1  # rate limit errors are counted separately

        except Exception as e:  # catching naked exceptions is bad practice, but in this case we'll log & save them
            logging.warning(f"Request {self.request_id} failed with Exception {e}")
            status_tracker.num_other_errors += 1
            error = e
        if error:
            self.result.append(error)
            if self.attempts_left:
                retry_queue.put_nowait(self)
            else:
                status_tracker.fatal_error = True
                status_tracker.fatal_error_message = (
                    f"Request {self.request_id} failed after all retry attempts. "
                    "Stopping job without saving a failed result item."
                )
                logging.error(f"{status_tracker.fatal_error_message} Errors: {self.result}")
                status_tracker.num_tasks_in_progress -= 1
                status_tracker.num_tasks_failed += 1
        else:
            data = (
                [self.request_json, response_data, self.metadata]
                if self.metadata
                else [self.request_json, response_data]
            )
            # print(data)
            result = {'id': self.request_id, 'ground_truth':self.request_truth, 'prompt': self.request_json, 'response': _json_safe(response_data)}
            async with write_lock:
                self.results_list.append(result)
                status_tracker.num_results_since_save += 1
                if save_every <= 1 or status_tracker.num_results_since_save >= save_every:
                    write_file(self.results_list, save_filepath)
                    status_tracker.num_results_since_save = 0
            status_tracker.num_tasks_in_progress -= 1
            status_tracker.num_tasks_succeeded += 1
            logging.debug(f"Request {self.request_id} saved to {save_filepath}")
            pbar.update(1)
        status_tracker.num_tasks_active -= 1

def load_results_file(results_json_file):
    for path in (results_json_file, results_json_file + '.backup'):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, FileNotFoundError):
            continue
    return []

def is_error_result(item):
    if not isinstance(item, dict):
        return False
    response = item.get('response')
    return isinstance(response, dict) and 'error' in response

def _json_safe(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_json_safe(v) for v in value]
        return str(value)

def write_file(results_list, results_json_file):
    backup_path = results_json_file + '.backup'
    tmp_path = results_json_file + '.tmp'
    for attempt in range(20):
        try:
            if os.path.exists(results_json_file) and os.path.getsize(results_json_file) > 0:
                shutil.copy(results_json_file, backup_path)
            break
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.1)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_json_safe(results_list), f)
    for attempt in range(20):
        try:
            os.replace(tmp_path, results_json_file)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.1)
