"""
common/llm.py —— 模型工厂（整个学习路线共用这一个文件）

为什么要单独抽一个工厂？
    阶段 1 之后我们会频繁换模型（OpenAI 兼容服务 / Ollama / 离线假模型），
    如果每个示例里都写一遍 ChatOpenAI(...)，换模型就要改 N 个文件。
    所以：所有"怎么连模型"的细节只在这里出现一次，示例代码只调 get_model()。

三个环境变量开关（写在 .env 里）：
    LLM_PROVIDER=openai   -> 走 langchain_openai.ChatOpenAI（DeepSeek / vLLM / 中转站都算）
    LLM_PROVIDER=ollama   -> 走 langchain_ollama.ChatOllama（本地模型）
    LLM_PROVIDER=fake     -> 走 FakeListChatModel（不联网的假模型，用来先跑通代码结构）
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel

# load_dotenv() 会读取当前工作目录下的 .env 文件。
# 注意：它只在"当前工作目录"找，所以请在 Demo 根目录下运行脚本。
load_dotenv()

# 假模型固定返回这句话，方便一眼看出"这次没真的调用大模型"
FAKE_REPLY = "（离线假模型）收到，我已经理解你的问题了。"


def get_provider() -> str:
    """读当前用哪个 provider；没配置就默认 openai。"""
    return os.getenv("LLM_PROVIDER", "openai").strip().lower()


def is_fake() -> bool:
    """当前是不是离线假模型（有些功能假模型做不了，比如结构化输出）。"""
    return get_provider() == "fake"


def _build_fake() -> BaseChatModel:
    """离线假模型：不发网络请求，用来先验证代码结构是否跑得通。"""
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    return FakeListChatModel(responses=[FAKE_REPLY])


def _build_openai(temperature: float) -> BaseChatModel:
    """OpenAI 及一切兼容 OpenAI 协议的服务。"""
    from langchain_openai import ChatOpenAI

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key == "sk-xxx":
        raise RuntimeError(
            "没有读到 OPENAI_API_KEY。\n"
            "  1) 把 .env.example 复制成 .env\n"
            "  2) 填上真实的 key（以及需要的话 OPENAI_BASE_URL）\n"
            "  3) 或者先把 .env 里的 LLM_PROVIDER 改成 fake，纯离线跑通代码结构"
        )

    kwargs = {
        "model": os.getenv("MODEL_NAME", "gpt-4o-mini"),
        "api_key": api_key,
        "temperature": temperature,   # 0 = 尽量确定，工具调用/结构化输出建议 0~0.3
        "timeout": 60,                # 单次请求超时（秒），阶段 6 会专门讲重试
        "max_retries": 2,             # 框架自带的网络重试
    }
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    if base_url:                      # 留空就用官方地址
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def _build_ollama(temperature: float) -> BaseChatModel:
    """本地 Ollama。需要先 `ollama serve` 并 `ollama pull <模型名>`。"""
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        temperature=temperature,
        # 本地小模型做工具调用时，num_ctx 太小会"忘记"工具定义，这里给大一点
        num_ctx=8192,
    )


def get_model(temperature: float = 0.0) -> BaseChatModel:
    """返回一个可用的聊天模型。所有示例都通过它拿模型。"""
    provider = get_provider()
    if provider == "fake":
        return _build_fake()
    if provider == "ollama":
        return _build_ollama(temperature)
    if provider == "openai":
        return _build_openai(temperature)
    raise ValueError(f"未知的 LLM_PROVIDER={provider!r}，只支持 openai / ollama / fake")


def describe_model() -> str:
    """给人看的一行说明，打印出来便于确认"我现在连的是谁"。"""
    provider = get_provider()
    if provider == "fake":
        return "provider=fake（离线假模型，不产生真实回答）"
    if provider == "ollama":
        return f"provider=ollama  model={os.getenv('OLLAMA_MODEL', 'qwen2.5:7b')}"
    return (
        f"provider=openai  model={os.getenv('MODEL_NAME', 'gpt-4o-mini')}  "
        f"base_url={os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')}"
    )
