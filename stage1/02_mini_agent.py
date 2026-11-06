"""
阶段 1 · 第 2 课：手写一个 Agent 循环（不依赖任何 Agent 封装）

一句话理解本课：
    Agent 的全部秘密就是下面这个 for 循环——
        调模型 → 模型要工具？→ 执行 → 把结果塞回消息 → 再调模型 → 直到它开口说话

运行（在 Demo 根目录下）：
    python stage1/02_mini_agent.py
    python stage1/02_mini_agent.py --scripted          # 无需 API key，用脚本假模型看循环怎么跑
    python stage1/02_mini_agent.py "帮我算 (120-30)/3 并告诉我 ROADMAP.md 多少行"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from common.llm import describe_model, get_model
from stage1.tools import ALL_TOOLS

SYSTEM_PROMPT = """你是一个严谨的中文助手。
规则：
1. 需要计算、查时间、看文件行数时，必须调用工具，不要心算或编造；
2. 一次可以同时调用多个互不依赖的工具；
3. 工具返回的结果如果报错，你要把错误原因告诉用户，并给出替代方案；
4. 回答简洁，不要复述工具的原始输出格式。"""


# ---------------------------------------------------------------------------
# 核心：整个 Agent 就是这个函数
# ---------------------------------------------------------------------------
def run_agent(
    model,
    tools,
    question: str,
    *,
    max_steps: int = 8,
    verbose: bool = True,
) -> tuple[str, list]:
    """跑一个完整的 Agent 循环，返回 (最终回答, 完整消息列表)。

    max_steps 是安全阀：模型可能一直"想再查一下"，没有上限就会烧钱。
    """
    # 1) 把工具"挂"到模型上：模型从此知道有哪些工具、参数长什么样
    model_with_tools = model.bind_tools(tools)
    tool_map = {t.name: t for t in tools}   # 名字 -> 工具对象，用于分发

    # 2) 对话状态就是这一串消息，没有别的东西
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=question)]

    tool_call_count = 0

    for step in range(1, max_steps + 1):
        # ---- 2.1 问模型：下一步干什么？----
        ai = model_with_tools.invoke(messages)
        messages.append(ai)   # 模型这一轮说的话，必须进历史

        if verbose:
            print(f"\n[第 {step} 步] 模型返回：{len(ai.tool_calls)} 个工具调用")

        # ---- 2.2 没有工具调用 = 它准备给最终答案了，循环结束 ----
        if not ai.tool_calls:
            if verbose:
                print("[结束] 模型不再需要工具，输出最终回答")
            return ai.content, messages

        # ---- 2.3 有调用就逐个执行（可能 1 个，也可能并行多个）----
        for call in ai.tool_calls:
            name = call["name"]
            args = call["args"]
            call_id = call["id"]
            tool_call_count += 1

            if verbose:
                print(f"   → 调用 {name}({args})")

            # 工具不存在 / 抛异常，都不能让整个循环崩掉
            if name not in tool_map:
                observation = f"错误：没有名为 {name} 的工具，可用工具是 {list(tool_map)}"
            else:
                try:
                    observation = tool_map[name].invoke(args)
                except Exception as exc:                      # noqa: BLE001
                    observation = f"工具 {name} 执行失败：{type(exc).__name__}: {exc}"

            if verbose:
                print(f"   ← 返回 {str(observation)[:120]}")

            # 关键：tool_call_id 必须和上面那次调用一模一样
            messages.append(
                ToolMessage(content=str(observation), tool_call_id=call_id, name=name)
            )

    # ---- 2.4 步数用尽：这是一种真实存在的失败模式 ----
    if verbose:
        print(f"\n[警告] 达到最大步数 {max_steps}，强制停止")
    messages.append(
        AIMessage(content="（已达到最大工具调用步数，任务可能没有完成，请缩小问题范围后重试）")
    )
    return messages[-1].content, messages


# ---------------------------------------------------------------------------
# 离线演示：一个"照着剧本说话"的假模型
# ---------------------------------------------------------------------------
class ScriptedModel:
    """模拟模型行为：按剧本返回 AIMessage。用来在没有 API key 时看清循环结构。

    它只需要实现两个方法：bind_tools（原样返回自己）和 invoke（吐出下一条剧本）。
    """

    def __init__(self, replies: list[AIMessage]):
        self._replies = replies
        self._index = 0

    def bind_tools(self, tools, **kwargs):    # noqa: ARG002
        return self

    def invoke(self, messages, **kwargs):     # noqa: ARG002
        reply = self._replies[min(self._index, len(self._replies) - 1)]
        self._index += 1
        return reply


def scripted_agent() -> ScriptedModel:
    """剧本：先算一个数，再同时查时间和数行数，最后给结论。"""
    return ScriptedModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "calculator", "args": {"expression": "23*47"},
                     "id": "call_001", "type": "tool_call"}
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_current_time", "args": {}, "id": "call_002", "type": "tool_call"},
                    {"name": "count_lines", "args": {"file_path": "ROADMAP.md"},
                     "id": "call_003", "type": "tool_call"},
                ],
            ),
            AIMessage(content="23*47 = 1081；现在是下午；ROADMAP.md 有 251 行。"),
        ]
    )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="手写 Agent 循环演示")
    parser.add_argument("question", nargs="*", help="要问的问题")
    parser.add_argument("--scripted", action="store_true", help="离线剧本模式，不调用真实模型")
    parser.add_argument("--show-messages", action="store_true", help="结束后打印完整消息列表")
    args = parser.parse_args()

    question = " ".join(args.question) or "先算一下 23*47，再看看现在几点，最后告诉我 ROADMAP.md 有多少行。"

    if args.scripted:
        print("模式：离线剧本（不联网、不花钱，用来观察循环结构）")
        model = scripted_agent()
    else:
        print("模型：", describe_model())
        model = get_model(temperature=0.0)

    print(f"问题：{question}")
    print("-" * 70)

    answer, messages = run_agent(model, ALL_TOOLS, question)

    print("\n" + "=" * 70)
    print("最终回答")
    print("=" * 70)
    print(answer)

    stats = {
        "消息条数": len(messages),
        "工具调用次数": sum(1 for m in messages if isinstance(m, ToolMessage)),
        "模型调用次数": sum(1 for m in messages if isinstance(m, AIMessage)),
    }
    print("\n本轮统计：", stats)

    if args.show_messages:
        print("\n完整消息序列：")
        for i, m in enumerate(messages, 1):
            preview = (m.content or "")[:60].replace("\n", " ")
            extra = f" tool_calls={len(m.tool_calls)}" if getattr(m, "tool_calls", None) else ""
            print(f"  {i:>2}. {type(m).__name__:<14}{extra} {preview}")


if __name__ == "__main__":
    main()
