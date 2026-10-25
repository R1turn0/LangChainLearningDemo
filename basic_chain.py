"""LangChain 基础 Demo：使用 LCEL 构建一个简单的链"""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()


def main():
    # 1. 初始化模型（兼容 OpenAI 接口的服务均可，通过环境变量配置）
    llm = ChatOpenAI(
        model=os.getenv("MODEL_NAME", "gpt-4o-mini"),
        temperature=0.7,
    )

    # 2. 定义提示词模板
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "你是一个友好的 AI 助教，用简洁易懂的中文回答问题。"),
            ("human", "{question}"),
        ]
    )

    # 3. 使用 LCEL（| 运算符）将 prompt -> llm -> parser 串联成链
    chain = prompt | llm | StrOutputParser()

    # 4. 调用链
    question = "什么是 LangChain 的 LCEL？请用一句话解释。"
    print(f"问题：{question}\n")
    answer = chain.invoke({"question": question})
    print(f"回答：{answer}")


if __name__ == "__main__":
    main()
