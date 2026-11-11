# stage0 学习笔记（消息对象、Prompt 模板、LCEL、结构化输出）

> 对应课程：`stage0/01_messages_and_chain.py`、`stage0/02_requirement_assistant.py`
> 本文由三份笔记合并而成，分三部分：① 排障记录 ② 概念问答 ③ 结构化输出方式对比。

---

# 第一部分 · 排障记录：运行 02_requirement_assistant.py 的四层报错

> 日期：2026-11-12
> 场景：首次运行 `stage0/02_requirement_assistant.py`，从环境到 API 一共剥开了四层问题。
> 关键经验：**换模型供应商时，报错是一层层剥开的**——网络/认证通了才会暴露参数兼容性问题，参数兼容了才会暴露能力限制。

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

## 修复总览

| # | 报错 | 层次 | 根因 | 修复 |
|---|------|------|------|------|
| 1 | `ModuleNotFoundError: langchain_core` | 环境 | 终端用了系统 Python，不是 `.venv` | 用 `.venv\Scripts\python.exe` 运行 |
| 2 | `401 api key ****here is invalid` | 认证 | 系统环境变量残留占位符 key，优先级高于 `.env` | 删除用户级 `OPENAI_API_KEY` 环境变量，重开终端 |
| 3 | `400 response_format type is unavailable` | API 兼容 | DeepSeek 不支持 `response_format: json_schema` | `with_structured_output(..., method="function_calling")` |
| 4 | `400 Thinking mode does not support this tool_choice` | 模型能力 | 思考模式模型不接受强制 tool_choice | `.env` 改 `MODEL_NAME=deepseek-chat` |

## 值得记住的三点

1. **终端 vs IDE 的解释器可能不同**：PyCharm 默认用项目 venv，终端的 `python` 不一定。
   遇到 `ModuleNotFoundError` 先确认 `python -c "import sys; print(sys.executable)"` 指向哪。
2. **`.env` 不等于一定生效**：`python-dotenv` 默认不覆盖已存在的环境变量；
   系统里残留的同名变量会"静默"劫持你的配置。401 且脱敏值可疑时，优先查系统环境变量。
3. **第三方兼容 OpenAI 接口 ≠ 行为等价**：DeepSeek 对 `response_format: json_schema`
   和强制 `tool_choice` 的支持与 OpenAI 有差异。换供应商时做好"逐层剥错"的心理准备，
   每修一层就重新跑一次，看下一层暴露什么。

---

# 第二部分 · 概念问答十二则

## 一、消息对象（01 课）

### Q1：第 55–57 行的循环是 Python 的循环输出语法吗？

是。三处都是纯 Python 基础语法，与 LangChain 无关：

```python
for msg in (system_msg, human_msg, ai_msg, tool_msg):
    print(f"{type(msg).__name__:<16} content={msg.content!r}")
```

- `for ... in 元组`：遍历元组，每轮把一条消息赋给 `msg`
- `{type(msg).__name__:<16}`：取类名，左对齐、占 16 字符宽（保证冒号后竖向对齐）
- `{msg.content!r}`：`!r` 以 repr 形式输出（字符串带引号），方便看清边界

### Q2：step1 里为什么每条 Message 都用独立变量存储？

教学代码的选择，不是 LangChain 的要求。三个原因：

1. **逐个展示四种消息类型**：拆开存 + 循环打印，输出一条一条列出，教学效果清楚
2. **强调"消息是一等对象，不是字典"**：角色信息藏在对象类型里（`HumanMessage` 类型即 "user"），不在 `"role": "user"` 字符串里
3. **ToolMessage 必须单独构造**：它多了个关键参数 `tool_call_id`，少了会报错

实际开发中不需要这么多中间变量，直接内联进列表即可：

```python
messages = [SystemMessage(content="..."), HumanMessage(content="...")]
```

## 二、Prompt 模板（01 课）

### Q3：ChatPromptTemplate.from_messages 是什么方法？

一个**类方法**：接收一组"消息描述"，组装成一个可复用的**聊天模具**。

- 输入：按顺序排的消息定义——`(角色, 文本)` 元组、消息对象、或 `MessagesPlaceholder`
- 输出：一个 `ChatPromptTemplate` 对象（此刻只是模具，不产生消息）
- 每次 `invoke({...})` 填入变量，才生产出一份完整的消息列表

它和简化版 `from_template` 的区别：能表达**多条不同角色**的消息（system + human 组合、few-shot、历史占位符）。

在 LCEL 里的位置：它也是 `Runnable`，所以能进管道 `chain = prompt | model | parser`。
分工是——**模板把变量加工成消息列表，模型消费消息列表，parser 把结果变回简单类型**。

### Q4：ChatPromptTemplate 就是"组装提示词的"，这个理解对吗？

基本对，但要修正两点让它更精确：

1. **组装的产物不是"一段提示词"，而是"一个消息列表"**。
   `PromptTemplate` 输出字符串（旧文本补全模式）；`ChatPromptTemplate` 输出带角色的消息对象（现代聊天模型的输入格式）。
2. **价值不在"组装"，而在"复用"**。结构定一次，变量换无限次：

   ```python
   prompt.invoke({"role": "技术审稿人", "question": "问题A"})
   prompt.invoke({"role": "小学老师",   "question": "问题B"})
   ```

一句话版本（就是 01 课文件第 6 行）：**Prompt 模板 = 批量生产消息列表的模具**。`from_messages` 是"开模"，`invoke` 是"注塑"。

### Q5：每次请求 LLM 之前都要用 ChatPromptTemplate 吗？

**不是必须的**。01 课的 `step4` 就是直接传消息列表：

```python
model.invoke([SystemMessage(content="..."), HumanMessage(content="...")])
```

判断标准只有一条：**有没有变量、会不会复用**。

| 方式 | 适用场景 |
|------|----------|
| 直接传消息列表 | 内容写死、只用一次 |
| `ChatPromptTemplate` | 同一结构重复使用，只是变量不同 |
| 模板 + `\|` 进链 | 运行时动态注入历史消息、批量调用、做 Agent 多轮对话 |

模板本质是"复用性工具"，和是否调用 LLM 无关。

## 三、记忆与 MessagesPlaceholder（01 课）

### Q6：想给会话加记忆，是不是"第一次请求做好提示词，后续靠记忆能力"就行？

方向对一半，关键误解要纠正：**每一轮都要重新组装完整的消息列表**。

因为 LLM 是无状态的——所谓"会话记忆"，实际是这样循环的：

```
第 1 轮：[system, human_1]                                → ai_1
第 2 轮：[system, human_1, ai_1, human_2]                 → ai_2
第 3 轮：[system, human_1, ai_1, human_2, ai_2, human_3]  → ...
```

记忆的本体是**你在客户端维护、不断增长的 `history` 消息列表**，每轮整包重发。
而模板（含 `MessagesPlaceholder`）恰恰是**每轮都执行**的工厂：

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个耐心的 Python 助教。"),
    MessagesPlaceholder("history"),   # 每轮填充不断增长的历史
    ("human", "{question}"),
])

history = []
for user_input in ["first?", "second?", "third?"]:
    result = chain.invoke({"history": history, "question": user_input})
    history += [HumanMessage(content=user_input), AIMessage(content=result)]
    #                        ↑ 记忆的本质就这两行：本轮消息追加进历史，下一轮整包重发
```

分工：**模板管"每轮把历史整齐地重新组装"，history 列表管"记住"**。
（历史太长要裁剪，否则 token 爆炸——这是记忆管理代码的职责。）

### Q7：MessagesPlaceholder 的历史消息是从哪里来的？

**没有自动来源**——它就是 `invoke` 时你传进去的同名 key：

```python
few_shot.invoke({"history": [HumanMessage(...), AIMessage(...)], "question": "..."})
```

`MessagesPlaceholder("history")` 的语义：执行时从输入字典取 key 为 `"history"` 的值，
把那一堆消息**原样展开**到模板中这个位置。

消息的原生来源只有两个：用户说的话（你 new 一个 `HumanMessage`）、模型的回答（它返回 `AIMessage`，你保存下来）。其他一切都是搬运。

几个约定/坑：

- 值必须是**消息对象列表**，传字符串列表会报错
- key 缺失直接报错；`MessagesPlaceholder("history", optional=True)` 可声明"没传也不报错"
- key 名不是保留字，改 `"chat_history"` 也行，只要创建模板到 invoke 全程一致

### Q8：说的"魔法"是什么意思？

指一种容易产生的错觉：**以为某个名字（如 `"history"`）是框架内置保留字，框架"天生"理解它、自动生效。**

真相很朴素：它只是**一个普通约定，由你自己从头到尾保持一致**。

- `MessagesPlaceholder("history")` = 创建模板时声明"去输入字典找 `history` 这个 key"
- `invoke({"history": ...})` = 调用时按约定提供这个 key
- 两边对不上 → 报 KeyError，框架不会"猜"或"兜底"

类比普通 Python 函数：模板里的每个占位符/MessagesPlaceholder 是**形参**，invoke 传的字典是**实参**——名字全是你自己定的，和 `def f(name)` + `f(name="Alice")` 一回事。

### Q9：为什么 history 不用花括号，{question} 却要？

因为**两个类的接口不同**，对应两种"洞"：

- **`{question}`：嵌在文本中间的小洞**——那条 human 消息是普通文本
  （比如 `"请用英文回答：{question}"`，前半固定、只有洞要填），由 LangChain 借用 `str.format` 风格替换成**一段文字**
- **`MessagesPlaceholder("history")`：单独占一行的整块插槽**——`"history"` 是它的**构造参数**（名字本身就是标识，不需要也不允许加花括号），替换单位是**一组消息对象**

为什么历史不能写 `("human", "{history}")`？因为花括号填进来的是**一个字符串**，
而历史是**一组消息对象**（且数量动态），一条 human 消息的 content 塞不下，
能整体承载的只有 MessagesPlaceholder。

> 一句话：**文本里留个洞 → `{name}`；一整块动态消息序列 → `MessagesPlaceholder("name")`。**

（补充修正：`{question}` 长得像 Python 格式化语法，但它**不是 Python 语法**——写模板那一刻它只是普通文本，真正替换发生在 `invoke` 时、由 LangChain 完成；它只认 invoke 字典，不看任何 Python 变量。）

## 四、结构化输出（02 课）

### Q10：为什么 demo_structured 的返回值是 RequirementAnalysis 类型？

**因为 LCEL 链的 `invoke` 返回类型 = 链尾组件的输出类型。**

```python
structured_model = model.with_structured_output(RequirementAnalysis)
chain = prompt | structured_model
```

`with_structured_output` 做两件事：

1. **发送时约束**：把 Pydantic 类转成 JSON Schema，作为工具定义发给模型，强迫模型按结构填字段
2. **返回时解析**：模型返回后自动校验并**构造出真正的 `RequirementAnalysis` 实例**

所以 `chain.invoke({...})` 返回的就是这个 Pydantic 对象，能直接 `result.model_dump()`。
`RequirementAnalysis | None` 中的 `None` 只是 fake 模式下跳过时的占位返回（函数里 `is_fake()` 分支 `return None`）。

对照：链尾换成 `StrOutputParser()`，返回就是 `str`（01 课的写法）。

### Q11：with_structured_output 里的类型是开发者决定的"any 类型"吗？

**由开发者决定——对；但它是强约束类型，不是 any。**

- 开发者可以传任意"结构描述"：Pydantic `BaseModel`（本课用法，校验最强）、`TypedDict`、或 JSON Schema 字典
- 但它对**双方都是硬约束**：
  - 对模型：字段定义以 JSON Schema 发过去，只能在框架里填，不能写散文、不能发明字段
  - 对你：返回内容过 Pydantic 校验，类型不对/缺字段直接报错，不会默默给你畸形对象

类比：`RequirementAnalysis` 是表单模板（你设计表单），schema 是"只能在这些格子里填"，Pydantic 是交回时的审核员。**any 没有表单也没有审核，这里两者都齐了。**

价值所在（02 课打印的要点）：`confidence` 是 float、`constraints` 是 list——
拿到的是**可以直接写进 if 判断的可靠数据**，`StrOutputParser` 给不了你。

### Q12：在 from_messages 里加 MessagesPlaceholder 就能把历史加进上下文了吧？

对。放在 02 课语境里：

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder("history"),      # 新增：历史插槽
    ("human", "用户的原始需求：{request}"),
])

history = []
result = chain.invoke({"request": REQUEST, "history": history})
history += [HumanMessage(content=REQUEST), AIMessage(content=result.next_question)]
```

要点：

- 第一轮 `history` 是空列表 → 展开为零条消息，效果和不加一样
- **位置有讲究**：放在 system 之后、新消息之前，模型才能"知道之前聊了什么"再答本轮
- 可选声明：`MessagesPlaceholder("history", optional=True)`，不传 key 也不报错

呼应 Q6 的结论：加了它，模具就多了"每轮从传入的 history 重新组装上下文"的能力；
记忆的存取仍在你的代码（或 LangGraph 记忆组件）手里，模板只负责在正确位置展开。

### 附：贯穿全部问答的一条主线

```
模型真正吃的：消息列表（对象，角色藏在类型里）        ← Q1 Q2
结构要复用：  ChatPromptTemplate.from_messages 开模   ← Q3 Q4 Q5
记忆 = 每轮把完整历史重发：history 列表 + Placeholder ← Q6 Q7
名字只是约定：形参/实参，没有魔法                     ← Q8 Q9
链尾定类型：  with_structured_output 锁死输出结构      ← Q10 Q11 Q12
```

---

# 第三部分 · 结构化输出的三种方式：json_schema / function_calling / json_mode

> 记录 `with_structured_output` 的 `method` 参数的完整选项与选择依据。
> 问题 3、4（见第一部分）即本主题的实战案例。
> 依据：本项目 `.venv` 中 `langchain_openai` 源码确认，`method` 合法值只有这三个：
> `Literal["function_calling", "json_mode", "json_schema"]`。

## 一、同一个目标，三种实现层次

三者目标相同——让模型按给定 JSON Schema 输出结构化数据——区别在**约束发生在哪一层**：

```
解码层（最硬）→ 协议层 → 提示词层（最软）
json_schema      function_calling   json_mode / 手写 parser
```

**约束越靠底层越可靠，供应商支持面也越窄。**

## 二、三种方式的机制

### 1. json_schema（解码层硬约束）

请求形态：

```json
{
  "response_format": {
    "type": "json_schema",
    "json_schema": { "name": "...", "schema": {...}, "strict": true }
  }
}
```

- Schema 在 `response_format` 参数里，**约束模型生成文本的格式**
- strict 模式是采样层约束（constrained decoding）：每个 token 只能在 schema 允许的范围内生成，理论上 **100% 合规**
- 输出是 content 里的 JSON 文本

### 2. function_calling（工具调用协议层）

请求形态：

```json
{
  "tools": [{ "type": "function",
              "function": { "name": "RequirementAnalysis", "parameters": {schema} } }],
  "tool_choice": { "type": "function", "function": { "name": "RequirementAnalysis" } }
}
```

- Schema 被包装成**工具定义**，`tool_choice` 强制模型"必须调用这个工具"
- 结构化数据藏在**工具调用的参数**（`tool_calls[].function.arguments`）里，LangChain 取出后构造对象
- 保证强度：**行为引导**而非硬约束——高概率符合，仍可能偶发填错（由 Pydantic 校验兜底报错）

### 3. json_mode（提示词层）

请求形态：

```json
{ "response_format": { "type": "json_object" } }
```

- **只保证输出是合法 JSON，不保证字段符合 schema**
- Schema 不会自动进 `response_format`，而是**以文字形式拼进提示词**，模型"看着说明书"填
- 坑：OpenAI 系要求提示词里必须出现 "json" 一词，否则 400
- 返回后同样过 Pydantic 校验，失败直接报错，没有解码层兜底

## 三、对比总表

| | `json_schema` | `function_calling` | `json_mode` |
|---|---|---|---|
| Schema 放哪 | `response_format`（解码层） | `tools` + 强制 `tool_choice`（协议层） | 提示词文字 + `json_object`（提示词层） |
| 保证强度 | 100% 符合 schema（strict） | 高概率符合，靠模型自觉 | 只保证合法 JSON，字段对不对看模型 |
| 输出形态 | content 里的 JSON 文本 | tool_calls 的 arguments | content 里的 JSON 文本 |
| 典型支持 | OpenAI 官方 | 几乎所有支持工具调用的供应商（含 DeepSeek） | 兼容面最广（OpenAI / DeepSeek / Ollama 等） |
| DeepSeek 支持 | ❌ 400 拒绝 | ✅ | ✅ |
| 本项目实战 | ❌ | ✅（02 课采用） | 可用但保证更弱 |

选择优先级：**`json_schema` > `function_calling` > `json_mode`**（保证强度递减、兼容面递增）。

## 四、`with_structured_output` 之外的老派做法（了解即可）

`json_mode` 和下面的手写做法本质同一档——全靠提示词约束，只是不传 `response_format`：

```python
from langchain_core.output_parsers import PydanticOutputParser

parser = PydanticOutputParser(pydantic_object=RequirementAnalysis)
prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT + "\n" + parser.get_format_instructions()),  # ← schema 塞进提示词
    ("human", "{request}"),
])
chain = prompt | model | parser   # 模型自己输出 JSON 文本，parser 负责解析
```

- 老教程常见写法，常配合 `OutputFixingParser`（解析失败时把报错喂回模型重试）
- 更底层还有**语法约束解码**方案（outlines、llama.cpp 的 GBNF 语法等），本地推理时逐 token 限制，效果等同 strict json_schema——但那是推理框架层面的技术，不属于 LangChain 的 `method` 参数

## 五、本项目的实战结论

```python
# OpenAI 官方 API、要最强结构保证 → 默认即可
model.with_structured_output(X)                            # 默认 method="json_schema"

# 供应商不支持 json_schema（DeepSeek 实测 400）→ 改工具调用
model.with_structured_output(X, method="function_calling") # ← 02 课的修复

# 连强制 tool_choice 都不支持的思考模型 → 换非思考模型（deepseek-chat）
```

两点提醒：

1. 02 课原注释（"把 Pydantic 模型转成 JSON Schema 作为工具定义发给模型"）描述的其实是
   function_calling 路线，与 `json_schema` 默认路线是两回事——看报错时注意区分。
2. 换供应商时先查它的能力表（是否支持 json_schema、是否支持强制 tool_choice），
   再定 `method`；选 `method` 本质上就是"查表"。
