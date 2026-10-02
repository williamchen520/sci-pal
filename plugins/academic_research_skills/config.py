"""
Academic Research Skills Plugin 配置
====================================
"""

import os
from dataclasses import dataclass


@dataclass
class PluginConfig:
    """插件配置"""

    # DeepSeek API 配置
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    # 插件设置
    enabled: bool = True
    max_tokens: int = 4096
    temperature: float = 0.7

    # 写作风格
    writing_style: str = "academic"  # academic / casual / formal


# 全局配置实例
config = PluginConfig()
