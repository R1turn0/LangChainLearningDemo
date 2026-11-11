# 结构化输出的三种方式：json_schema / function_calling / json_mode

> 记录 `with_structured_output` 的 `method` 参数的完整选项与选择依据。
> 背景排错见 `troubleshooting_02_requirement_assistant.md`（问题 3、4 即本主题的实战案例）。
> 依据：本项目 `.venv` 中 `langchain_openai` 源码确认，`method` 合法值只有这三个：
> `Literal["function_calling", "json_mode", "json_schema"]`。

---

## 一、同一个目标，三种实现层次

三者目标相同——让模型按给定 JSON Schema 输出结构化数据——区别在**约束发生在哪一层**：

```
解码层（最硬）→ 协议层 → 提示词层（最软）
json_schema      function_calling   json_mode / 手写 parser
```

**约束越靠底层越可靠，供应商支持面也越窄。**

---

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

---

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

---

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

---

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
