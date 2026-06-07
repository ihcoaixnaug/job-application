# Offer捕手 — Claude 协作规范

## 项目简介
AI 求职全链路助手，Streamlit 单文件前端（`streamlit_app.py`）+ FastAPI 后端 + Claude API。

## 品牌主题色（必须遵守，禁止使用蓝色或其他颜色替代）

| 用途 | 色值 | 说明 |
|------|------|------|
| 背景色 | `#efece8` | 温暖米白，页面底色 |
| 深色文字 / 深色组件 | `#272937` | 深蓝黑，标题、深色按钮、暗色 hero |
| 品牌强调色 | `#d64635` | 红橙，CTA、active 状态、评分、徽章 |

**严禁**在任何新增或修改的 UI 中引入蓝色（如 `#2563eb`、`#3b82f6` 等）作为主色。
唯一例外：公司 logo（favicon）中原本包含的品牌蓝色。

## 导航框架
页面通过 URL query param `?page=XXX` 切换：
- `dashboard` — 仪表盘
- `jobs` — 岗位匹配
- `resume` — 简历诊断
- `progress` — 投递追踪
- `settings` — 设置

## iframe 导航规则（重要，已踩坑多次）

Streamlit 1.x 的 `st.components.v1.html()` 生成的 iframe sandbox **不含 `allow-top-navigation`**，
因此以下方法**全部失效**：
- `target="_top"` / `target="_parent"`
- `window.top.location.href = ...`
- `window.parent.location.href = ...`

**唯一可靠方案**：利用 `allow-same-origin`，在父文档创建 `<a>` 并 click()：
```javascript
function navTo(page) {
  var a = window.parent.document.createElement('a');
  a.href = '?page=' + page;
  window.parent.document.body.appendChild(a);
  a.click();
  setTimeout(function() { window.parent.document.body.removeChild(a); }, 200);
}
```
所有 `st.components.v1.html()` 内的跳转链接都应调用 `navTo()`，不要用 href 直接导航。

## 代码约定
- 所有 HTML 通过 `st.markdown(..., unsafe_allow_html=True)` 或 `st.components.v1.html()` 注入
- 样式写在 `st.markdown("""<style>...</style>""")` 块里
- 公共 CSS 在文件顶部统一定义（约第 120–300 行）
