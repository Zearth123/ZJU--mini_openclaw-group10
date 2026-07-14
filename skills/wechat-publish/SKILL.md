---
name: wechat-publish
description: 当用户要求把 Markdown 文件发布到微信公众号时使用。优先使用 gzh-design 生成精美排版 HTML，再通过 MCP 工具上传到公众号草稿箱。
---

# 微信公众号发布 Skill

将本地 Markdown 文件排版后发布到微信公众号的完整流程。

## 何时使用

- 用户说"把 xxx.md 发到公众号"
- 用户说"发布一篇文章到公众号"
- 用户说"新建一篇图文素材"
- 用户说"排版并发布到公众号"

## 步骤

### Step 1：确认文件存在

用 `read` 或 `glob` 确认用户指定的 Markdown 文件存在。

### Step 2：用 gzh-design 排版生成 HTML

先调用 **gzh-design Skill** 对 Markdown 文件进行排版，生成精美的公众号风格 HTML 文件。

- 根据文件内容选择合适的主题风格
- 输出 HTML 文件到项目根目录（当前工作目录）
- 记录生成的 HTML 文件路径

### Step 3：读取生成的 HTML 内容

用 `read` 工具读取 gzh-design 生成的 HTML 文件内容，获取完整的 `<section>...</section>` 正文片段。

### Step 4：调用 MCP 创建微信草稿

用 `mcp__create_draft` 工具，将 gzh-design 生成的 HTML 作为正文内容传入：

```
mcp__create_draft(
    title="文章标题",
    content="从 HTML 文件中读取的完整 section 内容",
    author="可选作者名",
    digest="可选摘要",
    need_open_comment=1,   # 打开评论
    only_fans_can_comment=0
)
```

**注意**：不要使用 `mcp__publish_markdown`（它自己转的 HTML 不如 gzh-design 精美），要用 `mcp__create_draft` 直接传入已排好版的 HTML。

### Step 5：可选 — 提交发布

如果用户要求直接发布，调用 `mcp__publish_draft(media_id="...")` 提交发布。

### Step 6：告诉用户结果

返回草稿标题和 media_id。如果需要用户去公众号后台预览确认，给出提示。

## 注意事项

- **排版优先**：必须先调用 gzh-design Skill 生成排版 HTML，再通过 `mcp__create_draft` 传入。
- 文章中引用的本地图片（`![alt](./images/foo.png)`），gzh-design 生成的 HTML 中会保留这些引用。发布前先确认图片路径是否可访问，或先用 `mcp__upload_image` 上传到微信 CDN 后替换 HTML 中的图片 URL。
- 封面图：如不指定则自动生成默认绿色封面。
- 默认只创建草稿不发布，用户确认后再发布。
- `publish_draft` 是异步提交，微信侧处理需几分钟。

## 相关工具

- `mcp__create_draft` — 直接用 HTML 正文创建草稿（推荐）
- `mcp__upload_image` — 上传本地图片到微信 CDN
- `mcp__publish_draft` — 提交发布
- `mcp__list_drafts` — 查看所有草稿
- `mcp__get_draft` — 查看草稿详情
- `mcp__publish_markdown` — 直接传 markdown（内置转 HTML，排版不如 gzh-design）

## 相关 Skill

- `gzh-design` — 公众号排版引擎，生成精美 HTML（必须先调用）
