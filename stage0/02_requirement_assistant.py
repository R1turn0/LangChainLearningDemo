"""
阶段 0 · 第 2 课：结构化输出 + 流式输出（需求澄清助手）

一句话理解本课：
    你迟早要把模型的回答"交给程序继续用"。字符串没法可靠地交给程序，
    只有 JSON / Pydantic 对象可以。结构化输出就是让模型"按 schema 说话"。

本课做的助手：
    用户丢来一句模糊需求（"我想做个 AI 客服"），
    助手输出一份结构化分析：目标 / 约束 / 未知项 / 下一个该问的问题 / 把握度。

运行（在 Demo 根目录下）：
    python stage0/02_requirement_assistant.py

注意：LLM_PROVIDER=fake 时，结构化输出会被跳过（假模型不会 tool calling）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from common.llm import describe_model, get_model, is_fake

# ---------------------------------------------------------------------------
# 1. 用 Pydantic 定义"模型必须遵守的输出格式"
# ---------------------------------------------------------------------------
# 每个字段的 description 不是写给人看的注释，而是会发给模型的"字段说明书"。
# 描述写得准，模型填得准；描述含糊，字段就开始瞎编。
class RequirementAnalysis(BaseModel):
    goal: str = Field(description="用户真正想达成的目标，用一句中文概括")
    constraints: list[str] = Field(
        description="需求里明确提到的限制，比如预算、时间、平台、必须对接的系统；没有就给空列表"
    )
    unknowns: list[str] = Field(
        description="信息不足、必须先问清楚的点，按重要性排序"
    )
    next_question: str = Field(description="下一步最该问用户的一个问题，要具体、可直接回答")
    confidence: float = Field(
        ge=0.0, le=1.0, description="你对这次理解的把握程度，0 到 1 之间的小数"
    )


SYSTEM_PROMPT = """你是一个需求分析师。
你的任务不是马上给方案，而是把用户那句模糊的话拆成结构化信息。
规则：
1. 不要编造用户没说的信息，拿不准的放进 unknowns；
2. next_question 只能问一个问题，且必须是最影响方案选择的那一个；
3. confidence 要诚实：信息越少，分数越低。"""


def build_analyzer():
    """返回一条"提示词 -> 结构化模型"的链。"""
    model = get_model(temperature=0.0)

    # with_structured_output 做了两件事：
    #   1) 把 Pydantic 模型的字段转成 JSON Schema，作为工具定义发给模型
    #   2) 拿到模型返回后，自动校验并构造成 RequirementAnalysis 对象
    # 所以它只对"支持 tool calling / json schema"的模型有效。
    structured_model = model.with_structured_output(RequirementAnalysis)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "用户的原始需求：{request}"),
        ]
    )
    return prompt | structured_model


# ---------------------------------------------------------------------------
# 2. 主流程
# ---------------------------------------------------------------------------
REQUEST = "我想给公司做一个 AI 客服，能回答产品问题，最好还能直接帮客户下单。"


def demo_structured() -> RequirementAnalysis | None:
    print("\n" + "=" * 70)
    print("第 1 部分 · 结构化输出：让模型交回一个对象")
    print("=" * 70)

    if is_fake():
        print("当前是 fake 假模型，不支持结构化输出，跳过这一部分。")
        print("把 .env 里的 LLM_PROVIDER 改成 openai 或 ollama 再跑一次。")
        return None

    chain = build_analyzer()
    result = chain.invoke({"request": REQUEST})

    print(f"用户需求：{REQUEST}")
    print(f"\n返回对象类型：{type(result).__name__}")
    print("字段如下：")
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    print(
        "\n注意：confidence 不是字符串，是 float；constraints 不是一句话，是 list。\n"
        "这就是可以「直接写进 if 判断」的可靠数据，而 StrOutputParser 给不了你。"
    )
    return result


def demo_streaming(analysis: RequirementAnalysis | None) -> None:
    print("\n" + "=" * 70)
    print("第 2 部分 · 流式输出：让用户不用干等")
    print("=" * 70)

    model = get_model(temperature=0.3)

    # 这一条链的目标变了：不是产出结构化数据，而是"给人读的解释"。
    # 两种输出形态用两条链，比硬塞进一条链清楚得多——这是常见的设计取舍。
    writer_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是一个需求分析师，用口语化的中文向非技术的业务方复述你的理解。"
                "先说你的判断，再列出还需要确认的点，最后提出一个问题。不要用 Markdown 表格。",
            ),
            (
                "human",
                "原始需求：{request}\n\n你此前的结构化分析：{analysis}\n\n请向用户复述。",
            ),
        ]
    )
    chain = writer_prompt | model | StrOutputParser()

    payload = {
        "request": REQUEST,
        "analysis": (
            analysis.model_dump_json() if analysis else "（无结构化分析，请自己判断）"
        ),
    }

    print("模型开始输出（流式，边生成边打印）：\n")
    for chunk in chain.stream(payload):
        # end="" 不换行，flush=True 立刻刷到屏幕——这两行就是"打字机效果"的全部秘密
        print(chunk, end="", flush=True)
    print("\n")


# ---------------------------------------------------------------------------
# 3. 坑点演示：为什么不能"先用字符串再自己 json.loads"
# ---------------------------------------------------------------------------
def demo_why_not_manual() -> None:
    print("=" * 70)
    print("第 3 部分 · 为什么不自己 json.loads")
    print("=" * 70)
    print(
        "手写解析的典型翻车：\n"
        "  1) 模型在 JSON 外面加了句“好的，以下是分析：”—— json.loads 直接抛异常\n"
        "  2) 模型把 confidence 写成 \"高\" —— 类型错了，代码在很远的地方才崩\n"
        "  3) 字段少一个 / 多一个 —— 数据库插入时报 KeyError\n"
        "  4) 流式输出时 JSON 被切成两半，你没法边流边解析\n"
        "with_structured_output 把 1~3 交给框架（schema 校验 + 自动重试机制），\n"
        "第 4 条则要求你像本课一样：结构化归结构化，流式展示归流式展示。"
    )


if __name__ == "__main__":
    print("当前模型：", describe_model())
    analysis = demo_structured()
    demo_streaming(analysis)
    demo_why_not_manual()
    print("\n本课结束。下一步：把 .env 换成你自己的模型，观察 confidence 和 unknowns 的变化。")
