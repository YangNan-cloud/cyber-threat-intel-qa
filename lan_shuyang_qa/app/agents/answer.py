"""Evidence-bound answer generation through an optional DeepSeek endpoint."""
from __future__ import annotations

import os
import httpx

from app.config import load_dotenv
from app.schemas import Attribution, Evidence

load_dotenv()


class AnswerAgent:
    async def generate(self, question: str, evidence: list[Evidence], attribution: Attribution, refusal: bool) -> str:
        if refusal:
            return "当前证据不足，系统拒绝给出确定性威胁结论。请扩大检索范围或提供可验证的 IOC、CVE 编号、报告来源与时间范围。"
        context = "\n\n".join(f"[{i + 1}] {item.text}" for i, item in enumerate(evidence))
        key = os.getenv("DEEPSEEK_API_KEY", "")
        if key:
            prompt = (
                "你是网络威胁情报分析师。只能根据给定证据回答，每个事实后以[编号]引用。"
                "给出简洁结论、证据和可执行的取证/修复建议；信息不足时明确不确定。"
                f"\n问题：{question}\n归因状态：{attribution.verdict}\n证据：\n{context}"
            )
            try:
                async with httpx.AsyncClient(timeout=25) as client:
                    response = await client.post(
                        f"{os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/')}/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json={"model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"), "temperature": 0.1,
                              "messages": [{"role": "user", "content": prompt}]},
                    )
                    response.raise_for_status()
                    return response.json()["choices"][0]["message"]["content"]
            except (httpx.HTTPError, KeyError, IndexError, ValueError):
                pass
        excerpts = " ".join(f"[{i + 1}] {item.text[:240]}" for i, item in enumerate(evidence[:3]))
        return (f"基于已检索证据：{excerpts}\n\n"
                "建议：保全相关日志与样本哈希，关联终端、DNS、代理和身份认证日志；"
                "对命中的 IOC 先监测再按组织流程隔离处置，并以厂商公告确认补丁与缓解措施。")
