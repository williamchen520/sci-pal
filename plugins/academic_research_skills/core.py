"""
Academic Research Skills Plugin 核心功能
========================================
基于 academic-research-skills 的提示词模板，直接调用 DeepSeek API
"""

import openai
from typing import Dict, Optional
from .config import config


class AcademicResearchSkills:
    """学术写作插件"""

    def __init__(self):
        """初始化插件"""
        self.client = openai.OpenAI(
            api_key=config.deepseek_api_key,
            base_url=config.deepseek_base_url,
        )
        self.model = config.deepseek_model

    def _call_deepseek(self, system_prompt: str, user_prompt: str) -> str:
        """调用 DeepSeek API"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error: {str(e)}"

    def write_paper(self, topic: str, paper_type: str = "journal") -> str:
        """
        写论文

        Args:
            topic: 论文主题
            paper_type: 论文类型 (journal / conference / thesis)
        """
        system_prompt = """
        You are an expert academic paper writer. Write a high-quality academic paper following IMRaD structure:
        - Introduction
        - Methods
        - Results
        - Discussion
        - Conclusion

        Use formal academic English. Include proper citations.
        """

        user_prompt = f"""
        Write a {paper_type} paper on the topic: {topic}

        Please provide:
        1. Title
        2. Abstract
        3. Introduction
        4. Methods
        5. Results
        6. Discussion
        7. Conclusion
        8. References
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
        system_prompt = """
        You are an expert academic abstract writer. Write a concise and informative abstract.
        Follow the structure: Background, Methods, Results, Conclusion.
        Keep it under 250 words.
        """

        user_prompt = f"""
        Title: {title}

        Content: {content}

        Write an abstract in {language}.
        """

        return self._call_deepseek(system_prompt, user_prompt)

    def write_literature_review(self, topic: str, papers: list) -> str:
        """
        写文献综述

        Args:
            topic: 主题
            papers: 论文列表
        """
        system_prompt = """
        You are an expert literature review writer. Write a comprehensive literature review.
        Follow the structure: Introduction, Main Themes, Discussion, Conclusion.
        """

        user_prompt = f"""
        Topic: {topic}

        Papers: {papers}

        Write a literature review.
        """

        return self._call_deepseek(system_prompt, user_prompt)

    def check_citations(self, text: str) -> str:
        """
        检查引用

        Args:
            text: 文本
        """
        system_prompt = """
        You are an expert citation checker. Check the citations in the text.
        Identify any issues with the citations.
        """

        user_prompt = f"""
        Text: {text}

        Check the citations.
        """

        return self._call_deepseek(system_prompt, user_prompt)

    def format_citations(self, citations: list, format: str = "APA") -> str:
        """
        格式化引用

        Args:
            citations: 引用列表
            format: 格式 (APA / MLA / Chicago / IEEE / Vancouver)
        """
        system_prompt = f"""
        You are an expert citation formatter. Format the citations in {format} style.
        """

        user_prompt = f"""
        Citations: {citations}

        Format them in {format} style.
        """

        return self._call_deepseek(system_prompt, user_prompt)
