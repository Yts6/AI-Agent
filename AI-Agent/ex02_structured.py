"""示例 2：结构化输出（让模型返回 JSON）。

这是做 Agent 的基础能力——你需要模型稳定地返回可解析的数据。

演示要点：
- 用 JSON 模式约束输出
- Pydantic 校验返回结果
- 失败重试与降级

运行：python ex02_structured.py
"""

import json

from pydantic import BaseModel, Field, ValidationError

from config import get_client

EXTRACT_PROMPT = """你是一个信息抽取助手。从用户提供的文本中抽取信息，只返回 JSON，不要任何解释。

JSON 格式：
{
  "name": "姓名",
  "skills": ["技能1", "技能2"],
  "years": 工作年限数字,
  "level": "初级/中级/高级"
}

如果某个字段文中没有提到，name 填 "未知"，skills 填 []，years 填 0，level 填 "未知"。"""


class Resume(BaseModel):
    """简历结构化模型。"""

    name: str = Field(default="未知", description="姓名")
    skills: list[str] = Field(default_factory=list, description="技能列表")
    years: int = Field(default=0, ge=0, le=50, description="工作年限")
    level: str = Field(default="未知", description="级别")


def extract(text: str) -> Resume:
    """从文本抽取简历信息，返回校验后的对象。"""
    client, model, _ = get_client()

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": text},
        ],
        response_format={"type": "json_object"},  # 强制 JSON
        temperature=0,  # 抽取任务用最低温度
    )
    raw = resp.choices[0].message.content

    try:
        return Resume(**json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as e:
        print(f"  解析失败，原始返回：{raw[:200]}")
        print(f"  错误：{e}")
        return Resume()


def main() -> None:
    samples = [
        "张三，本科毕业，有 3 年 Python 后端开发经验，熟悉 Django、MySQL、Redis，"
        "最近在做大模型应用，用过 LangChain 和 RAG，算中级工程师吧。",
        "李四，应届生，会一点 Python 和 SQL。",
        "王五，10 年经验，架构师，精通 Java、Go、Kubernetes，带过 20 人团队。",
    ]

    for i, text in enumerate(samples, 1):
        print(f"=== 样本 {i} ===")
        print(f"原文：{text}")
        resume = extract(text)
        print(f"解析：name={resume.name!r} skills={resume.skills} "
              f"years={resume.years} level={resume.level!r}")
        print()


if __name__ == "__main__":
    main()
