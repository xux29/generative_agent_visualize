"""Editor LLM providers — OpenAI-compatible APIs (DeepSeek, MiniMax, …)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from modules.mechanism_config.loader import MECHANISM_DATA_DIR
from modules.mechanism_config.schema import MechanismConfigError

CONFIG_CANDIDATES = [
    MECHANISM_DATA_DIR / "editor_llm.json",
    MECHANISM_DATA_DIR / "editor_llm.example.json",
]

PROVIDER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "openai_compatible": {
        "model": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com",
        "temperature": 0.2,
        "max_tokens": 8192,
        "max_tool_rounds": 8,
        "thinking": False,
    },
    "minimax": {
        "model": "MiniMax-M2.7",
        "base_url": "https://api.minimaxi.com/v1",
        "temperature": 0.2,
        "max_completion_tokens": 8192,
        "max_tool_rounds": 8,
        "thinking": "disabled",
        "reasoning_split": True,
    },
}


def load_editor_llm_config() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    loaded_from_secret = False
    for path in CONFIG_CANDIDATES:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if path.name == "editor_llm.json":
                loaded_from_secret = True
                break

    env_provider = os.environ.get("EDITOR_LLM_PROVIDER")
    if env_provider:
        provider = env_provider.strip().lower()
    else:
        provider = (cfg.get("provider") or "openai_compatible").strip().lower()

    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["openai_compatible"])
    merged = dict(defaults)
    merged.update(cfg)
    merged["provider"] = provider

    # 用环境变量切换 provider 时，不用另一份 example 里的 model/base_url
    if env_provider and cfg.get("provider") != provider:
        merged["model"] = defaults["model"]
        merged["base_url"] = defaults["base_url"].rstrip("/")
        if provider == "minimax":
            merged["max_completion_tokens"] = defaults.get("max_completion_tokens", 8192)
            merged["reasoning_split"] = defaults.get("reasoning_split", True)
            merged["thinking"] = defaults.get("thinking", "disabled")
        else:
            merged["max_tokens"] = defaults.get("max_tokens", 8192)
            merged["thinking"] = defaults.get("thinking", False)

    merged["model"] = os.environ.get("EDITOR_LLM_MODEL", merged.get("model", defaults["model"]))
    merged["base_url"] = os.environ.get(
        "EDITOR_LLM_BASE_URL", merged.get("base_url", defaults["base_url"])
    ).rstrip("/")
    merged["api_key"] = os.environ.get("EDITOR_LLM_API_KEY", merged.get("api_key") or "")
    merged["temperature"] = float(merged.get("temperature", defaults.get("temperature", 0.2)))
    merged["max_tool_rounds"] = int(merged.get("max_tool_rounds", defaults.get("max_tool_rounds", 8)))
    if provider == "minimax":
        merged["max_completion_tokens"] = int(
            merged.get(
                "max_completion_tokens",
                merged.get("max_tokens", defaults.get("max_completion_tokens", 8192)),
            )
        )
        merged["reasoning_split"] = bool(merged.get("reasoning_split", True))
    else:
        merged["max_tokens"] = int(merged.get("max_tokens", defaults.get("max_tokens", 8192)))
    merged["thinking"] = merged.get("thinking", defaults.get("thinking", False))
    merged["_loaded_from_secret"] = loaded_from_secret
    return merged


def config_status() -> Dict[str, Any]:
    cfg = load_editor_llm_config()
    key = cfg.get("api_key") or ""
    return {
        "configured": bool(key),
        "provider": cfg.get("provider"),
        "model": cfg.get("model"),
        "base_url": cfg.get("base_url"),
        "has_local_file": (MECHANISM_DATA_DIR / "editor_llm.json").is_file(),
    }


def _chat_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _apply_thinking(payload: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    provider = (cfg.get("provider") or "").lower()
    thinking = cfg.get("thinking", False)
    if provider == "minimax":
        if thinking is True or thinking in {"enabled", "adaptive"}:
            payload["thinking"] = {"type": "adaptive"}
        elif thinking is False or thinking == "disabled":
            payload["thinking"] = {"type": "disabled"}
        if cfg.get("reasoning_split", True):
            payload["reasoning_split"] = True
        return
    if thinking is True or thinking == "enabled":
        payload["thinking"] = {"type": "enabled"}
    elif thinking is False or thinking == "disabled":
        payload["thinking"] = {"type": "disabled"}


def build_chat_payload(cfg: Dict[str, Any], messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    provider = (cfg.get("provider") or "").lower()
    payload: Dict[str, Any] = {
        "model": cfg["model"],
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": cfg["temperature"],
    }
    if provider == "minimax":
        payload["max_completion_tokens"] = int(cfg.get("max_completion_tokens", 8192))
    else:
        payload["max_tokens"] = int(cfg.get("max_tokens", 8192))
    _apply_thinking(payload, cfg)
    return payload


def assistant_message_from_choice(choice: Dict[str, Any]) -> Dict[str, Any]:
    """Preserve provider-specific fields (MiniMax reasoning_details, tool_calls, …)."""
    msg = dict(choice.get("message") or {})
    msg.setdefault("role", "assistant")
    if msg.get("content") is None and not msg.get("tool_calls"):
        msg["content"] = ""
    return msg


def chat_completions(cfg: Dict[str, Any], messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not cfg.get("api_key"):
        raise MechanismConfigError(
            "未配置编辑模型 API Key。请复制 data/mechanism/editor_llm.minimax.example.json "
            "（或 editor_llm.example.json）为 editor_llm.json 并填写 api_key，"
            "或设置环境变量 EDITOR_LLM_API_KEY。"
        )
    url = _chat_url(cfg["base_url"])
    payload = build_chat_payload(cfg, messages, tools)
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=180)
    if resp.status_code >= 400:
        retry_payload = dict(payload)
        changed = False
        provider = (cfg.get("provider") or "").lower()
        if resp.status_code in {400, 422}:
            if "thinking" in retry_payload:
                retry_payload.pop("thinking", None)
                changed = True
            if provider == "minimax" and "reasoning_split" in retry_payload:
                retry_payload.pop("reasoning_split", None)
                changed = True
            if provider != "minimax" and "max_tokens" in retry_payload:
                retry_payload["max_completion_tokens"] = retry_payload.pop("max_tokens")
                changed = True
        if changed:
            resp = requests.post(url, headers=headers, json=retry_payload, timeout=180)
        if resp.status_code >= 400:
            raise MechanismConfigError(f"LLM HTTP {resp.status_code}: {resp.text[:800]}")
    return resp.json()
