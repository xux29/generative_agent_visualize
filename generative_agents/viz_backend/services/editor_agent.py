"""Visualization-platform editor agent: chat → Skill-constrained tools → proposal.

Uses an OpenAI-compatible Chat Completions API (DeepSeek / MiniMax / DashScope / OpenAI …).
Never writes live active.json or live code; approve is a separate HTTP action.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

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
)
from viz_backend.services.editor_skills import build_system_prompt

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
            "description": "改 proposal 内一个界面可调参数（22 项白名单，见 docs/mechanism/界面可调参数.md）。改参优先用此工具。",
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
            "description": "列出界面可调 22 项参数及当前 proposal/live 取值。",
            "parameters": {
                "type": "object",
                "properties": {"proposal_id": {"type": "string"}},
            },
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
        return {"ok": True, "ui_key": ui_key, "before": before, "after": after}

    def tool_list_ui_params(self, proposal_id: Optional[str] = None) -> Dict[str, Any]:
        if proposal_id:
            cfg_path = self.store.proposal_dir(proposal_id) / "config.json"
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        else:
            from modules.mechanism_config import load_mechanism_config

            cfg = load_mechanism_config()
        return {"params": list_ui_param_specs(), "values": snapshot_ui_values(cfg)}

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


def chat_turn(user_text: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Run one user turn with tool loop. Returns assistant text + tool traces."""
    sid = session_id or uuid.uuid4().hex[:12]
    cfg = load_editor_llm_config()
    messages = _SESSIONS.get(sid)
    messages.append({"role": "user", "content": user_text})
    runtime = EditorToolRuntime()
    traces: List[Dict[str, Any]] = []
    final_text = ""

    try:
        for _ in range(cfg["max_tool_rounds"]):
            data = chat_completions(cfg, messages, TOOLS)
            choice = (data.get("choices") or [{}])[0]
            assistant_msg = assistant_message_from_choice(choice)
            messages.append(assistant_msg)
            tool_calls = assistant_msg.get("tool_calls") or []
            if not tool_calls:
                final_text = assistant_msg.get("content") or ""
                break
            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name") or ""
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except json.JSONDecodeError:
                    args = {}
                    result: Any = {"error": f"工具参数不是合法 JSON: {str(raw_args)[:200]}"}
                else:
                    if not isinstance(args, dict):
                        args = {}
                        result = {"error": "工具参数必须是 JSON 对象"}
                    else:
                        result = runtime.run(name, args)
                traces.append({"tool": name, "args": _safe_args(name, args), "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", name),
                        "content": json.dumps(result, ensure_ascii=False, default=str)[:20000],
                    }
                )
        else:
            final_text = "达到最大工具轮次，请把需求拆小再试。"
    except MechanismConfigError as e:
        if messages and messages[-1].get("role") == "user":
            messages.pop()
        return {
            "session_id": sid,
            "reply": str(e),
            "traces": traces,
            "model": cfg.get("model"),
            "error": True,
        }

    return {
        "session_id": sid,
        "reply": final_text,
        "traces": traces,
        "model": cfg.get("model"),
        "error": False,
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
