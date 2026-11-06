"""
阶段 1 · 第 1 课：工具是怎么"告诉"模型的

一句话理解本课：
    你写下 @tool 的那一刻，LangChain 就把你的 Python 函数翻译成了一段
    JSON Schema 发给模型。模型看不见你的代码，它只看见这段 JSON。
    模型返回的也不是"结果"，而是"我想调用谁、传什么参数"。

运行（在 Demo 根目录下）：
    python stage1/01_tool_call_basics.py

需要真实模型（DeepSeek / OpenAI / Ollama）。LLM_PROVIDER=fake 时本课会提示跳过。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from common.llm import describe_model, get_model, is_fake
from stage1.tools import ALL_TOOLS, calculator

SYSTEM_PROMPT = (
    "你是一个严谨的助手。需要算数、查时间、看文件时，必须调用工具，"
    "不要心算，也不要编造文件内容。"
)


def line(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def guard() -> bool:
    if is_fake():
        print("当前是 fake 假模型：它不会发起工具调用，第 3、4 步无法演示。")
        print("前两步（工具 schema）已经跑完了，这部分不需要真实模型。")
        print(
            "\n要跑完整课，请编辑 Demo 根目录的 .env：\n"
            "  LLM_PROVIDER=openai\n"
            "  OPENAI_API_KEY=sk-你的DeepSeekKey\n"
            "  OPENAI_BASE_URL=https://api.deepseek.com\n"
            "  MODEL_NAME=deepseek-flash"
        )
        return False
    return True


# ---------------------------------------------------------------------------
# 第 1 步：工具对象里到底有什么
# ---------------------------------------------------------------------------
def step1_tool_object() -> None:
    line("第 1 步 · @tool 把函数变成了一个带 schema 的对象")

    print("工具名   :", calculator.name)
    print("工具描述 :", calculator.description)
    print("参数结构 :", type(calculator.args_schema).__name__)
    print("参数字段 :", list(calculator.args_schema.model_json_schema()["properties"].keys()))

    # model_json_schema 是 pydantic v2 的方法，schema 由函数签名自动推导
    print("\n由函数签名自动生成的 JSON Schema：")
    print(json.dumps(calculator.args_schema.model_json_schema(), ensure_ascii=False, indent=2))

    print(
        "\n要点：\n"
        "  · 工具名 = 函数名；参数名 = 参数名；说明 = docstring 第一段 + Args 段\n"
        "  · 所以「给工具改个名」和「改文档」都是在改 prompt，会直接影响模型选不选它\n"
        "  · 想让描述更可控，可以用 @tool(description=\"...\") 或 args_schema=自定义 Pydantic 模型"
    )


# ---------------------------------------------------------------------------
# 第 2 步：模型真正收到的 JSON
# ---------------------------------------------------------------------------
def step2_wire_format() -> None:
    line("第 2 步 · 线上传输的真实格式（模型看到的就是这个）")

    for t in ALL_TOOLS:
        print(json.dumps(convert_to_openai_tool(t), ensure_ascii=False, indent=2)[:700])
        print("-" * 70)

    print(
        "要点：\n"
        "  · 整段 JSON 是塞在请求的 tools 字段里发出去的，和 messages 平级\n"
        "  · 它会计入 input token，工具越多越贵、也越容易选错（阶段 5 讲怎么办）\n"
        "  · 描述里的中文也算 token，所以描述要「够用」而不是「越长越好」"
    )


# ---------------------------------------------------------------------------
# 第 3 步：bind_tools 之后，模型的返回变了
# ---------------------------------------------------------------------------
def step3_bind_and_invoke() -> None:
    line("第 3 步 · bind_tools + invoke：看 AIMessage.tool_calls")

    model = get_model(temperature=0.0)
    print("当前模型：", describe_model())

    # bind_tools 不改模型本身，它返回一个"知道有哪些工具可用"的新 Runnable
    model_with_tools = model.bind_tools(ALL_TOOLS)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content="帮我算一下 23 * 47 等于多少，顺便告诉我现在几点。"),
    ]

    ai = model_with_tools.invoke(messages)

    print("\n返回类型      :", type(ai).__name__)
    print("content       :", repr(ai.content))
    print("tool_calls 数量:", len(ai.tool_calls))
    print("\ntool_calls 原始内容：")
    print(json.dumps(ai.tool_calls, ensure_ascii=False, indent=2))

    print(
        "\n要点（最重要的一步）：\n"
        "  · 模型没有算出 1081，也没有调用任何东西——它只是「申请」调用\n"
        "  · 真正执行工具的是你的 Python 代码，不是模型\n"
        "  · 一次可能要 1 个，也可能要 2 个（并行），必须用 for 循环处理\n"
        "  · content 经常是空字符串，这不是 bug"
    )


# ---------------------------------------------------------------------------
# 第 4 步：手动补齐这一轮，模型才能给出最终答案
# ---------------------------------------------------------------------------
def step4_manual_round() -> None:
    line("第 4 步 · 手动执行工具，把结果喂回去")

    model = get_model(temperature=0.0).bind_tools(ALL_TOOLS)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content="帮我算一下 23 * 47 等于多少，顺便告诉我现在几点。"),
    ]

    ai = model.invoke(messages)
    messages.append(ai)          # 关键：模型的"调用申请"必须留在历史里

    tool_map = {t.name: t for t in ALL_TOOLS}

    # 逐个执行（数量不定，可能是 0 个、1 个或多个）
    for call in ai.tool_calls:
        name, args, call_id = call["name"], call["args"], call["id"]
        print(f"\n>>> 准备执行 {name}({args})  id={call_id}")

        try:
            observation = tool_map[name].invoke(args)   # 真正执行
        except Exception as exc:                        # 工具炸了也不能让循环崩
            observation = f"工具执行失败：{exc}"

        print(f"<<< 结果: {observation}")

        # tool_call_id 必须原样带回，否则模型无法把"结果"和"申请"对上
        messages.append(
            ToolMessage(content=str(observation), tool_call_id=call_id, name=name)
        )

    # 带上工具结果再问一次，模型这次给出的才是"面向用户的回答"
    final = model.invoke(messages)
    print("\n最终回答：", final.content)

    print(
        "\n现在手里的消息序列（Agent 的「记忆」就是这个）：\n"
        + "\n".join(f"  {i}. {type(m).__name__}" for i, m in enumerate(messages, 1))
    )


if __name__ == "__main__":
    step1_tool_object()
    step2_wire_format()
    if guard():
        step3_bind_and_invoke()
        step4_manual_round()
    line("本课结束 · 下一课把它变成真正的循环")
