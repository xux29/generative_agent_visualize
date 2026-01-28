"""generative_agents.model.llm_model"""

import time
import re
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from magentic import prompt


class LLMModel:
    # API key 失败后的冷却时间（秒）
    KEY_COOLDOWN_SECONDS = 300  # 5分钟后重试失效的key
    # 连续失败多少次后标记为失效
    KEY_FAILURE_THRESHOLD = 3

    def __init__(self, config):
        # 支持多个 API key 轮询（负载均衡）
        api_keys = config.get("api_keys", [])
        if api_keys:
            self._api_keys = api_keys
        else:
            # 兼容单个 api_key 的旧格式
            self._api_keys = [config["api_key"]]

        self._api_key_index = 0
        self._api_key_lock = threading.Lock()
        self._api_key = self._api_keys[0]  # 当前使用的 key

        self._base_url = config["base_url"]
        self._model = config["model"]
        self._summary = {"total": [0, 0, 0]}

        # API key 健康状态追踪
        self._key_health = {}  # {key_index: {"failures": 0, "last_failure": timestamp, "disabled_until": timestamp}}
        for i in range(len(self._api_keys)):
            self._key_health[i] = {
                "failures": 0,
                "last_failure": 0,
                "disabled_until": 0,
                "total_requests": 0,
                "total_failures": 0,
            }

        self._handle = self.setup(config)
        self._enabled = True

    def _get_next_api_key(self):
        """轮询获取下一个 API key（跳过失效的key）"""
        with self._api_key_lock:
            return self._get_healthy_key_index()

    def _get_healthy_key_index(self):
        """获取一个健康的 API key 索引（内部方法，需在锁内调用）"""
        current_time = time.time()
        start_index = self._api_key_index
        attempts = 0

        while attempts < len(self._api_keys):
            idx = (start_index + attempts) % len(self._api_keys)
            health = self._key_health[idx]

            # 检查是否在冷却期
            if health["disabled_until"] > current_time:
                attempts += 1
                continue

            # 如果之前被禁用但冷却期已过，重置状态
            if health["disabled_until"] > 0 and health["disabled_until"] <= current_time:
                health["failures"] = 0
                health["disabled_until"] = 0
                print(f"[API Key] Key #{idx} 冷却期结束，重新启用")

            # 更新索引到下一个
            self._api_key_index = (idx + 1) % len(self._api_keys)
            return idx

        # 所有 key 都在冷却期，找最早解除的
        earliest_idx = 0
        earliest_time = float('inf')
        for idx, health in self._key_health.items():
            if health["disabled_until"] < earliest_time:
                earliest_time = health["disabled_until"]
                earliest_idx = idx

        # 等待最早解除的 key
        wait_time = earliest_time - current_time
        if wait_time > 0:
            print(f"[API Key] 所有 key 都在冷却期，等待 {wait_time:.1f} 秒...")
            # 不在锁内等待，返回最早的key（调用方会处理）

        self._api_key_index = (earliest_idx + 1) % len(self._api_keys)
        return earliest_idx

    def _mark_key_success(self, key_index):
        """标记 API key 调用成功"""
        with self._api_key_lock:
            health = self._key_health[key_index]
            health["failures"] = 0  # 重置连续失败计数
            health["total_requests"] += 1

    def _mark_key_failure(self, key_index, error_msg=""):
        """标记 API key 调用失败"""
        with self._api_key_lock:
            health = self._key_health[key_index]
            health["failures"] += 1
            health["total_failures"] += 1
            health["total_requests"] += 1
            health["last_failure"] = time.time()

            # 检查是否需要禁用
            if health["failures"] >= self.KEY_FAILURE_THRESHOLD:
                health["disabled_until"] = time.time() + self.KEY_COOLDOWN_SECONDS
                key_preview = self._api_keys[key_index][:8] + "..."
                print(f"[API Key] Key #{key_index} ({key_preview}) 连续失败 {health['failures']} 次，"
                      f"冷却 {self.KEY_COOLDOWN_SECONDS} 秒。错误: {error_msg[:100]}")

    def _is_auth_error(self, error):
        """判断是否是认证/授权错误（API key 失效）"""
        error_str = str(error).lower()
        auth_keywords = [
            "401", "403", "unauthorized", "forbidden",
            "invalid api key", "invalid_api_key",
            "authentication", "api key not found",
            "quota exceeded", "rate limit", "insufficient_quota"
        ]
        return any(keyword in error_str for keyword in auth_keywords)

    def get_key_health_summary(self):
        """获取所有 API key 的健康状态摘要"""
        with self._api_key_lock:
            summary = []
            current_time = time.time()
            for idx, health in self._key_health.items():
                key_preview = self._api_keys[idx][:8] + "..."
                status = "healthy"
                if health["disabled_until"] > current_time:
                    remaining = int(health["disabled_until"] - current_time)
                    status = f"disabled ({remaining}s remaining)"
                elif health["failures"] > 0:
                    status = f"degraded ({health['failures']} failures)"

                summary.append({
                    "index": idx,
                    "key_preview": key_preview,
                    "status": status,
                    "total_requests": health["total_requests"],
                    "total_failures": health["total_failures"],
                })
            return summary

    def setup(self, config):
        raise NotImplementedError(
            "setup is not support for " + str(self.__class__)
        )

    def completion(
        self,
        prompt,
        retry=10,
        callback=None,
        failsafe=None,
        return_type=None,
        caller="llm_normal",
        **kwargs
    ):
        response = None
        self._summary.setdefault(caller, [0, 0, 0])
        last_key_index = None

        for attempt in range(retry):
            try:
                # 获取健康的 key 索引（供子类使用）
                with self._api_key_lock:
                    last_key_index = self._get_healthy_key_index()

                output = self._completion_with_key(prompt, return_type, last_key_index, **kwargs)
                self._summary["total"][0] += 1
                self._summary[caller][0] += 1

                # 标记成功
                if last_key_index is not None:
                    self._mark_key_success(last_key_index)

                if callback:
                    response = callback(output)
                else:
                    response = output
            except Exception as e:
                error_msg = str(e)
                print(f"LLMModel.completion() caused an error (attempt {attempt+1}/{retry}): {e}")

                # 标记失败
                if last_key_index is not None:
                    is_auth_error = self._is_auth_error(e)
                    if is_auth_error:
                        # 认证错误立即标记为失败，加速切换
                        self._key_health[last_key_index]["failures"] = self.KEY_FAILURE_THRESHOLD
                    self._mark_key_failure(last_key_index, error_msg)

                time.sleep(2 if attempt < 3 else 5)  # 前几次快速重试
                response = None
                continue

            if response is not None:
                break

        pos = 2 if response is None else 1
        self._summary["total"][pos] += 1
        self._summary[caller][pos] += 1
        return response or failsafe

    def _completion_with_key(self, prompt, return_type, key_index, **kwargs):
        """使用指定 key 索引进行调用（子类可覆盖）"""
        return self._completion(prompt, return_type, **kwargs)

    def _completion(self, prompt, return_type, **kwargs):
        raise NotImplementedError(
            "_completion is not support for " + str(self.__class__)
        )

    def is_available(self):
        return self._enabled  # and self._summary["total"][2] <= 10

    def get_summary(self):
        des = {}
        for k, v in self._summary.items():
            des[k] = "S:{},F:{}/R:{}".format(v[1], v[2], v[0])
        return {"model": self._model, "summary": des}

    def disable(self):
        self._enabled = False

    def completion_parallel(
        self,
        prompts,
        retry=10,
        callbacks=None,
        failsafes=None,
        return_types=None,
        caller="llm_parallel",
        max_workers=None,
        **kwargs
    ):
        """
        并行执行多个 LLM 调用

        Args:
            prompts: 提示列表
            retry: 重试次数
            callbacks: 回调函数列表（与 prompts 对应）
            failsafes: 失败安全值列表（与 prompts 对应）
            return_types: 返回类型列表（与 prompts 对应）
            caller: 调用者标识
            max_workers: 最大并行数（默认为 API key 数量）
            **kwargs: 其他参数

        Returns:
            结果列表，顺序与 prompts 对应
        """
        if max_workers is None:
            max_workers = len(self._api_keys)

        # 规范化参数列表
        n = len(prompts)
        if callbacks is None:
            callbacks = [None] * n
        if failsafes is None:
            failsafes = [None] * n
        if return_types is None:
            return_types = [None] * n

        results = [None] * n

        def execute_single(index, prompt, callback, failsafe, return_type):
            """执行单个 LLM 调用"""
            return index, self.completion(
                prompt=prompt,
                retry=retry,
                callback=callback,
                failsafe=failsafe,
                return_type=return_type,
                caller=caller,
                **kwargs
            )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i in range(n):
                future = executor.submit(
                    execute_single,
                    i,
                    prompts[i],
                    callbacks[i],
                    failsafes[i],
                    return_types[i]
                )
                futures.append(future)

            for future in as_completed(futures):
                try:
                    index, result = future.result()
                    results[index] = result
                except Exception as e:
                    print(f"Parallel completion error: {e}")

        return results

    def get_num_workers(self):
        """获取可用的并行工作数（健康的 API key 数量）"""
        with self._api_key_lock:
            current_time = time.time()
            healthy_count = sum(
                1 for health in self._key_health.values()
                if health["disabled_until"] <= current_time
            )
            return max(1, healthy_count)  # 至少返回1

    def get_total_keys(self):
        """获取总 API key 数量"""
        return len(self._api_keys)

    def print_key_health(self):
        """打印 API key 健康状态"""
        summary = self.get_key_health_summary()
        print("\n=== API Key 健康状态 ===")
        for item in summary:
            success_rate = 0
            if item["total_requests"] > 0:
                success_rate = (1 - item["total_failures"] / item["total_requests"]) * 100
            print(f"  Key #{item['index']} ({item['key_preview']}): {item['status']} | "
                  f"请求: {item['total_requests']}, 失败: {item['total_failures']}, "
                  f"成功率: {success_rate:.1f}%")
        print("========================\n")


class OpenAILLMModel(LLMModel):
    def setup(self, config):
        from openai import OpenAI
        # 存储所有 client，每个 API key 一个
        self._clients = []
        for key in self._api_keys:
            self._clients.append(OpenAI(api_key=key, base_url=self._base_url))
        return self._clients[0]  # 默认返回第一个

    def _get_next_client(self):
        """轮询获取下一个 OpenAI client（跳过失效的）"""
        with self._api_key_lock:
            idx = self._get_healthy_key_index()
            return self._clients[idx], idx

    def _get_client_by_index(self, key_index):
        """根据索引获取 client"""
        return self._clients[key_index]

    def _completion_with_key(self, prompt, return_type, key_index, **kwargs):
        """使用指定 key 索引进行调用"""
        return self._completion_impl(prompt, return_type, key_index, **kwargs)

    def _completion(self, prompt, return_type, temperature=0.5):
        """兼容旧接口，使用轮询方式"""
        client, idx = self._get_next_client()
        return self._completion_impl(prompt, return_type, idx, temperature=temperature)

    def _completion_impl(self, prompt, return_type, key_index, temperature=0.5):
        """实际的 completion 实现"""
        import json

        client = self._clients[key_index]

        response = client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )

        if response and len(response.choices) > 0:
            ret = response.choices[0].message.content
            # 从输出结果中过滤掉<think>标签内的文字，以免影响后续逻辑
            ret = re.sub(r"<think>.*</think>", "", ret, flags=re.DOTALL)

            # Parse and validate the response using the Pydantic model
            if return_type is not None:
                try:
                    # Try to parse as JSON and validate with Pydantic
                    parsed = json.loads(ret)
                    validated = return_type.model_validate(parsed)
                    return validated.res
                except json.JSONDecodeError:
                    # If JSON parsing fails, try to extract JSON from the text
                    json_match = re.search(r'\{.*\}', ret, re.DOTALL)
                    if json_match:
                        try:
                            parsed = json.loads(json_match.group())
                            validated = return_type.model_validate(parsed)
                            return validated.res
                        except (json.JSONDecodeError, Exception):
                            pass
                    # If all parsing fails, return the raw text
                    return ret
                except Exception as e:
                    print(f"OpenAILLMModel: Failed to validate response: {e}")
                    return ret
            return ret
        return ""


class OllamaLLMModel(LLMModel):
    def setup(self, config):
        return None

    def ollama_chat(self, messages, temperature, response_format=None):
        headers = {
            "Content-Type": "application/json"
        }
        params = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if response_format:
            params["response_format"] = response_format

        response = requests.post(
            url=f"{self._base_url}/chat/completions",
            headers=headers,
            json=params,
            stream=False
        )
        return response.json()

    def _completion(self, prompt, return_type, temperature=0.5):
        import json
        
        # Generate JSON schema from the Pydantic model for structured output
        response_format = None
        if return_type is not None:
            try:
                schema = return_type.model_json_schema()
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": return_type.__name__,
                        "strict": True,
                        "schema": schema
                    }
                }
            except Exception:
                pass
        
        messages = [{"role": "user", "content": prompt}]
        response = self.ollama_chat(messages=messages, temperature=temperature, response_format=response_format)
        
        if response and len(response.get("choices", [])) > 0:
            ret = response["choices"][0]["message"]["content"]
            # 从输出结果中过滤掉<think>标签内的文字，以免影响后续逻辑
            ret = re.sub(r"<think>.*</think>", "", ret, flags=re.DOTALL)
            
            # Parse and validate the response using the Pydantic model
            if return_type is not None:
                try:
                    # Try to parse as JSON and validate with Pydantic
                    parsed = json.loads(ret)
                    validated = return_type.model_validate(parsed)
                    return validated.res
                except json.JSONDecodeError:
                    # If JSON parsing fails, try to extract JSON from the text
                    json_match = re.search(r'\{.*\}', ret, re.DOTALL)
                    if json_match:
                        try:
                            parsed = json.loads(json_match.group())
                            validated = return_type.model_validate(parsed)
                            return validated.res
                        except (json.JSONDecodeError, Exception):
                            pass
                    # If all parsing fails, return the raw text
                    return ret
                except Exception as e:
                    print(f"OllamaLLMModel: Failed to validate response: {e}")
                    return ret
            return ret
        return ""


def create_llm_model(llm_config):
    """Create llm model"""

    if llm_config["provider"] == "ollama":
        return OllamaLLMModel(llm_config)

    elif llm_config["provider"] == "openai":
        return OpenAILLMModel(llm_config)
    else:
        raise NotImplementedError(
            "llm provider {} is not supported".format(llm_config["provider"])
        )
    return None
