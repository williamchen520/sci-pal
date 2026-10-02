"""
Writing Service
===============
学术写作服务，提供论文写作、摘要写作、文献综述等功能
"""

import os
from typing import Dict, Optional
from openai import OpenAI


class WritingService:
    """学术写作服务"""

    def __init__(self):
        """初始化写作服务"""
        # 加载 DeepSeek API 配置
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        )
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

        # 加载写作规范模板
        self.prompts_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "prompts"
        )
        self.writing_style = self._load_prompt("academic_writing_style.md")
        self.imrad_structure = self._load_prompt("imrad_paper_structure.md")
        self.abstract_template = self._load_prompt("abstract_writing_template.md")
        self.literature_review_template = self._load_prompt("literature_review_template.md")

    def _load_prompt(self, filename: str) -> str:
        """加载提示词模板"""
        filepath = os.path.join(self.prompts_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def _call_deepseek(self, system_prompt: str, user_prompt: str) -> str:
        """调用 DeepSeek API"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=4096,
                temperature=0.7,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error: {str(e)}"

    def write_paper(self, topic: str, evidence: str = "", paper_type: str = "journal") -> str:
        """
        写论文

        Args:
            topic: 论文主题
            evidence: 检索到的证据
            paper_type: 论文类型 (journal / conference / thesis)
        """
        system_prompt = f"""
        You are an expert academic paper writer. Write a high-quality academic paper.

        {self.writing_style}

        {self.imrad_structure}
        """

        user_prompt = f"""
        Write a {paper_type} paper on the topic: {topic}

        Evidence from our database:
        {evidence}

        Please write the paper following the IMRaD structure and writing rules.
        """

        return self._call_deepseek(system_prompt, user_prompt)

    def write_abstract(self, title: str, content: str, language: str = "english") -> str:
        """
        写摘要

        Args:
            title: 论文标题
            content: 论文内容
            language: 语言 (english / chinese)
        """
        system_prompt = f"""
        You are an expert academic abstract writer. Write a concise and informative abstract.

        {self.writing_style}

        {self.abstract_template}
        """

        user_prompt = f"""
        Title: {title}

        Content: {content}

        Write an abstract in {language} following the structure and rules.
        """

        return self._call_deepseek(system_prompt, user_prompt)

    def write_literature_review(self, topic: str, papers: list) -> str:
        """
        写文献综述

        Args:
            topic: 主题
            papers: 论文列表
        """
        system_prompt = f"""
        You are an expert literature review writer. Write a comprehensive literature review.

        {self.writing_style}

        {self.literature_review_template}
        """

        user_prompt = f"""
        Topic: {topic}

        Papers from our database:
        {papers}

        Write a literature review following the structure and rules.
        """

        return self._call_deepseek(system_prompt, user_prompt)

    def polish_text(self, text: str) -> str:
        """
        润色文本

        Args:
            text: 要润色的文本
        """
        system_prompt = f"""
        You are an expert academic editor. Polish the following text to make it more academic and clear.

        {self.writing_style}
        """

        user_prompt = f"""
        Polish the following text:

        {text}

        Improve the clarity, conciseness, and academic style.
        """

        return self._call_deepseek(system_prompt, user_prompt)
