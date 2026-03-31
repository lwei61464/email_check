# Frontend Redesign Design Spec
**Date:** 2026-03-31  
**Status:** Approved

---

## Summary

将现有 Meridian Design System（深色默认、天蓝 accent、三字体）重构为 Stripe / Intercom 风格的主流商业 SaaS 设计，**浅色为默认主题，配套深色模式切换**。

**约束：** 保留 Bootstrap 5.3、228px 固定侧边栏、所有 JS 功能逻辑。仅重构视觉层。

---

## Design Tokens

### 字体

| 用途 | 字体 |
|------|------|
| UI 文本 / 标题 / 按钮 | DM Sans (400/500/600/700) |
| 数据 / 地址 / 时间戳 | DM Mono (400/500) |

Google Fonts:  
`https://fonts.googleapis.com/css2?family=DM+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=DM+Mono:wght@400;500&display=swap`

### CSS 变量

```css
:root {
  --font-ui:   'DM Sans', system-ui, sans-serif;
  --font-mono: 'DM Mono', 'Courier New', monospace;
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --transition-color: background 200ms ease, color 200ms ease,
                      border-color 200ms ease, box-shadow 200ms ease;
  --transition-fast: 150ms ease;
}

[data-theme="light"] {
  --color-bg:           #f8fafc;
  --color-bg-subtle:    #f1f5f9;
  --color-surface:      #ffffff;
  --color-border:       #e2e8f0;
  --color-border-strong:#cbd5e1;
  --color-text:         #0f172a;
  --color-text-2:       #475569;
  --color-text-3:       #94a3b8;
  --color-accent:       #0369a1;
  --color-accent-hover: #0284c7;
  --color-accent-subtle:#dbeafe;
  --color-accent-text:  #1d4ed8;
  --shadow-card:        0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
  --shadow-topbar:      0 1px 0 var(--color-border);
}

[data-theme="dark"] {
  --color-bg:           #0f1623;
  --color-bg-subtle:    #0a0f1a;
  --color-surface:      #111927;
  --color-border:       #1e2433;
  --color-border-strong:#2d3a4f;
  --color-text:         #e2e8f0;
  --color-text-2:       #94a3b8;
  --color-text-3:       #475569;
  --color-accent:       #3b82f6;
  --color-accent-hover: #60a5fa;
  --color-accent-subtle:rgba(59,130,246,0.12);
  --color-accent-text:  #60a5fa;
  --shadow-card:        0 1px 3px rgba(0,0,0,0.3);
  --shadow-topbar:      0 1px 0 var(--color-border);
}
```

### 分类徽标色

| 分类 | Light | Dark |
|------|-------|------|
| spam | bg #fef2f2 / text #dc2626 / border #fecaca | bg rgba(239,68,68,0.12) / text #f87171 |
| important | bg #eff6ff / text #1d4ed8 / border #bfdbfe | bg rgba(59,130,246,0.12) / text #60a5fa |
| transactional | bg #f0fdf4 / text #15803d / border #bbf7d0 | bg rgba(74,222,128,0.1) / text #4ade80 |
| newsletter | bg #fdf4ff / text #9333ea / border #e9d5ff | bg rgba(192,132,252,0.1) / text #c084fc |
| normal | bg #f8fafc / text #475569 / border #e2e8f0 | bg rgba(100,116,139,0.12) / text #94a3b8 |

---

## Component Specs

### 侧边栏
- 背景 `var(--color-surface)`，右边框 `1px solid var(--color-border)`
- Logo：24px 方形圆角色块（accent 色）+ 品牌名 DM Sans 700
- 导航项：`padding: 7px 10px`，`border-radius: var(--radius-md)`，margin 6px 水平
- Active：`background: var(--color-accent-subtle); color: var(--color-accent); font-weight: 600`
- Hover：`background: var(--color-bg-subtle)`

### 顶部栏
- 背景 `var(--color-surface)`，`box-shadow: var(--shadow-topbar)`
- 左：页面标题 (600) + `/` + 副标题 (`var(--color-text-3)`)
- 右：运行状态胶囊 + 主题 Toggle（36×20px 圆角滑块）

### 统计卡片
- `background: var(--color-surface); border: 1px solid var(--color-border); box-shadow: var(--shadow-card); border-radius: var(--radius-lg)`
- 主要指标 `.stat-card--accent`：`border-color: var(--color-accent-subtle)`
- 数字：1.8rem DM Sans 700，accent 卡用 `var(--color-accent)`

### 表格
- 表头：`background: var(--color-bg-subtle)`，0.65rem uppercase `var(--color-text-3)`
- 行分隔：`border-bottom: 1px solid var(--color-bg-subtle)`
- Hover：`background: var(--color-bg-subtle)`
- 邮件地址列：DM Mono 0.82rem

### 按钮
- Primary：`background: var(--color-accent); color: #fff`
- Secondary：`background: var(--color-bg-subtle); border: 1px solid var(--color-border)`
- Danger ghost：`color: #dc2626; border: 1px solid #fecaca`（dark 适配）
- Ghost：`color: var(--color-text-2); border: 1px solid var(--color-border)`

### 输入框
- `background: var(--color-surface); border: 1px solid var(--color-border)`
- Focus：`border-color: var(--color-accent); box-shadow: 0 0 0 3px var(--color-accent-subtle)`

---

## 主题逻辑

```javascript
// 浅色默认，作用于 document.body
const saved = localStorage.getItem('theme') || 'light';
document.body.setAttribute('data-theme', saved);

function toggleTheme() {
  const next = document.body.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
  document.body.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  updateChartColors();
}
```

---

## 动效

| 动效 | 属性 | 时长 |
|------|------|------|
| Staggered reveal | opacity 0→1, translateY 8px→0 | 300ms, delay: index×60ms |
| 主题切换 | background/color/border | 200ms |
| 行展开 | max-height + opacity | 220ms |
| Hover/Focus | background, border | 150ms |

---

## 文件修改清单

| 文件 | 操作 |
|------|------|
| `web/static/style.css` | 完整重写 |
| `web/templates/base.html` | 字体、主题 JS、toggle HTML、updateChartColors() |
| `web/templates/dashboard.html` | class 名适配 |
| `web/templates/emails.html` | class 名适配 |
| `web/templates/blacklist.html` | class 名适配 |
| `web/templates/rules.html` | class 名适配 |

---

## 验证方案

1. `uvicorn web.app:app --reload`，访问 `http://localhost:8000`
2. 逐页检查四个页面视觉效果
3. 切换主题：颜色平滑过渡，localStorage 保持
4. 刷新后主题保持（默认浅色）
5. Chart.js 颜色随主题更新
6. Bootstrap Modal 在双主题下样式正确
7. 移动端 768px 以下侧边栏响应式正常
