"""
阶段 1 · 工具集：三个"最小可用"的工具

每个工具都由三部分构成，缺一不可：
    1) 函数名        —— 模型看到的工具名（要短、要能猜出用途）
    2) docstring     —— 模型看到的工具说明（写得含糊，模型就不会用）
    3) 参数类型标注  —— 自动生成 JSON Schema（模型据此决定传什么参数）

本文件的工具在阶段 5 会被扩展成完整的"科研助手工具包"。
"""

from __future__ import annotations

import ast
import operator
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool

# 所有文件类工具都只能在这个目录里活动（阶段 5 会讲为什么必须做这件事）
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 工具 1：安全计算器
# ---------------------------------------------------------------------------
# 注意：绝对不要用 eval()。模型可能生成 __import__("os").system("...")，
# 那就是一个远程代码执行漏洞。下面用 AST 白名单只放行四则运算。
_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node: ast.AST) -> float:
    """递归求值，只认识"数字"和"四则运算"两种东西。"""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        op = _ALLOWED_BINOPS.get(type(node.op))
        if op is None:
            raise ValueError("只支持 + - * / // % ** 这几种运算")
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 10:
            raise ValueError("指数太大了，可能算很久，请拆成几步")
        return op(left, right)
    if isinstance(node, ast.UnaryOp):
        op = _ALLOWED_UNARYOPS.get(type(node.op))
        if op is None:
            raise ValueError("不支持这种一元运算")
        return op(_eval_node(node.operand))
    raise ValueError(f"表达式里有不支持的写法：{ast.dump(node)[:60]}")


@tool
def calculator(expression: str) -> str:
    """计算数学表达式并返回结果。

    支持 + - * / // % ** 和括号，只接受数字，不能有变量或函数调用。
    示例：'23*47'、'(120-30)/3'、'2**10'

    Args:
        expression: 要计算的数学表达式，例如 "23*47"
    """
    try:
        result = _eval_node(ast.parse(expression, mode="eval"))
    except SyntaxError:
        return f"计算失败：表达式语法不对 -> {expression}"
    except ZeroDivisionError:
        return "计算失败：除数不能为 0"
    except ValueError as exc:
        return f"计算失败：{exc}"
    # 整数结果不要显示成 1081.0
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return f"{expression} = {result}"


# ---------------------------------------------------------------------------
# 工具 2：当前时间（零参数工具）
# ---------------------------------------------------------------------------
@tool
def get_current_time() -> str:
    """查询当前的日期和时间（本地时区）。

    当用户问"现在几点""今天几号"，或者任务需要时间基准时调用本工具。
    """
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S") + f"（{['周一','周二','周三','周四','周五','周六','周日'][now.weekday()]}）"


# ---------------------------------------------------------------------------
# 工具 3：数文件行数（带路径沙箱）
# ---------------------------------------------------------------------------
@tool
def count_lines(file_path: str) -> str:
    """统计项目里某个文本文件的行数。

    只能读取项目根目录内的文件，路径相对于项目根目录。

    Args:
        file_path: 相对路径，例如 "ROADMAP.md" 或 "stage0/01_messages_and_chain.py"
    """
    # resolve() 会把 ".." 和符号链接都展开，得到真实路径
    target = (PROJECT_ROOT / file_path).resolve()

    # 沙箱检查：真实路径必须仍在项目根目录内，否则 ../.. 就能读到整块硬盘
    if PROJECT_ROOT not in target.parents and target != PROJECT_ROOT:
        return f"拒绝访问：{file_path} 不在项目目录内"
    if not target.exists():
        return f"文件不存在：{file_path}"
    if target.is_dir():
        return f"{file_path} 是一个目录，不是文件，请给出具体文件名"

    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return f"{file_path} 不是文本文件（可能是二进制），无法统计行数"
    return f"{file_path} 共 {len(lines)} 行，{len(target.read_bytes())} 字节"


# 统一导出，方便示例里一键引用
ALL_TOOLS = [calculator, get_current_time, count_lines]
