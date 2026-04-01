# Frontend Polish — Design Spec
**Date:** 2026-04-01  
**Approach:** 方案 A — 精准修复（style.css + 局部 HTML 微调）

---

## Scope

Five targeted fixes to the existing Stripe-style SaaS UI. No structural redesign. All changes stay within `web/static/style.css` and the four Jinja2 templates.

---

## Change 1 — Add three missing CSS classes (`style.css`)

**Problem:** Three classes are referenced in templates but absent from `style.css`:
- `anim-fade-in-up` — used on every `<tr>` in all tables for staggered entry animation
- `confidence-fill--high` — applied when confidence ≥ 80%, should tint the bar blue
- `detail-key` — label style inside the expandable detail row in `emails.html`

**Fix:**
```css
/* anim-fade-in-up: reuses existing fadeInUp keyframe already defined in style.css */
.anim-fade-in-up { opacity:0; animation: fadeInUp 280ms ease forwards; }

/* confidence-fill--high: accent-blue tint for bars >= 80% */
.confidence-fill--high { background: var(--color-accent); }

/* detail-key: small uppercase label in detail expansion */
.detail-key {
  font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--color-text-3); margin-right: 4px;
}
```

---

## Change 2 — Stat card icons use CSS variables (`style.css` + `dashboard.html`)

**Problem:** All four main stat card `stat-icon` divs use `style="background:rgba(…)"` with hardcoded values that look wrong in light theme.

**Fix:** Define semantic CSS classes for each icon variant and apply them in `dashboard.html`:
```css
.stat-icon--default  { background: var(--color-bg-subtle);          color: var(--color-text-3); }
.stat-icon--accent   { background: var(--color-accent-subtle);       color: var(--color-accent); }
.stat-icon--danger   { background: var(--danger-bg);                 color: var(--danger); }
.stat-icon--warning  { background: rgba(245,158,11,0.12);            color: var(--warning); }
.stat-icon--success  { background: var(--success-bg);                color: var(--success); }
```
Replace inline `style=` on all stat card `<div class="stat-icon">` elements with the appropriate class.

---

## Change 3 — Chart.js colors respond to light/dark theme (`dashboard.html`)

**Problem:** Chart tooltip background `#20242b`, grid `rgba(255,255,255,0.04)`, and axis tick colors `#6b7280` are all dark-theme values. In light theme the tooltip appears as a dark box over a white background.

**Fix:** Refactor `updateChartColors()` to destroy and re-create charts on theme toggle, pulling colors from CSS variables via `getComputedStyle`. Key values:
- Tooltip bg: `var(--color-surface)`, border: `var(--color-border)`, title: `var(--color-text)`, body: `var(--color-text-2)`
- Grid: `var(--color-border)`, ticks: `var(--color-text-3)`

Chart instances stored in module-level variables (`categoryChart`, `metricsChart`) so they can be destroyed and rebuilt. `updateChartColors()` is called on DOMContentLoaded and on every theme toggle click.

---

## Change 4 — Loading and empty state upgrades (`style.css` + all four templates)

**Problem:** "加载中…" is plain text with no visual feedback. "暂无记录" empty states use a faded icon + text but inconsistently styled across pages.

**Fix:**

Add a CSS spinner:
```css
.loading-spinner {
  width: 20px; height: 20px; border: 2px solid var(--color-border);
  border-top-color: var(--color-accent); border-radius: 50%;
  animation: spin 700ms linear infinite; display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }
```

Replace all "加载中…" text nodes with:
```html
<div class="text-center py-5" style="color:var(--color-text-3)">
  <span class="loading-spinner"></span>
  <div style="margin-top:10px;font-size:0.84rem">正在加载…</div>
</div>
```

Standardize empty states across all four pages to use the same structure:
```html
<div class="text-center py-5" style="color:var(--color-text-3)">
  <i class="bi bi-[icon] d-block mb-2" style="font-size:2rem;opacity:0.35"></i>
  <div style="font-size:0.84rem">[描述文字]</div>
</div>
```

---

## Change 5 — Rules form two-row layout + dashboard list cards (`rules.html` + `dashboard.html`)

### 5a — Rules form
**Problem:** Seven form fields crammed into a single `row` with `col-sm-1` and `col-sm-2` columns. Labels and inputs are barely readable.

**Fix:** Split into two rows:
- Row 1 (col-sm-4 / col-sm-2 / col-sm-3 / col-sm-3): 规则名称 · 匹配字段 · 匹配方式 · 匹配值
- Row 2 (col-sm-3 / col-sm-2 / col-sm-2 / col-sm-auto): 分类 · 优先级 · 添加按钮

### 5b — Dashboard list stats row
**Problem:** The blacklist/whitelist stat row only has two `col-6 col-md-3` cards, leaving half the row empty.

**Fix:** Add two more cards to fill the row:
- **自定义规则数** — fetched from `/api/rules` response length
- **今日拦截** — `category_counts.spam` from existing `/api/stats` response (already loaded)

Both new cards use existing `.stat-card` markup patterns; no new API endpoints needed.

---

## Files Changed

| File | Changes |
|------|---------|
| `web/static/style.css` | Add: `anim-fade-in-up`, `confidence-fill--high`, `detail-key`, `stat-icon--*` variants, `.loading-spinner`, `@keyframes spin` |
| `web/templates/dashboard.html` | Stat icon classes, chart color refactor, two new list stat cards, loading/empty states |
| `web/templates/emails.html` | Loading/empty state markup |
| `web/templates/blacklist.html` | Loading/empty state markup |
| `web/templates/rules.html` | Form two-row layout, loading/empty state markup |

---

## Non-Goals

- No new API endpoints
- No sidebar or topbar restructuring
- No responsive/mobile layout changes
- No new JavaScript dependencies
