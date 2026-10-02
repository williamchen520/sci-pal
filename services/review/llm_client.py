"""
V25.4 - 统一 LLM 接入层（支持本地 Ollama 和云端 OpenAI 兼容 API）。

封装 LLM 调用，支持超时、重试、JSON 输出解析。
通过环境变量切换本地 Ollama 和云端 API（如阿里云通义千问）。

环境变量配置:
    # 本地 Ollama（默认）
    SCIPAL_LLM_PROVIDER=ollama
    SCIPAL_LLM_MODEL=qwen2.5:14b
    SCIPAL_LLM_LIGHT_MODEL=qwen2.5:7b

    # 阿里云通义千问（OpenAI 兼容模式）
    SCIPAL_LLM_PROVIDER=openai
    SCIPAL_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
    SCIPAL_LLM_API_KEY=sk-你的key
    SCIPAL_LLM_MODEL=qwen-plus
    SCIPAL_LLM_LIGHT_MODEL=qwen-turbo

用法:
    client = create_llm_client()  # 自动从环境变量读取配置
    text = client.chat("你是一个科研助手。", "STAT1的功能是什么？")
    data = client.chat_json("你是一个抽取器。", "抽取以下段落的关键信息...")
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore


class LLMError(Exception):
    """LLM 调用错误。"""
    pass


class LLMClient:
    """
    统一 LLM 客户端，支持 Ollama（本地）和 OpenAI 兼容 API（云端）。

    Args:
        provider: "ollama" 或 "openai"
        model: 模型名
        host: Ollama 服务地址 或 OpenAI API base URL
        api_key: API key（openai 模式需要）
        timeout: 单次请求超时（秒）
        max_retries: 最大重试次数
        retry_delay: 重试间隔（秒）
        temperature: 生成温度
    """

    def __init__(
        self,
        provider: str = "ollama",
        model: str = "qwen2.5:7b",
        host: str = "http://localhost:11434",
        api_key: Optional[str] = None,
        timeout: int = 600,
        max_retries: int = 2,
        retry_delay: float = 2.0,
        temperature: float = 0.3,
    ):
        self.provider = provider.lower()
        self.model = model
        self.host = host.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.temperature = temperature
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """检查 LLM 服务是否可用（带缓存）。"""
        if self._available is not None:
            return self._available
        if requests is None:
            self._available = False
            return False
        try:
            if self.provider == "openai":
                # OpenAI 模式：检查 API key 是否配置
                self._available = bool(self.api_key)
            else:
                # Ollama 模式：检查服务是否响应
                resp = requests.get(f"{self.host}/api/tags", timeout=5)
                self._available = resp.status_code == 200
        except Exception:
            self._available = False
        return self._available

    def list_models(self) -> list[str]:
        """列出可用模型。"""
        if not self.is_available():
            return []
        try:
            if self.provider == "openai":
                # OpenAI 模式不列出模型，返回当前配置的模型
                return [self.model]
            resp = requests.get(f"{self.host}/api/tags", timeout=10)
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def _get_headers(self) -> dict:
        """获取请求头。"""
        headers = {"Content-Type": "application/json"}
        if self.provider == "openai" and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get_url(self) -> str:
        """获取请求 URL。"""
        if self.provider == "openai":
            return f"{self.host}/chat/completions"
        return f"{self.host}/api/chat"

    def _build_payload(self, system_prompt: str, user_prompt: str, temperature: float) -> dict:
        """构建请求体。"""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }
        if self.provider == "openai":
            payload["temperature"] = temperature
            payload["max_tokens"] = 8192  # V31.4: 改大一点，避免输出被截断
        else:
            payload["options"] = {"temperature": temperature, "num_predict": 8192}
        return payload

    def _parse_response(self, data: dict) -> str:
        """解析响应，返回文本内容。"""
        if self.provider == "openai":
            # OpenAI 格式: choices[0].message.content
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            return ""
        else:
            # Ollama 格式: message.content
            return data.get("message", {}).get("content", "").strip()

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
    ) -> str:
        """
        发送聊天请求，返回纯文本。

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            temperature: 覆盖默认温度

        Returns:
            模型生成的文本

        Raises:
            LLMError: 服务不可用或重试耗尽
        """
        if not self.is_available():
            if self.provider == "openai":
                raise LLMError(
                    "云端 API 不可用：未配置 SCIPAL_LLM_API_KEY。\n"
                    "请设置环境变量: export SCIPAL_LLM_API_KEY=sk-你的key"
                )
            else:
                raise LLMError(
                    f"Ollama 服务不可用（{self.host}）。请先启动 Ollama 并拉取模型：\n"
                    f"  ollama serve\n  ollama pull {self.model}"
                )

        temp = temperature if temperature is not None else self.temperature
        payload = self._build_payload(system_prompt, user_prompt, temp)
        url = self._get_url()
        headers = self._get_headers()

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                return self._parse_response(data)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)

        raise LLMError(f"LLM 调用失败（重试 {self.max_retries} 次）: {last_error}")

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
    ) -> Any:
        """
        发送聊天请求，期望返回 JSON，自动解析。

        如果模型返回的不是纯 JSON（有多余文字），尝试提取第一个 ```json 块
        或第一个 {...} / [...] 结构。

        Returns:
            解析后的 Python 对象（dict / list）

        Raises:
            LLMError: 服务不可用、重试耗尽、或 JSON 解析失败
        """
        raw = self.chat(system_prompt, user_prompt, temperature)

        # 尝试直接解析
        try:
            result = json.loads(raw)
            # V25.4 兼容：如果返回的是 dict（如 {"evidence": [...]}），尝试提取其中的数组
            if isinstance(result, dict):
                for key in ("evidence", "evidences", "results", "data", "items", "list"):
                    if key in result and isinstance(result[key], list):
                        return result[key]
                # 如果 dict 里没有已知的数组键，返回第一个数组值
                for v in result.values():
                    if isinstance(v, list):
                        return v
            return result
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 块
        if "```json" in raw:
            start = raw.index("```json") + 7
            end = raw.find("```", start)
            if end > start:
                try:
                    return json.loads(raw[start:end].strip())
                except json.JSONDecodeError:
                    pass

        # 尝试提取第一个 {...} 结构
        brace_start = raw.find("{")
        brace_end = raw.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            try:
                return json.loads(raw[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                pass

        # 尝试提取第一个 [...] 结构
        bracket_start = raw.find("[")
        bracket_end = raw.rfind("]")
        if bracket_start >= 0 and bracket_end > bracket_start:
            try:
                return json.loads(raw[bracket_start:bracket_end + 1])
            except json.JSONDecodeError:
                pass

        # V25.4 容错：如果 JSON 被截断（输出不完整），尝试提取最后一个完整对象
        # 场景：模型输出太长被 max_tokens 截断，导致数组或对象没有闭合
        if raw.strip().startswith("["):
            # 尝试找到所有完整的 {...} 对象，组装成数组
            objects = []
            i = 0
            while i < len(raw):
                if raw[i] == '{':
                    # 找到匹配的 }
                    depth = 0
                    j = i
                    while j < len(raw):
                        if raw[j] == '{':
                            depth += 1
                        elif raw[j] == '}':
                            depth -= 1
                            if depth == 0:
                                break
                        j += 1
                    if j < len(raw) and depth == 0:
                        try:
                            obj = json.loads(raw[i:j + 1])
                            if isinstance(obj, dict):
                                objects.append(obj)
                        except json.JSONDecodeError:
                            pass
                        i = j + 1
                    else:
                        break
                else:
                    i += 1
            if objects:
                return objects

        raise LLMError(f"LLM 返回内容无法解析为 JSON。原始输出前500字:\n{raw[:500]}")


def create_llm_client(
    model: Optional[str] = None,
    light: bool = False,
    timeout: Optional[int] = None,
    max_retries: Optional[int] = None,
) -> LLMClient:
    """
    工厂函数：从环境变量读取配置，创建 LLMClient。

    Args:
        model: 覆盖环境变量中的模型名
        light: 是否使用轻量模型（SCIPAL_LLM_LIGHT_MODEL）
        timeout: 覆盖超时时间
        max_retries: 覆盖重试次数

    Returns:
        配置好的 LLMClient 实例
    """
    provider = os.environ.get("SCIPAL_LLM_PROVIDER", "ollama").lower()

    if model:
        model_name = model
    elif light:
        model_name = os.environ.get("SCIPAL_LLM_LIGHT_MODEL", "qwen2.5:7b")
    else:
        model_name = os.environ.get("SCIPAL_LLM_MODEL", "qwen2.5:14b")

    if provider == "openai":
        host = os.environ.get(
            "SCIPAL_LLM_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        api_key = os.environ.get("SCIPAL_LLM_API_KEY", "")
    else:
        host = os.environ.get("SCIPAL_LLM_HOST", "http://localhost:11434")
        api_key = None

    return LLMClient(
        provider=provider,
        model=model_name,
        host=host,
        api_key=api_key,
        timeout=timeout if timeout is not None else int(os.environ.get("SCIPAL_LLM_TIMEOUT", "120")),
        max_retries=max_retries if max_retries is not None else int(os.environ.get("SCIPAL_LLM_MAX_RETRIES", "3")),
        temperature=float(os.environ.get("SCIPAL_LLM_TEMPERATURE", "0.3")),
    )


# ──────────────────────────────────────────────
# 自测
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("🧠 LLM Client Test (V25.4 - 双 Provider)")
    print("=" * 60)

    provider = os.environ.get("SCIPAL_LLM_PROVIDER", "ollama")
    print(f"Provider: {provider}")

    client = create_llm_client()
    print(f"Model: {client.model}")
    print(f"可用: {client.is_available()}")

    if client.is_available():
        print("\n--- 文本生成测试 ---")
        try:
            result = client.chat(
                "你是一个简洁的科研助手。",
                "用一句话说明 STAT1 在干扰素信号通路中的作用。",
            )
            print(f"结果: {result}")
        except LLMError as e:
            print(f"❌ {e}")

        print("\n--- JSON 输出测试 ---")
        try:
            data = client.chat_json(
                "你是一个JSON输出器，只返回JSON，不要任何解释。",
                '返回一个包含 "name": "STAT1", "function": "干扰素信号转导" 的JSON对象。',
            )
            print(f"解析结果: {data}")
        except LLMError as e:
            print(f"❌ {e}")
    else:
        if provider == "openai":
            print("⚠️  云端 API 未配置 API key")
            print("    设置: export SCIPAL_LLM_API_KEY=sk-你的key")
        else:
            print("⚠️  Ollama 未启动，跳过实际调用测试。")
            print("    启动方式: ollama serve && ollama pull qwen2.5:14b")
