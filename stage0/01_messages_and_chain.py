"""
阶段 0 · 第 1 课：消息对象、Prompt 模板、LCEL 数据流

一句话理解本课：
    Agent 的世界里没有"字符串"，只有"消息列表"；
    Prompt 模板 = 批量生产消息列表的模具；
    LCEL 的 `|` = 把上一个组件的输出，塞进下一个组件的输入。

运行（在 Demo 根目录下）：
    python stage0/01_messages_and_chain.py

想先不联网跑通？把 .env 里的 LLM_PROVIDER 改成 fake 即可。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 让脚本能 import 到上一级的 common 包（不用装成 pip 包）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from common.llm import describe_model, get_model


def line(title: str) -> None:
    """打印一条分隔线，方便看清每一步的输出属于哪里。"""
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


# ---------------------------------------------------------------------------
# 第 1 步：四种消息对象
# ---------------------------------------------------------------------------
def step1_messages() -> None:
    line("第 1 步 · 四种消息对象：模型的输入输出其实是一串消息")

    # SystemMessage：设定身份、规则、边界。一条对话通常只在最前面放一条。
    system_msg = SystemMessage(content="你是一个耐心的 Python 助教，回答不超过三句话。")

    # HumanMessage：用户说的话。
    human_msg = HumanMessage(content="什么是 LCEL？")

    # AIMessage：模型说的话。它可能带 tool_calls（阶段 1 会细讲），现在是空的。
    ai_msg = AIMessage(content="LCEL 是 LangChain 表达式语言，用 | 把组件串成管道。")

    # ToolMessage：工具执行结果。它必须带 tool_call_id，用来和"模型发起的那次调用"配对。
    tool_msg = ToolMessage(content="42", tool_call_id="call_demo_001")

    for msg in (system_msg, human_msg, ai_msg, tool_msg):
        # type(msg).__name__ 告诉我们它是哪一类消息
        print(f"{type(msg).__name__:<16} content={msg.content!r}")

    # 模型真正收到的，就是这样一个"消息列表"。角色信息藏在对象类型里，不在字符串里。
    messages = [system_msg, human_msg]
    print("\n传给模型的消息列表 =>", messages)
    print(
        "\n要点：\n"
        "  · 旧教程里的 'role': 'user' 字典写法仍然可用，但对象写法能带 tool_calls 等结构\n"
        "  · ToolMessage 少了 tool_call_id 会直接报错——阶段 1 最常见的问题\n"
        "  · 一条 AIMessage 的 content 可能是空的，而 tool_calls 有内容，这很正常"
    )


# ---------------------------------------------------------------------------
# 第 2 步：Prompt 模板 = 消息列表的模具
# ---------------------------------------------------------------------------
def step2_prompt_template() -> None:
    line("第 2 步 · ChatPromptTemplate：把变量塞进消息结构里")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "你是一个{role}，回答风格：{style}。"),  # {xxx} 是占位符
            ("human", "{question}"),
        ]
    )

    # invoke 的结果不是字符串，而是一个 ChatPromptValue（可以被打印成消息列表看）
    filled = prompt.invoke(
        {"role": "严谨的技术审稿人", "style": "先结论后理由", "question": "LCEL 有必要学吗？"}
    )
    print("模板填入变量后的结果：")
    for m in filled.to_messages():
        print(f"  {type(m).__name__:<14} {m.content}")

    # few-shot：用 MessagesPlaceholder 在固定位置插入一段"历史消息"
    # 这是 Agent 里最常用的技巧：模板 + 运行时动态拼接的历史/工具消息
    few_shot = ChatPromptTemplate.from_messages(
        [
            ("system", "你是小学数学老师，只回答数字。"),
            ("human", "3 + 5 = ?"),
            ("ai", "8"),
            ("human", "7 * 6 = ?"),
            ("ai", "42"),
            MessagesPlaceholder("history"),   # 这里会被真实历史消息填满
            ("human", "{question}"),
        ]
    )
    msgs = few_shot.invoke(
        {
            "history": [HumanMessage(content="100 / 4 = ?"), AIMessage(content="25")],
            "question": "9 * 9 = ?",
        }
    ).to_messages()
    print("\nfew-shot + 历史消息拼出来的完整输入：")
    for m in msgs:
        print(f"  {type(m).__name__:<14} {m.content}")

    print("\n要点：模板只负责拼消息，不做任何推理；它让同样的提问方式可以批量复用。")


# ---------------------------------------------------------------------------
# 第 3 步：LCEL，把 prompt → model → parser 串起来
# ---------------------------------------------------------------------------
def step3_lcel() -> None:
    line("第 3 步 · LCEL：prompt | model | parser")

    model = get_model(temperature=0.2)
    print("当前模型：", describe_model())

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "你是一个说话简洁的中文助教。"),
            ("human", "{question}"),
        ]
    )
    parser = StrOutputParser()   # 把 AIMessage 拆成纯字符串

    # 三个组件首尾相接，`|` 左边输出 = 右边输入
    chain = prompt | model | parser

    # invoke：一次性拿到完整结果
    answer = chain.invoke({"question": "用一句话解释什么是 Agent。"})
    print("\n[invoke 完整输出]")
    print(answer)

    # stream：一个字一个字吐出来（阶段 6 的"打字机效果"就靠它）
    print("\n[stream 流式输出]")
    for chunk in chain.stream({"question": "用三句话说明 Agent 和普通问答的区别。"}):
        print(chunk, end="", flush=True)
    print()

    print(
        "\n要点：\n"
        "  · prompt/model/parser 都是 Runnable，都实现了 invoke/stream/batch\n"
        "  · 所以任意两个都能用 | 连起来，链和模型可以互换使用\n"
        "  · 想调试？把 chain 拆开：先 prompt.invoke(...)，再 model.invoke(那堆消息)"
    )


# ---------------------------------------------------------------------------
# 第 4 步：掀开盖子，看看模型原始返回长什么样
# ---------------------------------------------------------------------------
def step4_raw_response() -> None:
    line("第 4 步 · 不接 parser，直接看 AIMessage 的全部字段")

    model = get_model(temperature=0.2)
    messages = [SystemMessage(content="只回答一个词。"), HumanMessage(content="天空是什么颜色？")]

    raw = model.invoke(messages)   # 注意：这里不经过 parser
    print("类型          :", type(raw).__name__)
    print("content       :", raw.content)
    print("tool_calls    :", raw.tool_calls)        # 阶段 1 的主角，现在应为 []
    print("usage_metadata:", raw.usage_metadata)    # token 用量，做成本控制时用
    print("id            :", raw.id)

    # content_blocks 是新版统一的多模态内容表示（文本/图片/工具调用都在里面）
    try:
        print("content_blocks:", raw.content_blocks)
    except Exception as exc:                       # 老一些的版本没有这个属性
        print("content_blocks: 当前版本不支持 ->", exc)

    print(
        "\n要点：\n"
        "  · StrOutputParser 帮你丢掉了除 content 之外的一切\n"
        "  · 一旦开始做 Agent，你就必须保留 AIMessage 本身（里面有 tool_calls）\n"
        "  · usage_metadata 是做成本/限流的基础，别等到上线才想起来"
    )


if __name__ == "__main__":
    step1_messages()
    step2_prompt_template()
    step3_lcel()
    step4_raw_response()
    line("本课结束 · 去看 README 里的思考题")
