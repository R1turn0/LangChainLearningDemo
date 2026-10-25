# LangChain Agent 系统学习路线（代码实践为主）

> 目标：从"会调模型"到"能自己写出并调试 Agent"，全程使用 LangChain 1.x 新 API。
> 节奏：一次只推进一个阶段；每阶段 = 概念 → 可运行代码（逐行注释）→ 原理与坑点 → 你跑通后进下一阶段。

---

## 一、学习目标（可验证）

学完这份路线，你应该能做到：

1. **说清 Agent 的内部结构**：一条用户消息进来，经过哪些消息对象、哪几次模型调用、哪几次工具执行、状态怎么变。
2. **不依赖框架手写 Agent 循环**，再用 `create_agent` / LangGraph 重写同一逻辑，并说清两者差异。
3. **按任务选范式**：ReAct、Plan-and-Solve、原生 Function Calling、自定义图，知道各自什么时候会翻车。
4. **交付一个能跑的小项目**：带工具、带记忆、带流式输出、带错误处理的问答/科研助手。

---

## 二、推荐版本与依赖

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | **3.12（首选）**，3.11 / 3.13 亦可 | 本机是 3.14.3，官方声明支持，但部分第三方包还没有 3.14 轮子，建议用 3.12 省事 |
| `langchain` | **1.4.x**（当前 1.4.7） | 1.x 主线，`create_agent` 在此 |
| `langchain-core` | 1.7.x（随 langchain 自动装） | 消息、Runnable、Tool 抽象 |
| `langgraph` | 1.2.x（随 langchain 自动装） | Agent 运行时（状态机 / 持久化 / 流式） |
| `langchain-openai` | 1.x | OpenAI 及一切兼容 OpenAI 协议的服务（DeepSeek、vLLM、中转站） |
| `langchain-ollama` | 1.x | 本地模型（你想换 Ollama 时用） |
| `langgraph-checkpoint-sqlite` | 阶段 3 装 | 对话记忆落盘 |
| `langchain-text-splitters` | 阶段 7 装 | 文档切分 |
| `python-dotenv` | 1.x | 读 `.env` |
| `rich` | 可选 | 阶段 6 做终端流式输出好看一点 |

安装（在 `Demo` 目录）：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install "langchain==1.4.7" langchain-openai langchain-ollama python-dotenv
# 国内网络慢可加：-i https://pypi.tuna.tsinghua.edu.cn/simple
```

**明确不用的旧东西**（网上 90% 教程还在教，照抄会直接报错）：

| 旧写法（0.x） | 现在应该用 |
|---|---|
| `initialize_agent` / `AgentExecutor` | `create_agent(...)` 或自建 `StateGraph`（旧实现已搬到 `langchain-classic`） |
| `ConversationBufferMemory` 等 Memory 类 | checkpointer + `thread_id`（1.x 已移除） |
| `LLMChain` | `prompt \| model \| parser`（LCEL） |
| `agent.run("...")` | `agent.invoke({"messages": [{"role": "user", "content": "..."}]})` |
| `from langchain.agents import tool` | `from langchain_core.tools import tool` |
| `.dict()` / pydantic v1 `BaseModel` | `.model_dump()` / pydantic v2 |

---

## 三、路线总览

| 阶段 | 主题 | 核心产出 | 预计 |
|---|---|---|---|
| 0 | 地基：模型接入 / 消息 / Prompt / 结构化输出 | 需求澄清助手（JSON 输出 + 流式 + 换模型） | 1.5h |
| 1 | 工具调用底层：从 `bind_tools` 到手写 Agent 循环 | `mini_agent.py`（纯手写 while 循环） | 2h |
| 2 | Agent 执行器：`create_agent` 与 LangGraph 状态机 | 同一 Agent 的三种实现对照 | 2h |
| 3 | 记忆与状态：checkpointer / thread / 长期记忆 | 重启不忘事的 SQLite 对话 Agent | 1.5h |
| 4 | 范式对比：ReAct / Plan-and-Solve / FC / 自定义 | 三范式同任务对比实验 + 选型表 | 2h |
| 5 | 工具工程化：自定义工具、多工具编排、安全边界 | 科研助手工具包 v1 | 2h |
| 6 | 流式输出、可观测性、错误重试与降级 | 打字机 CLI + 故障注入演练 | 2h |
| 7 | 落地项目：本地知识库问答 Agent | 带引用、带测试集的可运行项目 | 3h |

---

## 四、分阶段详解

### 阶段 0｜地基：模型接入 + 消息 + Prompt 编排

**知识点**
- `ChatOpenAI` / `init_chat_model` 的统一接口：`invoke` / `batch` / `stream`
- 消息体系：`SystemMessage` / `HumanMessage` / `AIMessage` / `ToolMessage`，以及 `content_blocks`
- `ChatPromptTemplate`、`MessagesPlaceholder`、few-shot 模板
- LCEL 的本质：`Runnable` 串联，数据怎么在管道里流动
- 结构化输出：`with_structured_output(PydanticModel)` vs `JsonOutputParser`（为什么优先前者）
- 用 `.env` 一键切换 OpenAI 兼容服务 / Ollama，代码零改动

**实战小任务**：写"需求澄清助手"——输入一句模糊需求，输出固定 JSON（目标 / 约束 / 未知项 / 下一步要问的问题），并流式打印过程。

**验收标准**
- 能画出 `prompt | model | parser` 每一步的输入输出
- 同一份代码，改 `.env` 就能切到 Ollama，不报错
- 结构化输出字段不符合 schema 时，能看懂报错并修正
- 能解释 `temperature` 对工具调用稳定性的影响

---

### 阶段 1｜工具调用底层：从 `bind_tools` 到手写 Agent 循环

**知识点**
- Function Calling 的本质：工具 → JSON Schema → 模型只**请求**调用，不执行
- `@tool` 装饰器、`args_schema`、docstring 就是提示词
- `bind_tools` / `tool_choice`；一次返回多个 `tool_calls` 怎么处理
- `ToolMessage.tool_call_id` 的配对规则（最常见的报错来源）
- 手写 Agent 循环：调模型 → 有 tool_calls 就执行 → 回填 → 再调 → 无 tool_calls 则结束
- 终止条件、最大步数、工具异常如何回传给模型

**实战小任务**：`mini_agent.py`——3 个工具（安全计算器 / 当前时间 / 文件行数统计），**不用任何 Agent 封装**，纯手写循环，把每一步消息打印出来。

**验收标准**
- 能背出一轮完整消息序列（顺序、角色、字段）
- 模型一次要求调用两个工具时，代码能正确并行执行并回填
- 工具抛异常时循环不崩，模型能读到错误信息并改用其他方式
- 能解释"模型没调工具直接回答"为什么是正常的

---

### 阶段 2｜Agent 执行器：`create_agent` 与 LangGraph 状态机

**知识点**
- `create_agent(model, tools, system_prompt=...)` 内部到底做了什么
- LangGraph 三件套：State / Node / Edge；`MessagesState` + `add_messages` reducer（追加而非覆盖）
- 条件边、`recursion_limit`、`stream` 观察每一步 state
- 为什么 `AgentExecutor` 退役：黑盒、难插桩，被 middleware / graph 取代
- 加一个自定义 state 字段（如 `step_count`）体会 reducer 的作用

**实战小任务**：用 `create_agent` 重建阶段 1 的 mini agent；再用 `StateGraph` 手搭同一张图；三份代码并排对比，打印每步 state。

**验收标准**
- 能画出这张图（模型节点 ⇄ 工具节点，退出条件）
- 能改 state schema 加字段，并说明缺 reducer 会发生什么
- 能调 `recursion_limit` 并观察超限报错
- 能解释 `create_agent` 帮你省掉的 4 件事

---

### 阶段 3｜记忆与状态：checkpointer / thread / 长期记忆

**知识点**
- 短期记忆 = 消息列表 + 持久化；为什么 Memory 类被删除
- `InMemorySaver` / `SqliteSaver`、`thread_id`、`config={"configurable": {...}}`
- 多轮工具对话的完整性：`tool_call_id` 必须成对出现
- 上下文治理：`trim_messages`、摘要中间件、跨会话长期记忆（向量库 / store）
- 会话隔离与用户隔离

**实战小任务**：SQLite 持久化的对话 Agent——`kill` 进程后重开还能接着聊；两个 `thread_id` 互不串台；超过 N 轮自动摘要压缩。

**验收标准**
- 重启进程后继续对话，上下文仍在
- 不同 thread 记忆隔离
- 对话变长时 token 不线性爆炸（能看到摘要生效）
- 能解释为什么"只存最后一句"会毁掉工具调用历史

---

### 阶段 4｜范式对比：ReAct / Plan-and-Solve / Function Calling / 自定义

**知识点**
- ReAct：Thought → Action → Observation；文本协议 vs 原生 function calling
- Plan-and-Solve：planner 出步骤 → executor 逐步执行 → 必要时重规划
- Reflection / self-critique：让模型检查自己的中间结果
- Supervisor 路由（简版多 agent）
- 选型判据：任务可分解性、工具数量、延迟预算、可解释性要求

**实战小任务**：同一个多步任务（读文件 → 算数 → 下结论），用 3 种范式各写一遍，记录步数 / token / 成功率，填一张对比表。

**验收标准**
- 能说出三种范式各自最容易翻车的场景
- 能画出 Plan-and-Solve 的 state 结构
- 给一个新任务能在 30 秒内做出选型并说明理由

---

### 阶段 5｜工具工程化：自定义工具、多工具编排、安全边界

**知识点**
- 工具设计：命名、描述、参数粒度（一个工具只做一件事）
- 错误契约：返回可读错误而不是抛异常；`content_and_artifact`
- 安全：路径沙箱、命令白名单、超时、只读约束
- 工具太多怎么办：分组路由、子 agent、动态工具选择
- 工具内读取 state（`ToolRuntime`）

**实战小任务**：科研助手工具包 v1——`calculator` / `read_file`（沙箱） / `list_dir` / 安全表达式求值 / mock 文献检索；统一错误返回；写一组越权测试。

**验收标准**
- 修改工具描述能明显改变模型的选择
- 越权路径被拒绝并给出清晰提示
- 单个工具失败不影响其他工具
- 能说清"工具描述写得好"比"模型换得更强"更有效

---

### 阶段 6｜流式输出、可观测性、错误重试与降级

**知识点**
- `stream_mode`：`messages` / `updates` / `values` / `custom` 的区别；`astream_events` 何时用
- token 流 + 工具调用事件的正确呈现（避免重复打印）
- 重试：模型层 `with_retry`、工具层 `ToolRetryMiddleware`、全局 `tenacity`，指数退避
- 降级：fallback 模型、超时、`ModelCallLimit`、异常分类处理
- 日志与追踪：结构化日志、LangSmith（可选）

**实战小任务**：终端打字机效果 + 工具调用可视化；加一个"故障注入"开关（模拟 429 / 超时 / 工具异常），验证重试与降级链路。

**验收标准**
- 流式输出不重不漏，工具调用有明确提示
- 注入 429 后能自动恢复，用户只看到一句"稍等，重试中"
- 超过调用上限时有可读报错，而不是堆栈
- 能说清哪些错误该重试、哪些重试也没用

---

### 阶段 7｜落地项目：本地知识库问答 Agent

**知识点**
- RAG 最小闭环：加载 → 切分 → embedding → 向量库 → 检索
- 把检索做成工具 vs 固定链路（Agentic RAG 的取舍）
- 引用来源与"我不知道"：让答案可核查
- 评估：10~20 条问题集 + 断言 + 回归
- 工程结构：`config / tools / graph / cli / tests`

**实战小任务（分 3 次交付）**
1. 检索工具可独立测试（不接模型，先看召回对不对）
2. 接入 Agent，能自己决定检索几次、是否要再查
3. 流式 CLI + 测试集跑通 + 引用展示

**验收标准**
- 10 条测试问题中 ≥8 条答案有据可查且带来源
- 知识库外的问题明确说"资料里没有"
- 一条命令启动，README 能照着跑通

---

## 五、每轮的教学格式

每进入一个阶段，我会按这个固定结构给你：

1. **一句比喻**：这个组件在生活中对应什么
2. **知识点**：3~6 条，每条配最小代码片段
3. **完整示例**：单文件、可直接运行、逐行中文注释
4. **运行说明**：依赖命令、执行命令、预期输出
5. **原理拆解**：数据在内部怎么流动
6. **坑点清单**：常见报错 → 原因 → 解决
7. **思考题 + 验收 checklist**
8. 然后停下来问你：跑通了吗？要改哪里？进下一阶段？

**不做的事**：不一上来给大项目；不贴无法运行的伪代码；不教已废弃 API。

---

## 六、需要注意的两个前置条件

1. **模型接入**：你需要至少一个可用的模型来源（OpenAI / DeepSeek / 中转站 / 本地 Ollama），阶段 0 会用 `.env` 封装好，之后切换只改环境变量。
2. **Python 版本**：当前 `.venv` 是 3.14.3。如果安装依赖时出现"找不到 wheel / 需要编译"的报错，建议改用 3.12 重建虚拟环境——这是目前最省事的组合。
