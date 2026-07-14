---
name: wechat-publish
description: 当用户要求把 Markdown 文件发布到微信公众号时使用。自动处理封面图、图片上传、HTML 转换。
---

# 微信公众号发布 Skill

将本地 Markdown 文件发布到微信公众号的完整流程。

## 何时使用

- 用户说"把 xxx.md 发到公众号"
- 用户说"发布一篇文章到公众号"
- 用户说"新建一篇图文素材"

## 步骤

1. **确认文件存在**：用 `read` 或 `glob` 确认用户指定的 Markdown 文件存在。

2. **调用 `mcp__publish_markdown` 一站式发布**（推荐）：
   ```
   mcp__publish_markdown(
       file_path="./article.md",
       author="可选作者名",
       need_open_comment=1,   # 打开评论
       publish=false           # 是否直接发布
   )
   ```
   这个工具会自动完成：读取文件 → 上传本地图片 → 生成默认封面 → 转 HTML → 创建草稿。

3. **用户要求直接发布时**：先 `mcp__publish_markdown` 创建草稿，再用 `mcp__publish_draft` 提交发布。

4. **告诉用户结果**：返回草稿标题和 media_id，让用户去公众号后台预览。

## 注意事项

- 如果文件中有本地图片（`![alt](./images/foo.png)`），`publish_markdown` 会自动上传到微信 CDN。
- 封面图会自动生成绿色默认封面，无需用户准备。
- 默认只创建草稿不发布，用户确认后再发布。
- `publish_draft` 是异步提交，微信侧处理需几分钟。

## 相关工具

- `mcp__publish_markdown` — 一站式工具
- `mcp__list_drafts` — 查看所有草稿
- `mcp__get_draft` — 查看草稿详情
- `mcp__publish_draft` — 提交发布
