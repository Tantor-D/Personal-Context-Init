# 个人信息文件夹

用 Markdown 与 JSON 保存个人上下文，AI 根据项目规则维护，文件可由通用工具读取。Obsidian 是可选阅读界面。无需安装初始化 Skill 即可继续使用本文件夹。

## 入口与管理文件

| 文件 | 用途 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | AI 读取入口与关键约束 |
| [CLAUDE.md](CLAUDE.md) | 单行引入 AGENTS.md |
| [POLICY.md](POLICY.md) | 统一维护规则 |
| [.gitignore](.gitignore) | 本地配置与临时文件忽略规则 |
| [.personal-context.json](.personal-context.json) | 规范版本、模板基线及升级元数据 |

## 按需建立主题

- `stable/`：稳定背景、约束，或结构化主题的说明入口。
- `mutable/`：当前状态、近期偏好、临时意图，覆盖更新。
- `history/`：需要长期保留的主题事件与纠错记录，使用 JSON。

这些目录仅在有授权内容时创建，不预填个人事实。新增文件需在本文件管理块之外的“主题文件目录”登记可点击的相对链接、内容简介及历史保留方式。历史 JSON 必须对应 stable/ 的主题说明入口。

## 使用

让 AI 先读取 AGENTS.md，再描述需要查询或更新的信息。可以直接编辑文件；普通 Markdown 采用标准链接，公式采用美元符号定界。规则要求的维护时间使用实际时钟。

Git 可保留全部版本；GitHub 同步是可选操作，需要另行配置。允许版本留存不等于已经启用自动提交或公开发布。
