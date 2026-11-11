# 学习问答笔记 · stage0（消息对象、Prompt 模板、结构化输出）

> 记录学习 stage0 两课（`01_messages_and_chain.py`、`02_requirement_assistant.py`）过程中提出的问题与结论。
> 排错过程见 `troubleshooting_02_requirement_assistant.md`。

---

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

---

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

---

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

分工：**模板管"每轮把历史整齐地重新组装"，history 列管"记住"**。
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

---

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

---

## 附：贯穿全部问答的一条主线

```
模型真正吃的：消息列表（对象，角色藏在类型里）        ← Q1 Q2
结构要复用：  ChatPromptTemplate.from_messages 开模   ← Q3 Q4 Q5
记忆 = 每轮把完整历史重发：history 列表 + Placeholder ← Q6 Q7
名字只是约定：形参/实参，没有魔法                     ← Q8 Q9
链尾定类型：  with_structured_output 锁死输出结构      ← Q10 Q11 Q12
```
