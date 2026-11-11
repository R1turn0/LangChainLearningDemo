# 排障记录 · stage0/02_requirement_assistant.py

> 日期：2026-11-12
> 场景：首次运行 `stage0/02_requirement_assistant.py`，从环境到 API 一共剥开了四层问题。
> 关键经验：**换模型供应商时，报错是一层层剥开的**——网络/认证通了才会暴露参数兼容性问题，参数兼容了才会暴露能力限制。

---

## 问题 1：ModuleNotFoundError: No module named 'langchain_core'

**现象**

```text
Traceback (most recent call last):
  File "stage0/02_requirement_assistant.py", line 26, in <module>
    from langchain_core.output_parsers import StrOutputParser
ModuleNotFoundError: No module named 'langchain_core'
```

**根因**

依赖都安装在项目的 `.venv` 虚拟环境里，但在终端里直接敲 `python`，用的是**系统全局 Python**，它看不到 `.venv` 里的包。
之前 01 课能跑，是因为在 PyCharm 里运行（默认使用项目的 venv 解释器）；这次在终端跑，暴露了解释器不一致的问题。

**修复（任选其一）**

```powershell
# 方式 A：明确指定 venv 的解释器
.venv\Scripts\python.exe stage0\02_requirement_assistant.py

# 方式 B：先激活虚拟环境，再正常运行
.venv\Scripts\Activate.ps1
python stage0\02_requirement_assistant.py
```

PyCharm 用户：`Settings → Project → Python Interpreter` 选 `.venv\Scripts\python.exe`。

---

## 问题 2：401 - Authentication Fails, Your api key: ****here is invalid

**现象**

```text
openai.AuthenticationError: Error code: 401 - Authentication Fails,
Your api key: ****here is invalid
```

注意脱敏后露出的 `here`——这是一个重要线索。

**根因**

Windows **用户级环境变量**里残留了一个占位符 `OPENAI_API_KEY`（值是 `your_api_key_here` 这类示例值，从未替换）。
`python-dotenv` 的默认行为是**不覆盖已存在的环境变量**，所以 `common/llm.py` 里 `load_dotenv()` 加载 `.env` 时，真实的 key 没有生效——程序实际发出的是系统环境变量里的那个假 key。

**排查方法**

```powershell
# 查看用户级环境变量（不打印完整值，只看长度和末尾）
[Environment]::GetEnvironmentVariable('OPENAI_API_KEY','User')
```

**修复**

```powershell
# 删除残留的占位环境变量（本身就没用）
[Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $null, 'User')
```

删除后必须**重开终端**（已打开的终端不会刷新环境变量）。

> 备选方案：不想删系统变量，可让 dotenv 强制覆盖——
> 在 `common/llm.py` 中把 `load_dotenv()` 改为 `load_dotenv(override=True)`。

---

## 问题 3：400 - This response_format type is unavailable now

**现象**

```text
openai.BadRequestError: Error code: 400 - This response_format type is unavailable now
```

**根因**

`with_structured_output(RequirementAnalysis)` 默认走 `method="json_schema"` 路线：
把 Pydantic 模型转成 JSON Schema，塞进 `response_format` 参数发给模型。
但 **DeepSeek 的 API 不支持 `response_format: json_schema`**（只支持 `json_object`，
且要求提示词里出现 "json" 字样），于是直接拒绝了请求。

这是"兼容 OpenAI 接口但不 100% 等价"的典型差异点。

**修复**

改用 `method="function_calling"`——把 Pydantic 类注册成一个"工具"让模型调用，
返回参数就是结构化 JSON。DeepSeek 对 function calling 支持完整：

```python
structured_model = model.with_structured_output(
    RequirementAnalysis, method="function_calling"
)
```

（已修改 `Demo/stage0/02_requirement_assistant.py` 第 67 行附近。）

---

## 问题 4：400 - Thinking mode does not support this tool_choice

**现象**

```text
openai.BadRequestError: Error code: 400 - Thinking mode does not support this tool_choice
```

**根因**

`.env` 里的 `MODEL_NAME=deepseek-flash` 对应**思考模式（thinking）模型**。
这类模型只接受 `tool_choice="auto"`（模型自己决定调不调工具），
而 LangChain 的 `function_calling` 结构化输出默认会**强制指定**调用某个具体工具，
思考模式直接拒绝这种强制。

**修复**

`.env` 中换用非思考模式模型（第 4 行）：

```ini
MODEL_NAME=deepseek-chat
```

---

## 修复总览

| # | 报错 | 层次 | 根因 | 修复 |
|---|------|------|------|------|
| 1 | `ModuleNotFoundError: langchain_core` | 环境 | 终端用了系统 Python，不是 `.venv` | 用 `.venv\Scripts\python.exe` 运行 |
| 2 | `401 api key ****here is invalid` | 认证 | 系统环境变量残留占位符 key，优先级高于 `.env` | 删除用户级 `OPENAI_API_KEY` 环境变量，重开终端 |
| 3 | `400 response_format type is unavailable` | API 兼容 | DeepSeek 不支持 `response_format: json_schema` | `with_structured_output(..., method="function_calling")` |
| 4 | `400 Thinking mode does not support this tool_choice` | 模型能力 | 思考模式模型不接受强制 tool_choice | `.env` 改 `MODEL_NAME=deepseek-chat` |

---

## 值得记住的三点

1. **终端 vs IDE 的解释器可能不同**：PyCharm 默认用项目 venv，终端的 `python` 不一定。
   遇到 `ModuleNotFoundError` 先确认 `python -c "import sys; print(sys.executable)"` 指向哪。
2. **`.env` 不等于一定生效**：`python-dotenv` 默认不覆盖已存在的环境变量；
   系统里残留的同名变量会"静默"劫持你的配置。401 且脱敏值可疑时，优先查系统环境变量。
3. **第三方兼容 OpenAI 接口 ≠ 行为等价**：DeepSeek 对 `response_format: json_schema`
   和强制 `tool_choice` 的支持与 OpenAI 有差异。换供应商时做好"逐层剥错"的心理准备，
   每修一层就重新跑一次，看下一层暴露什么。
