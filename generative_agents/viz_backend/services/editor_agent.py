"""Visualization-platform editor agent: chat → Skill-constrained tools → proposal.

Uses an OpenAI-compatible Chat Completions API (DeepSeek / MiniMax / DashScope / OpenAI …).
Never writes live active.json or live code; approve is a separate HTTP action.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import requests

from modules.health_mechanisms.ai_edit import AIEditAPI
from modules.health_mechanisms.model_version import (
    GA_ROOT,
    ModelVersionStore,
    assert_editable_relpath,
    resolve_editable_roots,
)
from modules.health_mechanisms.sandbox import validate_target
from modules.mechanism_config.schema import MechanismConfigError
from modules.mechanism_config.ui_tunable import (
    assert_ui_tunable_json_path,
    list_ui_param_specs,
    read_ui_param,
    snapshot_ui_values,
    write_ui_param,
)
from viz_backend.services.editor_llm import (
    assistant_message_from_choice,
    chat_completions,
    config_status,
    load_editor_llm_config,
    stream_chat_completions,
)
from viz_backend.services.editor_skills import build_system_prompt
from modules.mechanism_config.ui_param_guide import (
    UI_PARAM_GUIDE,
    enrich_param_specs,
    format_guide_for_system_prompt,
    get_ui_param_guide,
    list_ui_param_guides,
    summarize_probe_impact,
)
from viz_backend.services.probe_runner import probe_ui_param_delta

# Plumbing the visualization editor must not rewrite (self-escalation).
FROZEN_RELPATHS = {
    "viz_backend/services/editor_llm.py",
    "viz_backend/services/editor_agent.py",
    "viz_backend/services/editor_skills.py",
    "viz_backend/routes/editor.py",
    "viz_backend/routes/legacy_editor.py",
    "viz_backend/app.py",
    "modules/health_mechanisms/ai_edit.py",
    "modules/health_mechanisms/model_version.py",
    "modules/health_mechanisms/sandbox.py",
    "modules/health_mechanisms/editor_agent.py",
    "modules/health_mechanisms/editor_skills.py",
    "modules/health_mechanisms/editor_http.py",
}

TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "propose",
            "description": "开一份不改 live 的草稿 proposal。改参或改代码前必须先有 proposal。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "短名，如 lower_relapse"},
                    "note": {"type": "string", "description": "改动原因"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_ui_param",
            "description": "改 proposal 内一个界面可调参数（22 项 UI 键）。改前不确定含义/影响时先 explain_ui_param 或 preview_ui_param。禁止直接改非 UI 映射的 JSON。",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {"type": "string"},
                    "ui_key": {
                        "type": "string",
                        "description": "如 baseRelapseProb、penaltyStrength",
                    },
                    "value": {"type": "number"},
                },
                "required": ["proposal_id", "ui_key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_ui_params",
            "description": "列出 22 项界面参数：当前值、中文含义、JSON 映射摘要、调高/调低影响。",
            "parameters": {
                "type": "object",
                "properties": {"proposal_id": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_ui_param",
            "description": "查询单个 UI 键的完整说明：专家看到的标签、公式、底层 JSON 映射、与关联参数关系。改参前必查。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ui_key": {"type": "string", "description": "如 baseRelapseProb"},
                },
                "required": ["ui_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_ui_param",
            "description": "预览把某 UI 键调到新值后，机制探针 Tab KPI 如何变化（不写 proposal）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ui_key": {"type": "string"},
                    "value": {"type": "number"},
                    "proposal_id": {"type": "string", "description": "可选，基于草稿配置预览"},
                },
                "required": ["ui_key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_param_guides",
            "description": "返回全部 22 项 UI 参数语义与映射目录（静态参考）。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_config",
            "description": "改 proposal 内 JSON 叶子路径（仅限界面 22 项映射路径；优先 set_ui_param）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {"type": "string"},
                    "path": {"type": "string", "description": "如 simulation.relapse.base_prob"},
                    "value_json": {
                        "type": "string",
                        "description": "JSON 字面量，如 0.10 或 \"low\"",
                    },
                },
                "required": ["proposal_id", "path", "value_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_editable_files",
            "description": "列出白名单内可编辑的机制文件。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_editable_file",
            "description": "读取白名单文件。若给 proposal_id，优先读草稿里的副本。",
            "parameters": {
                "type": "object",
                "properties": {
                    "rel_path": {"type": "string"},
                    "proposal_id": {"type": "string"},
                    "max_chars": {"type": "integer", "default": 16000},
                },
                "required": ["rel_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_in_file",
            "description": "在 proposal 草稿中做精确字符串替换（优先于整文件覆盖）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {"type": "string"},
                    "rel_path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["proposal_id", "rel_path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_code",
            "description": "把白名单文件的完整新内容写入 proposal（非整仓重构）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {"type": "string"},
                    "rel_path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["proposal_id", "rel_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate",
            "description": "校验 proposal：schema + Python AST + 评分冒烟。",
            "parameters": {
                "type": "object",
                "properties": {"proposal_id": {"type": "string"}},
                "required": ["proposal_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "promote",
            "description": "把已校验 proposal 冻结为 model（仍不进 live）。下一步请用户在界面点批准落地。",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["proposal_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_proposals",
            "description": "列出当前草稿 proposal。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _assert_not_frozen(rel_path: str) -> str:
    rel = rel_path.replace("\\", "/").lstrip("/")
    assert_editable_relpath(rel)
    if rel in FROZEN_RELPATHS:
        raise MechanismConfigError(f"该文件为编辑器运行时冻结，不可改: {rel}")
    return rel


class EditorToolRuntime:
    def __init__(self):
        self.api = AIEditAPI()
        self.store = ModelVersionStore()

    def run(self, name: str, arguments: Dict[str, Any]) -> Any:
        fn = getattr(self, f"tool_{name}", None)
        if fn is None:
            return {"error": f"未知工具: {name}"}
        try:
            return fn(**arguments)
        except TypeError as e:
            return {"error": f"参数错误: {e}"}
        except MechanismConfigError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    def _proposal_file(self, proposal_id: str, rel_path: str) -> Path:
        return self.store.proposal_dir(proposal_id) / "code" / rel_path

    def tool_propose(self, name: str, note: str = "") -> Dict[str, str]:
        pid = self.api.propose(name=name, note=note, created_by="viz_editor")
        return {"proposal_id": pid, "live_unchanged": True}

    def tool_edit_config(self, proposal_id: str, path: str, value_json: str) -> Dict[str, Any]:
        assert_ui_tunable_json_path(path)
        value = json.loads(value_json)
        self.api.edit_config(proposal_id, dotted_path=path, value=value)
        return {"ok": True, "path": path, "value": value}

    def tool_set_ui_param(self, proposal_id: str, ui_key: str, value: float) -> Dict[str, Any]:
        cfg_path = self.store.proposal_dir(proposal_id) / "config.json"
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        before = read_ui_param(cfg, ui_key)
        updated = write_ui_param(cfg, ui_key, float(value))
        self.api.edit_config(proposal_id, config=updated)
        after = read_ui_param(updated, ui_key)
        preview = probe_ui_param_delta(updated, ui_key, after)
        return {
            "ok": True,
            "ui_key": ui_key,
            "label": get_ui_param_guide(ui_key).get("label"),
            "before": before,
            "after": after,
            "impact_summary": summarize_probe_impact(preview),
            "guide_hint": get_ui_param_guide(ui_key).get("meaning"),
        }

    def tool_list_ui_params(self, proposal_id: Optional[str] = None) -> Dict[str, Any]:
        if proposal_id:
            cfg_path = self.store.proposal_dir(proposal_id) / "config.json"
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        else:
            from modules.mechanism_config import load_mechanism_config

            cfg = load_mechanism_config()
        return {
            "params": enrich_param_specs(cfg),
            "section_formulas": {
                "health": "健康分演算",
                "relapse": "复发概率",
                "satisfaction": "满意度",
                "management": "管理机制",
            },
            "note": "专家 UI 显示 label；AI 必须用 ui_key 改参，勿直接改 subject/潮汐等内置 JSON。",
        }

    def tool_explain_ui_param(self, ui_key: str) -> Dict[str, Any]:
        try:
            return get_ui_param_guide(ui_key.strip())
        except KeyError:
            return {"error": f"未知 UI 键: {ui_key}；仅允许 22 项界面参数"}

    def tool_preview_ui_param(
        self,
        ui_key: str,
        value: float,
        proposal_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        ui_key = ui_key.strip()
        if proposal_id:
            cfg_path = self.store.proposal_dir(proposal_id) / "config.json"
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        else:
            from modules.mechanism_config import load_mechanism_config

            cfg = load_mechanism_config()
        probe = probe_ui_param_delta(cfg, ui_key, float(value))
        return {
            "preview": summarize_probe_impact(probe),
            "guide": get_ui_param_guide(ui_key),
            "proposed_value": float(value),
            "current_value": read_ui_param(cfg, ui_key),
        }

    def tool_list_param_guides(self) -> Dict[str, Any]:
        return {"guides": list_ui_param_guides(), "count": len(UI_PARAM_GUIDE)}

    def tool_list_editable_files(self) -> Dict[str, Any]:
        roots = resolve_editable_roots()
        files: List[str] = []
        for root in roots:
            base = GA_ROOT / root
            if not base.exists():
                continue
            if base.is_file():
                rel = root.replace("\\", "/").rstrip("/")
                if rel not in FROZEN_RELPATHS:
                    files.append(rel)
                continue
            for p in base.rglob("*"):
                if p.is_file() and p.suffix in {".py", ".txt", ".json", ".md"}:
                    rel = str(p.relative_to(GA_ROOT)).replace("\\", "/")
                    if rel not in FROZEN_RELPATHS:
                        files.append(rel)
        return {"roots": roots, "files": sorted(files)[:400]}

    def tool_read_editable_file(
        self,
        rel_path: str,
        proposal_id: Optional[str] = None,
        max_chars: int = 16000,
    ) -> Dict[str, Any]:
        rel = _assert_not_frozen(rel_path)
        path = None
        source = "live"
        if proposal_id:
            cand = self._proposal_file(proposal_id, rel)
            if cand.is_file():
                path = cand
                source = "proposal"
        if path is None:
            path = GA_ROOT / rel
            source = "live"
        if not path.is_file():
            return {"error": f"文件不存在: {rel}"}
        text = path.read_text(encoding="utf-8")
        return {
            "rel_path": rel,
            "source": source,
            "content": text[:max_chars],
            "truncated": len(text) > max_chars,
        }

    def tool_replace_in_file(
        self,
        proposal_id: str,
        rel_path: str,
        old_string: str,
        new_string: str,
    ) -> Dict[str, Any]:
        rel = _assert_not_frozen(rel_path)
        path = self._proposal_file(proposal_id, rel)
        if path.is_file():
            text = path.read_text(encoding="utf-8")
        else:
            live = GA_ROOT / rel
            if not live.is_file():
                return {"error": f"文件不存在: {rel}"}
            text = live.read_text(encoding="utf-8")
        count = text.count(old_string)
        if count == 0:
            return {"error": "old_string 未找到，请先 read_editable_file"}
        if count > 1:
            return {"error": f"old_string 出现 {count} 次，请扩大上下文使其唯一"}
        self.api.edit_code(proposal_id, rel, text.replace(old_string, new_string, 1))
        return {"ok": True, "rel_path": rel, "replaced": 1}

    def tool_edit_code(self, proposal_id: str, rel_path: str, content: str) -> Dict[str, Any]:
        rel = _assert_not_frozen(rel_path)
        self.api.edit_code(proposal_id, rel, content)
        return {"ok": True, "rel_path": rel, "chars": len(content)}

    def tool_validate(self, proposal_id: str) -> Dict[str, Any]:
        return validate_target(self.store, proposal_id, is_proposal=True)

    def tool_promote(self, proposal_id: str, name: Optional[str] = None) -> Dict[str, str]:
        mid = self.api.promote(proposal_id, name=name)
        return {
            "model_id": mid,
            "live_unchanged": True,
            "next": "请用户在界面点击「批准落地」，模型不可自行 approve",
        }

    def tool_list_proposals(self) -> Dict[str, Any]:
        return {"proposals": self.store.list_proposals()}


class EditorSessionStore:
    def __init__(self):
        self._sessions: Dict[str, List[Dict[str, Any]]] = {}

    def get(self, session_id: str) -> List[Dict[str, Any]]:
        if session_id not in self._sessions:
            self._sessions[session_id] = [
                {"role": "system", "content": build_system_prompt()}
            ]
        return self._sessions[session_id]


_SESSIONS = EditorSessionStore()


def _parse_tool_call(call: Dict[str, Any]) -> tuple[str, Dict[str, Any], Any]:
    fn = call.get("function") or {}
    name = fn.get("name") or ""
    raw_args = fn.get("arguments") or "{}"
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
    except json.JSONDecodeError:
        return name, {}, {"error": f"工具参数不是合法 JSON: {str(raw_args)[:200]}"}
    if not isinstance(args, dict):
        return name, {}, {"error": "工具参数必须是 JSON 对象"}
    return name, args, None


def _llm_assistant_message(cfg: Dict[str, Any], messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    data = chat_completions(cfg, messages, TOOLS)
    choice = (data.get("choices") or [{}])[0]
    return assistant_message_from_choice(choice)


def _stream_llm_assistant_message(
    cfg: Dict[str, Any],
    messages: List[Dict[str, Any]],
) -> Iterator[Dict[str, Any]]:
    """Yield delta/reasoning events, then message_complete with full assistant msg."""
    assistant_msg: Optional[Dict[str, Any]] = None
    try:
        for event in stream_chat_completions(cfg, messages, TOOLS):
            if event["type"] == "message_complete":
                assistant_msg = event["message"]
            else:
                yield event
    except MechanismConfigError:
        assistant_msg = _llm_assistant_message(cfg, messages)
        content = assistant_msg.get("content") or ""
        if content:
            yield {"type": "content_delta", "content": content}
    if assistant_msg is None:
        raise MechanismConfigError("流式响应未返回完整 assistant 消息")
    yield {"type": "message_complete", "message": assistant_msg}


def chat_turn_events(
    user_text: str,
    session_id: Optional[str] = None,
) -> Iterator[Dict[str, Any]]:
    """SSE-friendly event stream for one user turn (content deltas + tool traces)."""
    sid = session_id or uuid.uuid4().hex[:12]
    cfg = load_editor_llm_config()
    messages = _SESSIONS.get(sid)
    messages.append({"role": "user", "content": user_text})
    runtime = EditorToolRuntime()
    traces: List[Dict[str, Any]] = []
    final_text = ""

    yield {"type": "session", "session_id": sid, "model": cfg.get("model")}

    try:
        for _ in range(cfg["max_tool_rounds"]):
            assistant_msg: Optional[Dict[str, Any]] = None
            for event in _stream_llm_assistant_message(cfg, messages):
                if event["type"] == "message_complete":
                    assistant_msg = event["message"]
                elif event["type"] == "content_delta":
                    yield {"type": "delta", "content": event["content"]}
                elif event["type"] == "reasoning_delta":
                    yield {"type": "reasoning", "content": event["content"]}

            if assistant_msg is None:
                raise MechanismConfigError("未收到模型回复")

            messages.append(assistant_msg)
            tool_calls = assistant_msg.get("tool_calls") or []
            if not tool_calls:
                final_text = assistant_msg.get("content") or ""
                break

            yield {"type": "tools_start", "tools": [c.get("function", {}).get("name", "") for c in tool_calls]}
            for call in tool_calls:
                name, args, parse_err = _parse_tool_call(call)
                if parse_err is not None:
                    result = parse_err
                    args = {}
                    yield {"type": "tool_start", "tool": name or "?", "args": {}}
                    yield {"type": "tool_end", "tool": name or "?", "result": result}
                else:
                    yield {"type": "tool_start", "tool": name, "args": _safe_args(name, args)}
                    result = runtime.run(name, args)
                    yield {"type": "tool_end", "tool": name, "result": result}
                traces.append({"tool": name, "args": _safe_args(name, args), "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", name),
                        "content": json.dumps(result, ensure_ascii=False, default=str)[:20000],
                    }
                )
            yield {"type": "tools_done"}
        else:
            final_text = "达到最大工具轮次，请把需求拆小再试。"

        yield {
            "type": "done",
            "session_id": sid,
            "reply": final_text,
            "traces": traces,
            "model": cfg.get("model"),
            "error": False,
        }
    except MechanismConfigError as e:
        if messages and messages[-1].get("role") == "user":
            messages.pop()
        yield {
            "type": "done",
            "session_id": sid,
            "reply": str(e),
            "traces": traces,
            "model": cfg.get("model"),
            "error": True,
        }
    except requests.RequestException as e:
        if messages and messages[-1].get("role") == "user":
            messages.pop()
        yield {
            "type": "done",
            "session_id": sid,
            "reply": f"编辑模型网络错误: {e}",
            "traces": traces,
            "model": cfg.get("model"),
            "error": True,
        }


def chat_turn(user_text: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Non-streaming fallback — aggregates chat_turn_events into one JSON response."""
    result: Dict[str, Any] = {}
    for event in chat_turn_events(user_text, session_id=session_id):
        if event.get("type") == "done":
            result = event
    return result or {
        "session_id": session_id or "",
        "reply": "无响应",
        "traces": [],
        "error": True,
    }


def _safe_args(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(args or {})
    if name == "edit_code" and "content" in out:
        out["content"] = f"<{len(str(out['content']))} chars>"
    if name == "replace_in_file":
        for k in ("old_string", "new_string"):
            val = str(out.get(k, ""))
            if len(val) > 400:
                out[k] = val[:400] + "…"
    return out


def approve_model(model_id: str, config_only: bool = False) -> Dict[str, Any]:
    api = AIEditAPI()
    applied = api.approve(model_id, apply_code=not config_only, autosave=True)
    return {"ok": True, "applied": applied, "model_id": model_id, "config_only": config_only}


def list_editor_state() -> Dict[str, Any]:
    store = ModelVersionStore()
    return {
        "proposals": store.list_proposals(),
        "models": store.list_models(),
        "active_model_id": store.get_active_model_id(),
        "llm": config_status(),
    }
