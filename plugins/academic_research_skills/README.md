# Academic Research Skills Plugin

学术写作插件，基于 [academic-research-skills](https://github.com/Imbad0202/academic-research-skills) 开源项目，直接使用 DeepSeek API。

## 功能

- **写论文**：完整的学术论文写作（IMRaD 结构）
- **写摘要**：中英文摘要写作
- **写文献综述**：文献综述写作
- **检查引用**：引用检查
- **格式化引用**：APA / MLA / Chicago / IEEE / Vancouver 格式

## 安装

1. 确保你的环境里有 DeepSeek API key
2. 设置环境变量：

```bash
export DEEPSEEK_API_KEY="your-api-key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com/v1"
export DEEPSEEK_MODEL="deepseek-chat"
```

## 使用

### 1. 作为 Python 模块

```python
from plugins.academic_research_skills import AcademicResearchSkills

# 初始化插件
plugin = AcademicResearchSkills()

# 写摘要
abstract = plugin.write_abstract(
    title="STAT1 in interferon signaling",
    content="STAT1 is a key transcription factor in interferon signaling.",
    language="english"
)
print(abstract)

# 写文献综述
review = plugin.write_literature_review(
    topic="JAK-STAT signaling in cancer",
    papers=["Paper 1", "Paper 2", "Paper 3"]
)
print(review)
```

### 2. 测试插件

```bash
cd plugins/academic_research_skills
python test_plugin.py
```

## 配置

配置文件在 `config.py` 里，你可以修改：

- `deepseek_api_key`：DeepSeek API key
- `deepseek_base_url`：DeepSeek API endpoint
- `deepseek_model`：模型名称
- `max_tokens`：最大 token 数
- `temperature`：温度
- `writing_style`：写作风格

## 来源

这个插件基于 [academic-research-skills](https://github.com/Imbad0202/academic-research-skills) 开源项目，主要提取了它的提示词模板，然后改成直接调用 DeepSeek API。
