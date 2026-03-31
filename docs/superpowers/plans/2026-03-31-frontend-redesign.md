# Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 Meridian 深色设计系统替换为 Stripe/Intercom 风格的浅色优先 SaaS 视觉设计，保留全部功能逻辑，支持浅/深色双主题切换。

**Architecture:** 完整重写 `web/static/style.css`（新 CSS 变量系统 + 组件样式），修改 `web/templates/base.html`（字体、主题 JS、toggle 按钮），对各页模板做最小化修改（移除 inline style 覆盖、添加 accent-card class）。CSS 中保留旧变量名别名，确保未修改的 HTML inline styles 继续生效。

**Tech Stack:** Bootstrap 5.3、Chart.js 4.4、DM Sans + DM Mono (Google Fonts)、纯 CSS 变量主题系统、Jinja2 模板

---

## File Map

| 文件 | 操作 | 说明 |
|------|------|------|
| `web/static/style.css` | 完整重写 | 新 token 系统 + 所有组件样式 + 旧变量别名 |
| `web/templates/base.html` | 修改 3 处 | 字体 URL、主题 JS（浅色默认）、toggle 按钮 HTML |
| `web/templates/dashboard.html` | 修改 1 处 | 第二张 stat-card 添加 `accent-card` class |
| `web/templates/emails.html` | 修改 1 处 | 移除 panel-card 上的 `border-radius` inline style |
| `web/templates/blacklist.html` | 不修改 | CSS 别名已覆盖 |
| `web/templates/rules.html` | 不修改 | CSS 别名已覆盖 |

---

## Task 1: 完整重写 style.css

**Files:**
- Modify: `web/static/style.css` （完整替换全部 927 行）

- [ ] **Step 1: 用以下内容完整替换 `web/static/style.css`**

```css
/* ============================================================
   Email Sorter UI — 2026 Redesign
   Light-first SaaS theme (Stripe/Intercom style)
   Fonts: DM Sans (UI) + DM Mono (data)
   ============================================================ */

/* ===== Layout Constants ===== */
:root {
  --sidebar-w: 228px;
  --topbar-h:  60px;
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --font-ui:   'DM Sans', system-ui, sans-serif;
  --font-mono: 'DM Mono', 'Consolas', monospace;
  --transition-color: background-color 200ms ease, color 200ms ease,
                      border-color 200ms ease, box-shadow 200ms ease;
  --transition-fast:  150ms ease;
}

/* ===== Light Theme (default) ===== */
:root,
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
  --shadow-topbar:      0 1px 0 #e2e8f0;
  --shadow-sidebar:     1px 0 0 #e2e8f0;
  --success:            #16a34a;
  --success-bg:         #f0fdf4;
  --success-border:     #bbf7d0;
  --danger:             #dc2626;
  --danger-bg:          #fef2f2;
  --danger-border:      #fecaca;
  --warning:            #d97706;
  --warning-bg:         #fffbeb;
  --warning-border:     #fde68a;
  --close-filter:       invert(0.3);
  /* ── backward-compat aliases (for existing inline styles) ── */
  --bg-base:       var(--color-bg);
  --bg-surface:    var(--color-surface);
  --bg-elevated:   var(--color-surface);
  --bg-overlay:    var(--color-surface);
  --bg-hover:      var(--color-bg-subtle);
  --border-subtle: var(--color-border);
  --border-mid:    var(--color-border);
  --border-strong: var(--color-border-strong);
  --accent:        var(--color-accent);
  --accent-dim:    var(--color-accent-subtle);
  --accent-hover:  var(--color-accent-hover);
  --text-primary:  var(--color-text);
  --text-secondary:var(--color-text-2);
  --text-muted:    var(--color-text-3);
  --muted:         var(--color-text-3);
  --font-body:     var(--font-ui);
  --font-display:  var(--font-ui);
  --shadow-sm:     var(--shadow-card);
  --shadow-md:     0 4px 16px rgba(0,0,0,0.10);
  --shadow-lg:     0 12px 40px rgba(0,0,0,0.14);
}

/* ===== Dark Theme ===== */
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
  --shadow-topbar:      0 1px 0 #1e2433;
  --shadow-sidebar:     1px 0 0 #1e2433;
  --success:            #4ade80;
  --success-bg:         rgba(74,222,128,0.10);
  --success-border:     rgba(74,222,128,0.20);
  --danger:             #f87171;
  --danger-bg:          rgba(239,68,68,0.12);
  --danger-border:      rgba(239,68,68,0.20);
  --warning:            #fbbf24;
  --warning-bg:         rgba(251,191,36,0.10);
  --warning-border:     rgba(251,191,36,0.20);
  --close-filter:       invert(0.6);
  /* ── backward-compat aliases ── */
  --bg-base:       var(--color-bg);
  --bg-surface:    var(--color-surface);
  --bg-elevated:   var(--color-surface);
  --bg-overlay:    var(--color-surface);
  --bg-hover:      var(--color-bg-subtle);
  --border-subtle: var(--color-border);
  --border-mid:    var(--color-border);
  --border-strong: var(--color-border-strong);
  --accent:        var(--color-accent);
  --accent-dim:    var(--color-accent-subtle);
  --accent-hover:  var(--color-accent-hover);
  --text-primary:  var(--color-text);
  --text-secondary:var(--color-text-2);
  --text-muted:    var(--color-text-3);
  --muted:         var(--color-text-3);
  --font-body:     var(--font-ui);
  --font-display:  var(--font-ui);
  --shadow-sm:     var(--shadow-card);
  --shadow-md:     0 4px 16px rgba(0,0,0,0.40);
  --shadow-lg:     0 12px 40px rgba(0,0,0,0.55);
}

/* ===== Bootstrap Overrides ===== */
body {
  --bs-body-bg:      var(--color-bg);
  --bs-body-color:   var(--color-text);
  --bs-border-color: var(--color-border);
  font-family: var(--font-ui);
  background: var(--color-bg);
  color: var(--color-text);
  transition: var(--transition-color);
}

/* ===== Scrollbar ===== */
::-webkit-scrollbar              { width: 5px; height: 5px; }
::-webkit-scrollbar-track        { background: transparent; }
::-webkit-scrollbar-thumb        { background: var(--color-border-strong); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover  { background: var(--color-text-3); }

/* ===== Typography ===== */
h1, h2, h3, h4, h5, h6 {
  font-family: var(--font-ui);
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.02em;
}
.section-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.02em;
  margin-bottom: 2px;
}
.section-subtitle {
  font-size: 0.84rem;
  color: var(--color-text-3);
}
.address-code, code {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 1px 5px;
  color: var(--color-text);
}

/* ===== Layout: Brand Header ===== */
.sidebar-brand {
  position: fixed;
  top: 0; left: 0;
  width: var(--sidebar-w);
  height: var(--topbar-h);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 18px;
  background: var(--color-surface);
  box-shadow: var(--shadow-sidebar), 0 1px 0 var(--color-border);
  text-decoration: none;
  z-index: 200;
  transition: var(--transition-color);
}
.brand-icon {
  font-size: 1.1rem;
  color: var(--color-accent);
  flex-shrink: 0;
}
.brand-text {
  font-size: 0.88rem;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.01em;
}
.brand-tag {
  font-size: 0.6rem;
  font-weight: 600;
  color: var(--color-text-3);
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
  padding: 1px 5px;
  border-radius: 4px;
  font-family: var(--font-mono);
}

/* ===== Layout: Sidebar ===== */
.sidebar {
  position: fixed;
  top: var(--topbar-h);
  left: 0;
  width: var(--sidebar-w);
  height: calc(100vh - var(--topbar-h));
  background: var(--color-surface);
  box-shadow: var(--shadow-sidebar);
  display: flex;
  flex-direction: column;
  padding: 12px 0;
  overflow-y: auto;
  z-index: 100;
  transition: var(--transition-color);
}
.sidebar-nav-section {
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--color-text-3);
  padding: 6px 18px 4px;
}
.sidebar .nav-link {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  margin: 1px 8px;
  border-radius: var(--radius-md);
  font-size: 0.84rem;
  font-weight: 500;
  color: var(--color-text-2);
  text-decoration: none;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.sidebar .nav-link i { font-size: 0.95rem; flex-shrink: 0; }
.sidebar .nav-link .nav-dot { display: none; }
.sidebar .nav-link:hover {
  background: var(--color-bg-subtle);
  color: var(--color-text);
}
.sidebar .nav-link.active {
  background: var(--color-accent-subtle);
  color: var(--color-accent-text);
  font-weight: 600;
}
[data-theme="dark"] .sidebar .nav-link.active {
  color: var(--color-accent);
}
.sidebar-footer {
  margin-top: auto;
  padding: 12px 18px;
  border-top: 1px solid var(--color-border);
  font-size: 0.7rem;
  color: var(--color-text-3);
  font-family: var(--font-mono);
}

/* ===== Layout: Topbar ===== */
.topbar {
  position: fixed;
  top: 0;
  left: var(--sidebar-w);
  right: 0;
  height: var(--topbar-h);
  display: flex;
  align-items: center;
  padding: 0 24px;
  gap: 12px;
  background: var(--color-surface);
  box-shadow: var(--shadow-topbar);
  z-index: 100;
  transition: var(--transition-color);
}
.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--success);
  background: var(--success-bg);
  border: 1px solid var(--success-border);
  padding: 4px 10px;
  border-radius: 20px;
  white-space: nowrap;
  transition: var(--transition-color);
}
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success);
  flex-shrink: 0;
}
[data-theme="dark"] .status-dot {
  box-shadow: 0 0 6px var(--success);
}

/* Theme Toggle — CSS-driven sliding switch */
.theme-toggle {
  position: relative;
  width: 38px;
  height: 22px;
  border-radius: 11px;
  border: none;
  cursor: pointer;
  padding: 0;
  flex-shrink: 0;
  background: var(--color-border-strong);
  transition: background 200ms ease;
}
[data-theme="dark"] .theme-toggle { background: var(--color-accent); }
.theme-toggle::after {
  content: '';
  position: absolute;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  top: 3px;
  left: 3px;
  transition: left 200ms ease, box-shadow 200ms ease;
  box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}
[data-theme="dark"] .theme-toggle::after { left: 19px; }
.theme-toggle i { display: none; }  /* icon hidden; visual is ::after pseudo-element */

/* ===== Layout: Main Content ===== */
.main-content {
  margin-left: var(--sidebar-w);
  padding-top: calc(var(--topbar-h) + 24px);
  padding-bottom: 40px;
  padding-left: 24px;
  padding-right: 24px;
  min-height: 100vh;
  background: var(--color-bg);
  transition: background var(--transition-color);
}

/* ===== Stat Cards ===== */
.stat-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
  box-shadow: var(--shadow-card);
  transition: var(--transition-color);
  height: 100%;
}
.stat-card.accent-card {
  border-color: var(--color-accent-subtle);
}
[data-theme="dark"] .stat-card.accent-card {
  border-color: rgba(59,130,246,0.25);
}
.stat-label {
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--color-text-3);
  margin-bottom: 4px;
}
.stat-number {
  font-size: 1.9rem;
  font-weight: 700;
  letter-spacing: -0.04em;
  line-height: 1;
  color: var(--color-text);
  margin-bottom: 4px;
}
.accent-card .stat-number,
.stat-number--accent { color: var(--color-accent); }
/* Preserve colored number variants from existing HTML */
.stat-number--green { color: var(--success); }
.stat-number--red   { color: var(--danger); }
.stat-number--amber { color: var(--color-accent); }
.stat-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
  margin-bottom: 10px;
}

/* ===== Panel Cards ===== */
.panel-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  overflow: hidden;
  transition: var(--transition-color);
}
.panel-header {
  padding: 14px 18px;
  border-bottom: 1px solid var(--color-border);
  font-size: 0.84rem;
  font-weight: 600;
  color: var(--color-text);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.panel-body { padding: 18px; }

/* ===== Filter Bar ===== */
.filter-bar {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px 18px;
  box-shadow: var(--shadow-card);
  transition: var(--transition-color);
}
.filter-bar label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-2);
  margin-bottom: 4px;
  display: block;
}

/* ===== Table ===== */
.table {
  --bs-table-bg: transparent;
  --bs-table-border-color: var(--color-border);
  color: var(--color-text);
  margin-bottom: 0;
}
.table thead th {
  background: var(--color-bg-subtle);
  border-bottom: 1px solid var(--color-border) !important;
  color: var(--color-text-3);
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding: 10px 14px;
  font-family: var(--font-ui);
  white-space: nowrap;
}
.table tbody td {
  padding: 11px 14px;
  border-bottom: 1px solid var(--color-bg-subtle);
  border-top: none;
  vertical-align: middle;
  font-size: 0.84rem;
  color: var(--color-text-2);
  transition: background var(--transition-fast);
}
[data-theme="dark"] .table tbody td { border-bottom-color: #1a2235; }
.table tbody tr:last-child td { border-bottom: none; }
.table tbody tr:hover td      { background: var(--color-bg-subtle); }
.table-sm thead th { padding: 8px 12px; }
.table-sm tbody td { padding: 9px 12px; }

/* ===== Category Badges ===== */
.badge-spam,
.badge-important,
.badge-transactional,
.badge-newsletter,
.badge-normal {
  display: inline-block;
  font-size: 0.7rem;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  white-space: nowrap;
}
/* Light */
.badge-spam          { background: #fef2f2; color: #dc2626; border-color: #fecaca; }
.badge-important     { background: #eff6ff; color: #1d4ed8; border-color: #bfdbfe; }
.badge-transactional { background: #f0fdf4; color: #15803d; border-color: #bbf7d0; }
.badge-newsletter    { background: #fdf4ff; color: #9333ea; border-color: #e9d5ff; }
.badge-normal        { background: #f8fafc; color: #475569; border-color: #e2e8f0; }
/* Dark */
[data-theme="dark"] .badge-spam          { background: rgba(239,68,68,0.12);   color: #f87171; border-color: rgba(239,68,68,0.2); }
[data-theme="dark"] .badge-important     { background: rgba(59,130,246,0.12);  color: #60a5fa; border-color: rgba(59,130,246,0.2); }
[data-theme="dark"] .badge-transactional { background: rgba(74,222,128,0.10);  color: #4ade80; border-color: rgba(74,222,128,0.2); }
[data-theme="dark"] .badge-newsletter    { background: rgba(192,132,252,0.10); color: #c084fc; border-color: rgba(192,132,252,0.2); }
[data-theme="dark"] .badge-normal        { background: rgba(100,116,139,0.12); color: #94a3b8; border-color: rgba(100,116,139,0.2); }

/* ===== Confidence Bar ===== */
.confidence-bar {
  height: 6px;
  background: var(--color-border);
  border-radius: 3px;
  overflow: hidden;
  min-width: 60px;
}
.confidence-fill {
  height: 100%;
  background: var(--color-accent);
  border-radius: 3px;
  transition: width 600ms ease;
}

/* ===== Buttons ===== */
.btn-amber,
.btn-primary-custom {
  background: var(--color-accent);
  color: #fff !important;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  padding: 8px 16px;
  font-size: 0.84rem;
  font-weight: 600;
  font-family: var(--font-ui);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  text-decoration: none;
  transition: background var(--transition-fast);
  line-height: 1.5;
}
.btn-amber:hover { background: var(--color-accent-hover); color: #fff !important; }
.btn-ghost {
  background: transparent;
  color: var(--color-text-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 7px 14px;
  font-size: 0.82rem;
  font-weight: 500;
  font-family: var(--font-ui);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.btn-ghost:hover { background: var(--color-bg-subtle); color: var(--color-text); }
.btn-danger-ghost {
  background: transparent;
  color: var(--danger);
  border: 1px solid var(--danger-border);
  border-radius: var(--radius-md);
  padding: 6px 12px;
  font-size: 0.8rem;
  font-weight: 600;
  font-family: var(--font-ui);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.btn-danger-ghost:hover { background: var(--danger-bg); }
/* Bootstrap btn overrides */
.btn-sm { padding: 6px 12px; font-size: 0.8rem; }

/* ===== Form Controls ===== */
.form-control,
.form-select {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-family: var(--font-ui);
  font-size: 0.84rem;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast),
              background var(--transition-color);
}
.form-control:focus,
.form-select:focus {
  background: var(--color-surface);
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-subtle);
  color: var(--color-text);
  outline: none;
}
.form-control::placeholder { color: var(--color-text-3); }
.form-control-sm, .form-select-sm { font-size: 0.82rem; padding: 6px 10px; }
.form-label {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--color-text-2);
}

/* ===== Pill Tabs ===== */
.pill-tabs {
  display: flex;
  gap: 0;
  background: var(--color-bg-subtle);
  border-radius: var(--radius-lg);
  padding: 3px;
  border: 1px solid var(--color-border);
  width: fit-content;
  transition: var(--transition-color);
}
.pill-tab {
  padding: 7px 20px;
  border-radius: 9px;
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--color-text-2);
  cursor: pointer;
  border: none;
  background: transparent;
  font-family: var(--font-ui);
  transition: background var(--transition-fast), color var(--transition-fast),
              box-shadow var(--transition-fast);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.pill-tab.active {
  background: var(--color-surface);
  color: var(--color-text);
  font-weight: 600;
  box-shadow: var(--shadow-card);
}

/* ===== Pager ===== */
.pager {
  display: flex;
  align-items: center;
  gap: 4px;
}
.pager-btn {
  min-width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--color-text-2);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast),
              border-color var(--transition-fast);
  font-family: var(--font-ui);
  padding: 0 8px;
}
.pager-btn:hover,
.pager-btn.active {
  background: var(--color-accent-subtle);
  color: var(--color-accent-text);
  border-color: transparent;
}
[data-theme="dark"] .pager-btn:hover,
[data-theme="dark"] .pager-btn.active { color: var(--color-accent); }

/* ===== Detail Row ===== */
.detail-row > td {
  padding: 0 !important;
  border-top: none !important;
}
.detail-content {
  padding: 14px 18px;
  background: var(--color-bg-subtle);
  font-size: 0.82rem;
  color: var(--color-text-2);
  border-top: 1px solid var(--color-border);
  transition: var(--transition-color);
}

/* ===== Toast ===== */
.toast-container {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 9999;
}
#app-toast {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  color: var(--color-text);
  min-width: 280px;
  transition: var(--transition-color);
}
.toast--success { border-left: 3px solid var(--success); }
.toast--error   { border-left: 3px solid var(--danger); }
.toast--warning { border-left: 3px solid var(--warning); }
.toast-body {
  font-size: 0.84rem;
  padding: 12px 14px;
  font-family: var(--font-ui);
}

/* ===== Bootstrap Modal ===== */
.modal-content {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}
.modal-header {
  border-bottom: 1px solid var(--color-border);
  padding: 16px 20px;
}
.modal-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--color-text);
}
.modal-footer {
  border-top: 1px solid var(--color-border);
  padding: 12px 20px;
}
.modal-body { padding: 18px 20px; color: var(--color-text-2); font-size: 0.88rem; }
.btn-close { filter: var(--close-filter); }

/* ===== Scan / History Panel ===== */
.scan-panel {
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  font-size: 0.82rem;
  color: var(--color-text-2);
  transition: var(--transition-color);
}
.scan-progress { margin-top: 8px; }

/* ===== Staggered Reveal Animation ===== */
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.anim-card {
  opacity: 0;
  animation: fadeInUp 300ms ease forwards;
}

/* ===== Responsive ===== */
@media (max-width: 768px) {
  .sidebar, .sidebar-brand { display: none; }
  .topbar     { left: 0; }
  .main-content { margin-left: 0; padding-left: 16px; padding-right: 16px; }
}
```

- [ ] **Step 2: 确认文件已保存，继续下一个 Task**

---

## Task 2: 修改 base.html

**Files:**
- Modify: `web/templates/base.html`

需要做 4 处修改：
1. `<html>` 标签的 `data-theme` 从 `dark` 改为 `light`
2. Google Fonts URL 替换（Fraunces+Figtree+JetBrains → DM Sans+DM Mono）
3. 主题 JS 默认值从 `'dark'` 改为 `'light'`，并添加 `updateChartColors()` 和 staggered reveal
4. Chart.js 字体从 Figtree 改为 DM Sans

- [ ] **Step 1: 修改 `web/templates/base.html` 第 2 行**

将：
```html
<html lang="zh-CN" data-theme="dark">
```
改为：
```html
<html lang="zh-CN" data-theme="light">
```

- [ ] **Step 2: 修改第 10 行 — 替换 Google Fonts URL**

将：
```html
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Figtree:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```
改为：
```html
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
```

- [ ] **Step 3: 修改第 7 行注释**

将：
```html
  <!-- Google Fonts: Fraunces (display) + Figtree (UI) + JetBrains Mono (data) -->
```
改为：
```html
  <!-- Google Fonts: DM Sans (UI) + DM Mono (data) -->
```

- [ ] **Step 4: 替换 base.html 中的全部 `<script>` 块（第 98-172 行）**

将第 98 行到第 172 行（从 `<script>` 到 `</script>`，不含 `{% block extra_scripts %}`）替换为：

```html
  <script>
    // ===== 主题管理（浅色默认）=====
    (function () {
      const saved = localStorage.getItem('theme') || 'light';
      document.documentElement.setAttribute('data-theme', saved);
    })();

    document.getElementById('theme-toggle-btn').addEventListener('click', function () {
      const html = document.documentElement;
      const cur  = html.getAttribute('data-theme') || 'light';
      const next = cur === 'light' ? 'dark' : 'light';
      html.setAttribute('data-theme', next);
      localStorage.setItem('theme', next);
      updateChartColors(next);
    });

    function updateChartColors(theme) {
      theme = theme || document.documentElement.getAttribute('data-theme') || 'light';
      if (typeof Chart === 'undefined') return;
      const textColor  = theme === 'dark' ? '#94a3b8' : '#94a3b8';
      const gridColor  = theme === 'dark' ? 'rgba(30,36,51,0.8)' : 'rgba(226,232,240,0.8)';
      Chart.defaults.color      = textColor;
      Chart.defaults.font.family = "'DM Sans', system-ui, sans-serif";
      Chart.defaults.borderColor = gridColor;
    }

    // ===== Toast 通知 =====
    function showToast(message, type = 'success') {
      const toast = document.getElementById('app-toast');
      const msg   = document.getElementById('toast-message');
      const icon  = document.getElementById('toast-icon');
      toast.classList.remove('toast--success', 'toast--error', 'toast--warning');
      const map = {
        success: ['toast--success', 'bi bi-check-circle-fill', 'var(--success)'],
        error:   ['toast--error',   'bi bi-x-circle-fill',     'var(--danger)'],
        warning: ['toast--warning', 'bi bi-exclamation-triangle-fill', 'var(--warning)'],
      };
      const [cls, iconCls, color] = map[type] || map.success;
      toast.classList.add(cls);
      icon.className  = iconCls;
      icon.style.color = color;
      msg.textContent = message;
      bootstrap.Toast.getOrCreateInstance(toast, { delay: 3000 }).show();
    }

    // ===== 数字滚动计数 =====
    function animateCounter(el, target, duration = 800) {
      if (!el) return;
      if (target === 0) { el.textContent = 0; return; }
      const start = performance.now();
      function step(now) {
        const p    = Math.min((now - start) / duration, 1);
        const ease = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.round(target * ease);
        if (p < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    }

    // ===== 加载最后处理时间 =====
    async function loadLastTime() {
      try {
        const res  = await fetch('/api/stats');
        const json = await res.json();
        const t    = json.data?.last_processed_at;
        document.getElementById('last-time-value').textContent = t || '暂无记录';
      } catch (_) {}
    }
    loadLastTime();

    // ===== Staggered Reveal =====
    document.addEventListener('DOMContentLoaded', function () {
      updateChartColors();
      const cards = document.querySelectorAll('.stat-card, .panel-card');
      cards.forEach(function (card, i) {
        card.classList.add('anim-card');
        card.style.animationDelay = (i * 60) + 'ms';
      });
    });

    // ===== Chart.js 全局配置 =====
    if (typeof Chart !== 'undefined') {
      updateChartColors();
    }
  </script>
```

- [ ] **Step 5: 确认文件保存完毕**

---

## Task 3: 修改 dashboard.html — 添加 accent-card

**Files:**
- Modify: `web/templates/dashboard.html:22-29`

将"今日处理"统计卡片（第 22-29 行）的 `stat-card` 添加 `accent-card` class，使其数字以 accent 蓝色显示，形成视觉主指标。

- [ ] **Step 1: 修改 `web/templates/dashboard.html`**

将：
```html
  <div class="col-6 col-xl-3">
    <div class="stat-card">
      <div class="stat-icon" style="background:rgba(16,185,129,0.12);color:var(--success)">
        <i class="bi bi-calendar-check-fill"></i>
      </div>
      <div class="stat-label">今日处理</div>
      <div class="stat-number stat-number--green" id="stat-today">0</div>
    </div>
  </div>
```
改为：
```html
  <div class="col-6 col-xl-3">
    <div class="stat-card accent-card">
      <div class="stat-icon" style="background:var(--color-accent-subtle);color:var(--color-accent)">
        <i class="bi bi-calendar-check-fill"></i>
      </div>
      <div class="stat-label">今日处理</div>
      <div class="stat-number" id="stat-today">0</div>
    </div>
  </div>
```

- [ ] **Step 2: 确认文件保存**

---

## Task 4: 修改 emails.html — 移除 inline border-radius

**Files:**
- Modify: `web/templates/emails.html:46`

现有 panel-card 上有 `style="border-radius:var(--radius-md)"` 会覆盖 CSS 的 `--radius-lg`，导致圆角偏小。移除它。

- [ ] **Step 1: 修改 `web/templates/emails.html` 第 46 行**

将：
```html
<div class="panel-card" style="border-radius:var(--radius-md)">
```
改为：
```html
<div class="panel-card">
```

- [ ] **Step 2: 确认文件保存**

---

## Task 5: 端对端验证

**Goal:** 确认四页面在浅色/深色双模式下视觉正确，功能无损。

- [ ] **Step 1: 启动开发服务器**

```bash
cd C:/Users/simple/email_sorter
uvicorn web.app:app --reload --port 8000
```

预期输出：`INFO: Uvicorn running on http://127.0.0.1:8000`

- [ ] **Step 2: 检查仪表盘 — 浅色模式**

访问 `http://localhost:8000`

检查项：
- [ ] 页面背景为浅灰 `#f8fafc`
- [ ] 侧边栏白色背景，"仪表盘"导航项有蓝色浅底高亮
- [ ] 顶部栏白色背景，运行状态为绿色胶囊
- [ ] Toggle 按钮为灰色（浅色模式），thumb 在左侧
- [ ] 4 张统计卡片白色背景，"今日处理"有蓝色边框和蓝色数字
- [ ] 图表和最近记录表格正常显示，徽标颜色正确（spam=红，important=蓝等）
- [ ] 统计卡片有 staggered 入场动画（页面加载时依次淡入上移）

- [ ] **Step 3: 切换深色模式**

点击顶栏 Toggle 按钮

检查项：
- [ ] Toggle thumb 滑动到右侧，按钮变蓝
- [ ] 所有颜色平滑过渡（200ms，无闪烁）
- [ ] 背景变为深色 `#0f1623`，卡片变为 `#111927`
- [ ] 侧边栏 active 项颜色变为亮蓝 `#3b82f6`
- [ ] 徽标颜色切换为深色版本（半透明背景，亮色文字）

- [ ] **Step 4: 刷新页面确认主题持久化**

切换到深色后刷新，确认：
- [ ] 页面载入时直接显示深色，无白色闪烁
- [ ] 再次切换回浅色，刷新后保持浅色

- [ ] **Step 5: 检查其余三页面**

访问 `/emails`、`/blacklist`、`/rules`，在浅色和深色模式各检查：
- [ ] 筛选栏样式正确（inputs、selects、按钮）
- [ ] 表格行 hover 效果
- [ ] Pill 标签页切换样式（黑白名单页）
- [ ] Modal 弹窗在深色模式下背景色正确（删除确认弹窗）
- [ ] 分页按钮样式正确

- [ ] **Step 6: 检查 Chart.js 图表**

访问 `/`，检查：
- [ ] 饼图/折线图的图例文字颜色随主题改变
- [ ] 折线图网格线颜色随主题改变

- [ ] **Step 7: 提交**

```bash
git add web/static/style.css web/templates/base.html web/templates/dashboard.html web/templates/emails.html
git commit -m "redesign: Stripe-style light/dark theme with DM Sans + DM Mono

- Rewrote style.css with new CSS variable system (light-first)
- DM Sans replaces Fraunces+Figtree, DM Mono replaces JetBrains Mono  
- Light mode default (#f8fafc bg, #0369a1 accent) with dark companion
- Smooth theme toggle with CSS sliding switch (38x22px)
- Staggered reveal animation on stat/panel cards
- Preserved all functional JS logic unchanged"
```

---

## Self-Review Notes

- **Spec coverage:** ✓ 所有 Token、组件、页面、动效均有对应 Task
- **Backward compat:** ✓ 旧变量名（`--accent`, `--text-primary`, `--muted`, `--font-mono` 等）在两套主题中均有别名，存量 inline styles 无需修改
- **Type consistency:** ✓ CSS 类名在 Task 1-4 中保持一致（`.accent-card`, `.anim-card`, `.btn-amber`, `.btn-ghost`, `.btn-danger-ghost`）
- **Detail row:** 保留现有 `display:none/block` 机制，`.detail-content` 仅提供视觉样式，不改变 JS 逻辑
