"""All styling for the H1 review workbench.

The server inlines these CSS constants into every page: no build step, no
framework, no external resources, system font stack. Change styling here and
re-run.

The semantic colour discipline comes from the Visual System v1 in the
briefloop-prototypes README, and must hold — this is product honesty, not
decoration:

- Blue = action / info. The current state of a human decision
  (accept/reject/correct/abstain) is also blue: human-confirmed is not a
  deterministic pass, and must not be green.
- Purple = advisory: values and hints sourced from DWS or a model. Never means
  "passed".
- Green = deterministic pass only (a gate passing, a bundle verifying).
- Red = deterministic block. `.wb-rejected` / `.wb-blocking` use this.
- Yellow = attention (warnings, convention disputes, the armed state of a
  two-step confirmation).
- Grey = unavailable or awaiting review.
"""

CSS = """/* ==========================================================================
   InvoiceLoop 复核工作台 —— token 层
   ========================================================================== */
:root {
    --wb-font-body: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    --wb-font-mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;

    --wb-paper: #faf9f6;
    --wb-surface: #ffffff;
    --wb-sunken: #f3f2ee;
    --wb-ink: #1e2320;
    --wb-ink-soft: #3a403b;
    --wb-muted: #6a706b;
    --wb-faint: #949a94;
    --wb-line: rgba(30, 35, 32, 0.14);
    --wb-line-soft: rgba(30, 35, 32, 0.08);

    /* 语义色:每族 实色 / wash 底 / line 描边 三件套 */
    --wb-action: #1d5fd1;
    --wb-action-wash: rgba(29, 95, 209, 0.08);
    --wb-action-line: rgba(29, 95, 209, 0.35);
    --wb-advisory: #6d4bc4;
    --wb-advisory-wash: rgba(109, 75, 196, 0.08);
    --wb-advisory-line: rgba(109, 75, 196, 0.30);
    --wb-pass: #2c7a4b;
    --wb-pass-wash: rgba(44, 122, 75, 0.10);
    --wb-pass-line: rgba(44, 122, 75, 0.30);
    --wb-block: #c2401f;
    --wb-block-wash: rgba(194, 64, 31, 0.08);
    --wb-block-line: rgba(194, 64, 31, 0.28);
    --wb-warn: #a8540a;
    --wb-warn-wash: rgba(168, 84, 10, 0.09);
    --wb-warn-line: rgba(168, 84, 10, 0.28);
    --wb-unavail: #6a706b;
    --wb-unavail-wash: rgba(106, 112, 107, 0.10);
    --wb-unavail-line: rgba(106, 112, 107, 0.25);

    --wb-radius: 10px;
    --wb-radius-sm: 7px;
    --wb-shadow: 0 1px 2px rgba(30, 35, 32, 0.05), 0 8px 24px rgba(30, 35, 32, 0.05);
    --wb-max: 1200px;
}

*, *::before, *::after { box-sizing: border-box; }

body {
    margin: 0;
    background: var(--wb-paper);
    color: var(--wb-ink);
    font-family: var(--wb-font-body);
    font-size: 15px;
    line-height: 1.65;
    -webkit-font-smoothing: antialiased;
}
button, input, textarea, select { font: inherit; }
button { cursor: pointer; border: none; background: none; color: inherit; }
a { color: var(--wb-action); text-decoration: none; }
a:hover { text-decoration: underline; }
:focus-visible { outline: 2px solid var(--wb-action); outline-offset: 2px; border-radius: 3px; }

/* 主内容容器:1200px 上限 */
.wb-main {
    max-width: var(--wb-max);
    margin: 0 auto;
    padding: 24px 24px 72px;
}

/* ---- 顶栏:品牌 + 页签 + 语言 ---- */
.wb-topbar {
    position: sticky;
    top: 0;
    z-index: 30;
    display: flex;
    align-items: center;
    gap: 16px;
    background: var(--wb-paper);
    border-bottom: 1px solid var(--wb-line-soft);
    /* 与 1200px 内容列对齐,同时保住整栏底色 */
    padding: 10px max(24px, calc((100% - var(--wb-max)) / 2 + 24px));
}
.wb-brand {
    font-weight: 700;
    font-size: 15px;
    letter-spacing: 0.01em;
    color: var(--wb-ink);
    white-space: nowrap;
}
/* 顶栏内层:服务器输出的实际 flex 容器(brand/tabs/runs/lang 都在它里面),
   外层 .wb-topbar 只负责底色与对齐内边距 */
.wb-topbar-inner {
    display: flex;
    align-items: center;
    gap: 16px;
    width: 100%;
}
.wb-topbar-inner .wb-brand { margin-right: auto; }
.wb-tabs { display: flex; gap: 4px; }
.wb-tab {
    font-size: 13.5px;
    font-weight: 500;
    color: var(--wb-muted);
    padding: 8px 12px 6px;
    border-bottom: 2px solid transparent;
    white-space: nowrap;
    text-decoration: none;
}
.wb-tab:hover { color: var(--wb-ink); text-decoration: none; }
.wb-tab.active { color: var(--wb-action); border-bottom-color: var(--wb-action); }
.wb-lang {
    font-size: 12.5px;
    color: var(--wb-muted);
    background: var(--wb-surface);
    border: 1px solid var(--wb-line);
    border-radius: var(--wb-radius-sm);
    padding: 5px 10px;
    white-space: nowrap;
}

/* ---- 横幅与提示条 ---- */
.wb-banner {
    background: var(--wb-surface);
    border: 1px solid var(--wb-line-soft);
    border-radius: var(--wb-radius);
    box-shadow: var(--wb-shadow);
    padding: 18px 22px;
    margin-bottom: 18px;
}
.wb-terminated {
    border-color: var(--wb-warn-line);
    background: var(--wb-warn-wash);
    color: var(--wb-warn);
    font-weight: 600;
}
.wb-triad {
    font-size: 13px;
    color: var(--wb-ink-soft);
    padding: 8px 0 4px;
}
.wb-triad-cell {
    display: inline-block;
    margin-right: 14px;
}
.wb-notice {
    border: 1px solid var(--wb-action-line);
    background: var(--wb-action-wash);
    color: var(--wb-ink-soft);
    border-radius: var(--wb-radius-sm);
    padding: 10px 14px;
    font-size: 13px;
    margin: 12px 0;
}
.wb-notice.warn {
    border-color: var(--wb-warn-line);
    background: var(--wb-warn-wash);
    color: var(--wb-warn);
}
.wb-scope {
    border-bottom: 1px solid var(--wb-action-line);
    background: var(--wb-action-wash);
    color: var(--wb-ink-soft);
    padding: 6px 24px;
    font: 600 12px/1.4 var(--wb-font-mono);
}

/* ---- 进度条(宽度由服务器内联 style 给百分比) ---- */
.wb-progress {
    height: 8px;
    background: var(--wb-sunken);
    border: 1px solid var(--wb-line-soft);
    border-radius: 6px;
    overflow: hidden;
    margin: 10px 0 4px;
}
.wb-progress-bar {
    display: block;
    height: 100%;
    background: var(--wb-action);
    border-radius: 6px 0 0 6px;
}

/* ---- 过滤 chips ---- */
.wb-filters {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 14px 0 18px;
    align-items: center;
}
/* 搜索框:与 chips 同行,服务器端过滤 */
.wb-search { display: inline-flex; gap: 6px; margin-left: auto; }
.wb-search input[type="search"] {
    font-size: 13px;
    color: var(--wb-ink);
    background: var(--wb-surface);
    border: 1px solid var(--wb-line);
    border-radius: var(--wb-radius-sm);
    padding: 5px 11px;
    min-width: 200px;
}
.wb-search-btn {
    font-size: 12.5px;
    font-weight: 600;
    color: var(--wb-action);
    background: var(--wb-action-wash);
    border: 1px solid var(--wb-action-line);
    border-radius: var(--wb-radius-sm);
    padding: 5px 13px;
}
.wb-search-btn:hover { border-color: var(--wb-action); }
.wb-chip {
    font-size: 12.5px;
    font-weight: 500;
    color: var(--wb-ink-soft);
    background: var(--wb-surface);
    border: 1px solid var(--wb-line);
    border-radius: 20px;
    padding: 5px 13px;
    text-decoration: none;
    transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}
.wb-chip:hover { border-color: var(--wb-ink); text-decoration: none; }
.wb-chip.active {
    color: var(--wb-action);
    border-color: var(--wb-action-line);
    background: var(--wb-action-wash);
}

/* ---- 行卡片:一行 = 一个待复核字段 ---- */
.wb-row {
    background: var(--wb-surface);
    border: 1px solid var(--wb-line-soft);
    border-radius: var(--wb-radius);
    box-shadow: var(--wb-shadow);
    padding: 18px 22px;
    margin-bottom: 14px;
    transition: background 0.15s ease;
}
.wb-row:hover { background: #fdfdfc; }
.wb-row-head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 8px 14px;
    margin-bottom: 10px;
}
.wb-doc {
    font-family: var(--wb-font-mono);
    font-size: 12px;
    color: var(--wb-muted);
}
.wb-field {
    font-family: var(--wb-font-mono);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--wb-faint);
}
.wb-value {
    font-size: 16px;
    font-weight: 600;
    color: var(--wb-ink);
    word-break: break-all;
}
.wb-value.none {
    font-weight: 400;
    font-style: italic;
    color: var(--wb-faint);
}

/* ---- 支持强度徽章:模型/OCR 来源,紫(永不表示"通过");无支持 = 灰 ---- */
.wb-badge {
    display: inline-block;
    font-family: var(--wb-font-mono);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.02em;
    border: 1px solid;
    border-radius: 20px;
    padding: 2px 10px;
    white-space: nowrap;
}
.wb-badge.unsupported {
    color: var(--wb-unavail);
    background: var(--wb-unavail-wash);
    border-color: var(--wb-unavail-line);
}
.wb-badge.single_source {
    color: var(--wb-advisory);
    background: var(--wb-advisory-wash);
    border-color: var(--wb-advisory-line);
}
.wb-badge.corroborated {
    color: var(--wb-advisory);
    background: var(--wb-advisory-wash);
    border-color: var(--wb-advisory);
}
/* 口径争议:显式展示,attention 黄,不进任何错误计数 */
.wb-disputed {
    display: inline-block;
    font-size: 12px;
    color: var(--wb-warn);
    background: var(--wb-warn-wash);
    border: 1px solid var(--wb-warn-line);
    border-radius: var(--wb-radius-sm);
    padding: 2px 9px;
}

/* ---- 门禁:确定性结果,pass 绿 / warning 黄 / fail 红 / unavailable 灰 ---- */
.wb-gates {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 8px 0;
}
.wb-gate {
    font-family: var(--wb-font-mono);
    font-size: 11px;
    font-weight: 600;
    border: 1px solid;
    border-radius: var(--wb-radius-sm);
    padding: 3px 9px;
    white-space: nowrap;
}
.wb-gate.pass { color: var(--wb-pass); background: var(--wb-pass-wash); border-color: var(--wb-pass-line); }
.wb-gate.warning { color: var(--wb-warn); background: var(--wb-warn-wash); border-color: var(--wb-warn-line); }
.wb-gate.fail { color: var(--wb-block); background: var(--wb-block-wash); border-color: var(--wb-block-line); }
.wb-gate.unavailable { color: var(--wb-unavail); background: var(--wb-unavail-wash); border-color: var(--wb-unavail-line); }

/* ---- 裁决状态:人的裁决一律蓝(human-confirmed ≠ deterministic pass) ---- */
.wb-status {
    display: inline-block;
    font-size: 12px;
    font-weight: 600;
    border: 1px solid;
    border-radius: 20px;
    padding: 2px 11px;
    white-space: nowrap;
}
.wb-status.pending {
    color: var(--wb-unavail);
    background: var(--wb-unavail-wash);
    border-color: var(--wb-unavail-line);
}
.wb-status.accept,
.wb-status.reject,
.wb-status.correct,
.wb-status.abstain {
    color: var(--wb-action);
    background: var(--wb-action-wash);
    border-color: var(--wb-action-line);
}
/* 多人裁决冲突:需要 attention */
.wb-status.conflict {
    color: var(--wb-warn);
    background: var(--wb-warn-wash);
    border-color: var(--wb-warn-line);
}

/* ---- 证据区:details/summary 手风琴 ---- */
.wb-evidence {
    border: 1px solid var(--wb-line-soft);
    border-radius: var(--wb-radius-sm);
    background: var(--wb-paper);
    margin: 10px 0;
}
.wb-evidence > summary {
    cursor: pointer;
    list-style: none;
    font-size: 13px;
    font-weight: 500;
    color: var(--wb-ink-soft);
    padding: 9px 14px;
    user-select: none;
}
.wb-evidence > summary::-webkit-details-marker { display: none; }
.wb-evidence > summary::before {
    content: "▸";
    display: inline-block;
    margin-right: 7px;
    color: var(--wb-faint);
    transition: transform 0.15s ease;
}
.wb-evidence[open] > summary::before { transform: rotate(90deg); }
.wb-evidence[open] > summary { border-bottom: 1px solid var(--wb-line-soft); }
.wb-evidence > div, .wb-evidence > section { padding: 12px 14px; }

/* 引用 span 小签 */
.wb-span {
    display: inline-block;
    font-family: var(--wb-font-mono);
    font-size: 11.5px;
    color: var(--wb-ink-soft);
    background: var(--wb-surface);
    border: 1px solid var(--wb-line);
    border-radius: 5px;
    padding: 2px 7px;
    margin: 2px 4px 2px 0;
}
/* 字段裁剪图(class 直接挂在 <img> 上,没有容器),限宽 360px */
.wb-crop {
    display: block;
    margin: 8px 0;
    max-width: 360px;
    width: 100%;
    height: auto;
    border: 1px solid var(--wb-line);
    border-radius: var(--wb-radius-sm);
    background: var(--wb-surface);
}
/* 独立 OCR 原文:等宽、灰 */
.wb-ocr {
    font-family: var(--wb-font-mono);
    font-size: 12px;
    line-height: 1.6;
    color: var(--wb-muted);
    background: var(--wb-sunken);
    border: 1px solid var(--wb-line-soft);
    border-radius: var(--wb-radius-sm);
    padding: 10px 12px;
    margin: 8px 0;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 220px;
    overflow-y: auto;
}
.wb-label { font-style: italic; color: var(--wb-muted); font-size: 12.5px; }
/* 被拒行的复核证据缺位提示:红字小字 */
.wb-rejected { color: var(--wb-block); font-size: 12px; }
/* 阻断级发现:红字加粗 */
.wb-blocking { color: var(--wb-block); font-weight: 700; }

/* ---- 裁决表单区:sunken 底,与证据区拉开层级 ---- */
.wb-decide {
    background: var(--wb-sunken);
    border: 1px solid var(--wb-line-soft);
    border-radius: var(--wb-radius);
    padding: 16px 18px;
    margin-top: 14px;
}
.wb-decide-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    margin: 10px 0;
}

/* choice-card 单选:藏 input,label 成药丸 */
.wb-radio {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-size: 13px;
    font-weight: 500;
    color: var(--wb-ink-soft);
    background: var(--wb-surface);
    border: 1px solid var(--wb-line);
    border-radius: 20px;
    padding: 7px 15px;
    cursor: pointer;
    transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
}
.wb-radio:hover { border-color: var(--wb-ink); }
.wb-radio input {
    position: absolute;
    opacity: 0;
    width: 0;
    height: 0;
    pointer-events: none;
}
/* 选中态:默认蓝(人的裁决);reject 红色调;correct 蓝色调;abstain 灰 */
.wb-radio:has(input:checked) {
    color: var(--wb-action);
    border-color: var(--wb-action);
    background: var(--wb-action-wash);
    box-shadow: inset 0 0 0 1px var(--wb-action);
}
.wb-radio.reject:has(input:checked),
.wb-radio:has(input[value="reject"]:checked) {
    color: var(--wb-block);
    border-color: var(--wb-block);
    background: var(--wb-block-wash);
    box-shadow: inset 0 0 0 1px var(--wb-block);
}
.wb-radio.correct:has(input:checked),
.wb-radio:has(input[value="correct"]:checked) {
    color: var(--wb-action);
    border-color: var(--wb-action);
    background: var(--wb-action-wash);
    box-shadow: inset 0 0 0 1px var(--wb-action);
}
.wb-radio.abstain:has(input:checked),
.wb-radio:has(input[value="abstain"]:checked) {
    color: var(--wb-unavail);
    border-color: var(--wb-unavail);
    background: var(--wb-unavail-wash);
    box-shadow: inset 0 0 0 1px var(--wb-unavail-line);
}

/* 修正值输入:correct 必带,disabled 时灰 */
.wb-corr {
    font-size: 13.5px;
    color: var(--wb-ink);
    background: var(--wb-surface);
    border: 1px solid var(--wb-line);
    border-radius: var(--wb-radius-sm);
    padding: 8px 12px;
    min-width: 240px;
}
.wb-corr:focus { outline: 2px solid var(--wb-action); outline-offset: 1px; border-color: var(--wb-action); }
.wb-corr:disabled {
    background: var(--wb-unavail-wash);
    color: var(--wb-unavail);
    border-color: var(--wb-line-soft);
    cursor: not-allowed;
}

/* 问题 / 理由:人工输入的主入口,占满宽、要醒目 */
.wb-rationale {
    display: block;
    width: 100%;
    min-height: 120px;
    font-size: 14px;
    line-height: 1.65;
    color: var(--wb-ink);
    background: var(--wb-surface);
    border: 1px solid var(--wb-line);
    border-radius: var(--wb-radius-sm);
    padding: 12px 14px;
    resize: vertical;
    margin: 10px 0;
}
.wb-rationale:focus {
    outline: 2px solid var(--wb-action);
    outline-offset: 1px;
    border-color: var(--wb-action);
}

/* 快捷问题标签 */
.wb-issue-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    margin: 8px 0;
}
.wb-issue-chip {
    font-size: 12px;
    color: var(--wb-ink-soft);
    background: var(--wb-surface);
    border: 1px solid var(--wb-line);
    border-radius: 20px;
    padding: 4px 12px;
    transition: border-color 0.15s ease, color 0.15s ease;
}
.wb-issue-chip:hover { border-color: var(--wb-action); color: var(--wb-action); }

/* 裁决人署名 */
.wb-adjudicator {
    font-size: 13px;
    color: var(--wb-ink);
    background: var(--wb-surface);
    border: 1px solid var(--wb-line);
    border-radius: var(--wb-radius-sm);
    padding: 7px 11px;
    min-width: 160px;
}

/* ---- 按钮:主按钮蓝;两步确认武装态转黄底黑字 ---- */
.wb-btn {
    font-size: 13.5px;
    font-weight: 600;
    color: #ffffff;
    background: var(--wb-action);
    border: 1px solid var(--wb-action);
    border-radius: 8px;
    padding: 9px 20px;
    transition: background 0.15s ease;
}
.wb-btn:hover:not(:disabled) { background: #1a54b8; }
.wb-btn:disabled {
    background: var(--wb-unavail-wash);
    border-color: var(--wb-unavail-line);
    color: var(--wb-unavail);
    cursor: not-allowed;
}
.wb-btn.armed {
    background: #f2c317;
    border-color: #d9ae0e;
    color: #1e2320;
}

/* ---- 已有裁决提示条(蓝 wash)/ 孤儿裁决提示(紫 wash) ---- */
.wb-current {
    border: 1px solid var(--wb-action-line);
    background: var(--wb-action-wash);
    color: var(--wb-ink-soft);
    border-radius: var(--wb-radius-sm);
    padding: 10px 14px;
    font-size: 13px;
    margin: 10px 0;
}
.wb-orphan {
    border: 1px solid var(--wb-advisory-line);
    background: var(--wb-advisory-wash);
    color: var(--wb-advisory);
    border-radius: var(--wb-radius-sm);
    padding: 10px 14px;
    font-size: 13px;
    margin: 10px 0;
}

/* ---- 提交被拒的表单内提示(红 = 确定性阻断:这次写入被拒了)。
       摆在表单**正上方**,人的输入原样还在下面 —— 以前这里是一张整页
       「阻断」,回不去也带不走已填内容(2026-08-08 用户实测) ---- */
.wb-form-error {
    border: 1px solid var(--wb-block-line);
    background: var(--wb-block-wash);
    color: var(--wb-block);
    border-radius: var(--wb-radius-sm);
    padding: 10px 14px;
    font-size: 13px;
    line-height: 1.55;
    margin: 10px 0;
}
.wb-form-error p { margin: 4px 0 0; }
.wb-form-error .wb-form-error-kept { color: var(--wb-ink-soft); }

/* ---- 报告页:统计卡 + 修正清单 ---- */
.wb-report-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 10px;
    margin: 16px 0;
}
.wb-stat {
    background: var(--wb-surface);
    border: 1px solid var(--wb-line-soft);
    border-radius: var(--wb-radius-sm);
    padding: 12px 14px;
}
.wb-stat .k, .wb-stat .wb-stat-k {
    display: block;
    font-family: var(--wb-font-mono);
    font-size: 10.5px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--wb-faint);
}
.wb-stat .v, .wb-stat .wb-stat-v {
    display: block;
    font-size: 22px;
    font-weight: 700;
    margin-top: 4px;
}
.wb-corrections { margin: 14px 0; }
.wb-corr-item {
    background: var(--wb-surface);
    border: 1px solid var(--wb-line-soft);
    border-left: 3px solid var(--wb-action);
    border-radius: var(--wb-radius-sm);
    padding: 10px 14px;
    margin-bottom: 8px;
    font-size: 13px;
    color: var(--wb-ink-soft);
}

/* ---- 上传 / 列表 / 表单 / 键值 ---- */
.wb-upload {
    background: var(--wb-surface);
    border: 1px dashed var(--wb-line);
    border-radius: var(--wb-radius);
    padding: 22px;
    margin: 14px 0;
}
.wb-list {
    margin: 0;
    padding: 0;
    list-style: none;
}
.wb-list li {
    padding: 9px 0;
    border-bottom: 1px solid var(--wb-line-soft);
    font-size: 13.5px;
    color: var(--wb-ink-soft);
}
.wb-list li:last-child { border-bottom: none; }
.wb-form { margin: 12px 0; }
.wb-form label {
    display: block;
    font-size: 12.5px;
    font-weight: 500;
    color: var(--wb-muted);
    margin: 10px 0 4px;
}
.wb-form input[type="text"], .wb-form input[type="file"], .wb-form select {
    font-size: 13.5px;
    color: var(--wb-ink);
    background: var(--wb-surface);
    border: 1px solid var(--wb-line);
    border-radius: var(--wb-radius-sm);
    padding: 8px 12px;
}
.wb-kv {
    width: 100%;
    border-collapse: collapse;
    font-size: 13.5px;
}
.wb-kv th, .wb-kv td {
    text-align: left;
    vertical-align: top;
    padding: 7px 10px 7px 0;
    border-bottom: 1px solid var(--wb-line-soft);
}
.wb-kv tr:last-child th, .wb-kv tr:last-child td { border-bottom: none; }
.wb-kv th { font-weight: 500; color: var(--wb-muted); width: 220px; font-size: 13px; }
.wb-kv td { color: var(--wb-ink-soft); }
.wb-kv code {
    font-family: var(--wb-font-mono);
    font-size: 12px;
    background: var(--wb-sunken);
    border: 1px solid var(--wb-line-soft);
    border-radius: 4px;
    padding: 1px 6px;
}

/* ---- bundle 校验:确定性结果,绿 / 红 ---- */
.wb-verify-ok {
    color: var(--wb-pass);
    background: var(--wb-pass-wash);
    border: 1px solid var(--wb-pass-line);
    border-radius: var(--wb-radius-sm);
    padding: 10px 14px;
    font-size: 13px;
    margin: 10px 0;
}
.wb-verify-fail {
    color: var(--wb-block);
    background: var(--wb-block-wash);
    border: 1px solid var(--wb-block-line);
    border-radius: var(--wb-radius-sm);
    padding: 10px 14px;
    font-size: 13px;
    margin: 10px 0;
}

/* ---- 页脚与独立消息页 ---- */
.wb-footer {
    max-width: var(--wb-max);
    margin: 36px auto 0;
    padding: 18px 24px 0;
    border-top: 1px solid var(--wb-line-soft);
    font-size: 12px;
    color: var(--wb-faint);
    line-height: 1.8;
}
.wb-footer code {
    font-family: var(--wb-font-mono);
    font-size: 11px;
    background: var(--wb-sunken);
    border: 1px solid var(--wb-line-soft);
    border-radius: 4px;
    padding: 1px 5px;
}
.wb-msg-page {
    max-width: 560px;
    margin: 72px auto;
    padding: 28px 30px;
    background: var(--wb-surface);
    border: 1px solid var(--wb-line-soft);
    border-radius: var(--wb-radius);
    box-shadow: var(--wb-shadow);
}
.wb-msg-page h1 { font-size: 19px; margin: 0 0 10px; }
.wb-msg-page p { color: var(--wb-ink-soft); font-size: 14px; }

/* ---- 窄屏:基本可用即可 ---- */
@media (max-width: 900px) {
    .wb-main { padding: 16px 14px 56px; }
    .wb-topbar { flex-wrap: wrap; padding: 8px 14px; gap: 8px; }
    .wb-brand { margin-right: 0; }
    .wb-tabs { order: 3; width: 100%; overflow-x: auto; }
    .wb-row { padding: 14px 16px; }
    .wb-row-head { flex-direction: column; align-items: flex-start; gap: 4px; }
    .wb-decide-row { flex-direction: column; align-items: stretch; }
    .wb-corr, .wb-adjudicator { min-width: 0; width: 100%; }
    .wb-crop { max-width: 100%; }
    .wb-kv th { width: 130px; }
    .wb-msg-page { margin: 32px 14px; padding: 20px; }
}

/* ---- 打印:不苛求,去掉交互件即可读 ---- */
@media print {
    .wb-topbar, .wb-filters, .wb-decide, .wb-btn { display: none; }
    .wb-row, .wb-banner { box-shadow: none; }
    .wb-evidence > div, .wb-evidence > section { display: block; }
}


/* ---- 读图预填建议层(紫 = advisory,永不绿;建议不是裁决) ---- */
.wb-vision-suggest {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    margin: 6px 0;
    padding: 6px 10px;
    background: var(--wb-advisory-wash);
    border: 1px solid var(--wb-advisory-line);
    border-radius: var(--wb-radius-sm);
    font-size: 13px;
}
.wb-vision-suggest.muted { opacity: 0.75; }
.wb-invoice-read {
    margin: 8px 0;
    padding: 8px 10px;
    background: var(--wb-advisory-wash);
    border: 1px dashed var(--wb-advisory-line);
    border-radius: var(--wb-radius-sm);
    font-size: 13px;
}
.wb-invoice-read-kv { margin: 2px 0; }
.wb-invoice-read-why {
    margin: 6px 0 0;
    color: var(--wb-muted, #5c5748);
}
.wb-vs-label {
    font-size: 11.5px;
    font-weight: 600;
    color: var(--wb-advisory);
    letter-spacing: 0.04em;
}
.wb-vs-value { color: var(--wb-ink); }
.wb-vs-agree { color: var(--wb-muted); font-size: 12px; }
.wb-vs-split { color: var(--wb-warn); font-size: 12.5px; }
.wb-vs-blind { color: var(--wb-muted); font-size: 12.5px; }
.wb-vs-rejected { color: var(--wb-block); font-size: 12.5px; }
.wb-vs-adopt {
    margin-left: auto;
    padding: 3px 12px;
    border: 1px solid var(--wb-advisory);
    border-radius: 999px;
    background: transparent;
    color: var(--wb-advisory);
    font-size: 12.5px;
    font-weight: 600;
}
.wb-vs-adopt:hover { background: var(--wb-advisory); color: #fff; }

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { transition-duration: 0.01ms !important; }
}

/* ---- 复核任务的主角(2026-08-03 用户反馈:字段名又小又灰,任务目标看不见) ---- */
.wb-field {
    font-family: var(--wb-font-body);
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 0;
    color: var(--wb-ink);
}
.wb-raw {
    font-family: var(--wb-font-mono);
    font-size: 11px;
    font-weight: 400;
    color: var(--wb-faint);
    margin-left: 6px;
}
.wb-task {
    margin: 2px 0 4px;
    font-size: 13.5px;
    color: var(--wb-ink-soft);
}
.wb-doctype {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 4px 8px;
    border: 1px solid var(--wb-unavail-line);
    border-radius: var(--wb-radius-sm);
    background: var(--wb-unavail-wash);
    color: var(--wb-ink-soft);
    padding: 7px 10px;
    margin: 5px 0;
    font-size: 12.5px;
    line-height: 1.45;
}
.wb-doctype b { color: var(--wb-ink); }
.wb-doctype.pass {
    border-color: var(--wb-pass-line);
    background: var(--wb-pass-wash);
}
.wb-doctype.pass b { color: var(--wb-pass); }
.wb-doctype.warn {
    border-color: var(--wb-warn-line);
    background: var(--wb-warn-wash);
}
.wb-doctype.warn b { color: var(--wb-warn); }
.wb-doctype-proof {
    font-family: var(--wb-font-mono);
    color: var(--wb-muted);
    font-size: 11.5px;
}

/* ==========================================================================
   Gradescope 风格裁决页:左整页证据 / 右判定卡 / 底栏导航
   ========================================================================== */
.wb-adj {
    display: grid;
    grid-template-columns: minmax(0, 7fr) minmax(0, 5fr);
    gap: 18px;
    align-items: start;
    margin-top: 14px;
}
.wb-adj-left, .wb-adj-right { min-width: 0; }
.wb-adj-colhead {
    font-family: var(--wb-font-mono);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--wb-faint);
    margin: 0 0 10px;
}
.wb-adj-card {
    background: var(--wb-surface);
    border: 1px solid var(--wb-line-soft);
    border-radius: var(--wb-radius);
    box-shadow: var(--wb-shadow);
    padding: 18px 22px;
}
.wb-adj-verdict {
    border: 1px solid var(--wb-line-soft);
    border-radius: var(--wb-radius-sm);
    background: var(--wb-paper);
    padding: 12px 14px;
    margin: 10px 0;
}
.wb-adj-kv {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 8px 12px;
    margin: 6px 0;
}
.wb-adj-k {
    font-size: 12px;
    font-weight: 600;
    color: var(--wb-muted);
}
/* 策略放行提示:紫 wash —— 机器策略不是人工裁决,也不是确定性通过 */
.wb-policy {
    border: 1px solid var(--wb-advisory-line);
    background: var(--wb-advisory-wash);
    color: var(--wb-advisory);
    border-radius: var(--wb-radius-sm);
    padding: 9px 13px;
    font-size: 12.5px;
    margin: 8px 0 0;
}

/* 左栏:整页渲染 + bbox overlay(相对坐标 → CSS 百分比,不重渲染图片) */
.wb-page-wrap { margin: 0 0 14px; }
.wb-page-cap {
    font-family: var(--wb-font-mono);
    font-size: 11.5px;
    color: var(--wb-muted);
    margin-bottom: 5px;
}
.wb-page-stage {
    position: relative;
    border: 1px solid var(--wb-line);
    border-radius: var(--wb-radius-sm);
    overflow: hidden;
    background: var(--wb-surface);
    line-height: 0;  /* img 基线缝隙 */
}
.wb-page { display: block; width: 100%; height: auto; }
.wb-page-tools {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 0 0 7px;
    font-size: 12px;
}
.wb-hl-toggle, .wb-page-clean {
    border: 1px solid var(--wb-line);
    border-radius: var(--wb-radius-sm);
    background: var(--wb-surface);
    color: var(--wb-ink-soft);
    font: inherit;
    line-height: 1.3;
    padding: 4px 8px;
    cursor: pointer;
    text-decoration: none;
}
.wb-hl-toggle:hover, .wb-page-clean:hover { border-color: var(--wb-muted); }
/* 高亮框不能占用 bbox 内的任何像素:极扁的金额/日期 span 与字同高,
   1.5px border 仍会直接压住数字(2026-08-08 人工复核实测)。outline
   画在 bbox 外,透明底不再罩字;冻结绑定 = 绿实线,引用 = 紫虚线。 */
.wb-hl {
    position: absolute;
    border-radius: 2px;
    box-sizing: border-box;
    pointer-events: none;
}
.wb-hl-bind {
    outline: 1.5px solid var(--wb-pass);
    outline-offset: 2px;
    background: transparent;
}
.wb-hl-cited {
    outline: 1.5px dashed var(--wb-advisory);
    outline-offset: 2px;
    background: transparent;
}
.wb-hl-doctype {
    outline: 1.5px dotted var(--wb-pass);
    outline-offset: 4px;
    background: transparent;
}
.wb-page-stage.wb-hl-off .wb-hl { display: none; }
.wb-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 18px;
    font-size: 12px;
    color: var(--wb-muted);
}
.wb-legend-swatch {
    display: inline-block;
    width: 16px;
    height: 11px;
    margin-right: 6px;
    vertical-align: -1px;
    border-radius: 2px;
}
.wb-legend-swatch.bind {
    border: 1.5px solid var(--wb-pass);
    background: rgba(44, 122, 75, 0.08);
}
.wb-legend-swatch.cited {
    border: 1.5px dashed var(--wb-advisory);
    background: rgba(109, 75, 196, 0.08);
}
.wb-legend-swatch.doctype {
    border: 1.5px dotted var(--wb-pass);
    background: var(--wb-pass-wash);
}

/* 底栏:上一条 / 下一条未裁决 + 进度,sticky 贴底 */
.wb-adj-nav {
    position: sticky;
    bottom: 0;
    z-index: 20;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    background: var(--wb-paper);
    border-top: 1px solid var(--wb-line-soft);
    padding: 12px 2px;
    margin-top: 18px;
}
.wb-nav-btn {
    font-size: 13px;
    font-weight: 600;
    color: var(--wb-action);
    background: var(--wb-surface);
    border: 1px solid var(--wb-action-line);
    border-radius: 8px;
    padding: 8px 16px;
    white-space: nowrap;
    text-decoration: none;
}
.wb-nav-btn:hover { border-color: var(--wb-action); text-decoration: none; }
.wb-nav-btn.disabled {
    color: var(--wb-faint);
    border-color: var(--wb-line-soft);
    background: transparent;
    cursor: default;
}
.wb-adj-progress { font-size: 13px; color: var(--wb-muted); }

/* 队列行上的裁决页入口 */
.wb-adj-link {
    margin-left: auto;
    font-size: 12.5px;
    font-weight: 600;
    white-space: nowrap;
}

@media (max-width: 900px) {
    .wb-adj { grid-template-columns: 1fr; }
    .wb-adj-nav { flex-wrap: wrap; }
}
@media print {
    .wb-adj-nav, .wb-adj-link { display: none; }
}

/* ==========================================================================
   裁决页紧凑模式(2026-08-05 用户实测:一屏放下一页发票 + 判定卡,不滚动)
   只压空间,不动语义色与信息项 —— 所有内容仍在,只是不再浪费。
   ========================================================================== */
.wb-compact .wb-thesis {
    padding: 3px 24px;
    font-size: 12px;
    line-height: 1.4;
}
.wb-compact .wb-banner,
.wb-compact .wb-notice,
.wb-compact .wb-scope {
    padding: 5px 14px;
    margin: 4px auto;
    font-size: 12px;
    line-height: 1.45;
    max-width: var(--wb-max);
    border-radius: var(--wb-radius-sm);
    box-shadow: none;
}
.wb-compact .wb-main { padding: 8px 24px 64px; }
.wb-compact .wb-adj { margin-top: 6px; gap: 14px; }
.wb-compact .wb-adj-colhead { margin-bottom: 5px; }

/* 左栏:整页高度压进视口 —— 图按视口高缩放,stage 收缩包裹图,
   overlay 百分比相对 stage,任何缩放都对齐 */
.wb-compact .wb-page-wrap { margin-bottom: 6px; text-align: center; }
.wb-compact .wb-page-cap { margin-bottom: 3px; font-size: 11px; }
.wb-compact .wb-page-stage { display: inline-block; }
.wb-compact .wb-page {
    width: auto;
    max-width: 100%;
    max-height: calc(100vh - 190px);
    margin: 0 auto;
}
.wb-compact .wb-legend { margin-top: 3px; font-size: 11px; gap: 6px 12px; }

/* 右栏:判定卡全面压缩 */
.wb-compact .wb-adj-card { padding: 10px 14px; }
.wb-compact .wb-row-head { margin-bottom: 4px; gap: 6px 10px; }
.wb-compact .wb-task { font-size: 12.5px; margin: 2px 0; line-height: 1.45; }
.wb-compact .wb-doctype {
    padding: 5px 8px;
    margin: 3px 0;
    font-size: 12px;
    line-height: 1.4;
}
.wb-compact .wb-adj-verdict { padding: 7px 10px; margin: 5px 0; }
.wb-compact .wb-adj-kv { margin: 3px 0; gap: 5px 9px; }
.wb-compact .wb-gates { gap: 4px; margin: 5px 0; }
.wb-compact .wb-gate { padding: 1px 7px; font-size: 10.5px; }
.wb-compact .wb-badge { padding: 1px 8px; }
.wb-compact .wb-evidence { margin: 5px 0; }
.wb-compact .wb-evidence > summary { padding: 5px 10px; font-size: 12px; }
.wb-compact .wb-evidence > div,
.wb-compact .wb-evidence > section { padding: 6px 10px; font-size: 12px; }
.wb-compact .wb-vision-suggest { padding: 3px 8px; font-size: 12px; margin: 3px 0; }

/* 决策表单:一屏内收完 */
.wb-compact .wb-decide { padding: 8px 12px; margin-top: 6px; }
.wb-compact .wb-decide-row { margin: 5px 0; gap: 6px; }
.wb-compact .wb-radio { padding: 4px 11px; font-size: 12px; }
.wb-compact .wb-corr { padding: 5px 9px; min-width: 160px; font-size: 12.5px; }
.wb-compact .wb-rationale {
    min-height: 44px;
    padding: 6px 10px;
    font-size: 12.5px;
    line-height: 1.5;
    margin: 5px 0;
}
.wb-compact .wb-issue-chips { gap: 5px; margin: 4px 0; }
.wb-compact .wb-issue-chip { padding: 2px 9px; font-size: 11px; }
.wb-compact .wb-adjudicator { padding: 4px 9px; min-width: 120px; font-size: 12px; }
.wb-compact .wb-btn { padding: 5px 14px; font-size: 12.5px; }
.wb-compact .wb-current, .wb-compact .wb-orphan, .wb-compact .wb-policy {
    padding: 5px 10px; font-size: 12px; margin: 5px 0;
}

/* 底栏再薄一点 */
.wb-compact .wb-adj-nav { padding: 6px 2px; margin-top: 8px; }
.wb-compact .wb-nav-btn { padding: 5px 12px; font-size: 12.5px; }
.wb-compact .wb-footer { display: none; }  /* 快照 id 在判定卡里已有,页脚让位 */

/* 一键快路:主流量「原值正确」的显眼入口。蓝 = 人的 action(纪律:
human-confirmed 不用绿) */
.wb-quick-ok {
    display: block;
    width: 100%;
    margin: 0 0 6px;
    padding: 7px 14px;
    font-size: 13px;
    font-weight: 600;
    color: var(--wb-action);
    background: var(--wb-action-wash);
    border: 1.5px solid var(--wb-action);
    border-radius: var(--wb-radius-sm);
    text-align: center;
    transition: background 0.15s ease, color 0.15s ease;
}
.wb-quick-ok:hover { background: var(--wb-action); color: #fff; }
.wb-compact .wb-quick-ok { padding: 5px 12px; font-size: 12.5px; margin-bottom: 4px; }
/* 「而且这条不该进队列」:同样是一键,但它是次要分支 —— 弱化成描边,
   免得和主快路抢眼;两个按钮长得一样会让人随手点错,而点错的心码
   正是会喂给 mining 的那个字段 */
.wb-quick-fp {
    font-weight: 500;
    color: var(--wb-muted);
    background: transparent;
    border-color: var(--wb-line);
}
.wb-quick-fp:hover { background: var(--wb-muted); color: #fff; }

/* 改进循环页:原话是主体,模型草稿必须看起来像草稿 —— 它和系统发现
   长得一样,人就会当成系统发现,那正是这一层最该避免的事 */
.wb-improve { max-width: 860px; }
.wb-imp-intro { color: var(--wb-muted); font-size: 13px; line-height: 1.6; }
.wb-imp-h { font-size: 14px; margin: 22px 0 8px; }
.wb-imp-danger { color: #a3341f; }
.wb-imp-empty { color: var(--wb-muted); font-size: 13px; }
.wb-imp-cohort, .wb-imp-sug, .wb-imp-overturn, .wb-imp-cand {
    border: 1px solid var(--wb-line);
    border-radius: var(--wb-radius-sm);
    padding: 10px 12px;
    margin: 0 0 8px;
    font-size: 13px;
}
.wb-imp-overturn { border-color: #a3341f; background: rgba(163, 52, 31, 0.05); }
.wb-imp-sug { border-style: dashed; }
.wb-imp-notes { margin: 6px 0 0; padding-left: 18px; line-height: 1.65; }
.wb-imp-note { margin: 4px 0; line-height: 1.6; }
.wb-imp-meta { color: var(--wb-muted); font-size: 12px; }
.wb-imp-tag {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 11px;
    background: var(--wb-line);
    color: var(--wb-muted);
}
.wb-imp-tag.advisory { background: rgba(163, 52, 31, 0.12); color: #a3341f; }
.wb-imp-cmd {
    margin: 6px 0 0;
    padding: 8px 10px;
    background: var(--wb-line-soft);
    border-radius: var(--wb-radius-sm);
    font-size: 12px;
    white-space: pre-wrap;
    word-break: break-all;
}

/* 采纳 / 评测 / 晋升表单:模型的话只是预填,人可以改 —— 签字的是人 */
.wb-imp-form {
    margin: 10px 0 0;
    padding-top: 10px;
    border-top: 1px solid var(--wb-line-soft);
    display: flex;
    flex-direction: column;
    gap: 8px;
    align-items: flex-start;
}
.wb-imp-lbl {
    display: flex;
    flex-direction: column;
    gap: 3px;
    width: 100%;
    font-size: 12px;
    color: var(--wb-muted);
}
.wb-imp-lbl input, .wb-imp-lbl textarea {
    width: 100%;
    padding: 6px 8px;
    font: inherit;
    font-size: 13px;
    color: var(--wb-ink);
    background: var(--wb-bg);
    border: 1px solid var(--wb-line);
    border-radius: var(--wb-radius-sm);
    box-sizing: border-box;
}
.wb-imp-lbl textarea { resize: vertical; line-height: 1.5; }
.wb-imp-cand-box {
    border: 1px solid var(--wb-line);
    border-radius: var(--wb-radius-sm);
    padding: 12px 14px;
    margin: 10px 0;
}
.wb-imp-eval { margin: 8px 0; border-collapse: collapse; font-size: 13px; }
.wb-imp-eval td { padding: 3px 10px 3px 0; }
.wb-imp-eval td:first-child { color: var(--wb-muted); }
/* 门禁判定:通过与拒绝一样醒目 —— 拒绝的理由是这页最该被读到的东西 */
.wb-imp-gate {
    margin: 8px 0;
    padding: 8px 10px;
    border-radius: var(--wb-radius-sm);
    font-size: 13px;
}
.wb-imp-gate.ok { background: rgba(31, 122, 68, 0.09); color: #1f7a44; }
.wb-imp-gate.refuse { background: rgba(163, 52, 31, 0.09); color: #a3341f; }
.wb-btn.danger { background: #a3341f; }
.wb-btn.danger:hover:not(:disabled) { background: #862a19; }

/* ── 外发批准 ──────────────────────────────────────────────────
   一张卡一份单据,一次署名一份单据。「没有人看过的字段」排在表单**之前**:
   要它先被读到,再被签字。 */
.wb-approve-card {
    border: 1px solid var(--wb-line);
    border-radius: var(--wb-radius-sm);
    padding: 12px 14px;
    margin: 10px 0;
}
.wb-approve-card h3 { margin: 0 0 4px; font-size: 14px; }
.wb-approve-unreviewed {
    margin: 6px 0;
    font-size: 13px;
    color: #8a5a12;
    background: rgba(196, 132, 27, 0.10);
    padding: 7px 10px;
    border-radius: var(--wb-radius-sm);
}
.wb-approve-stale {
    margin: 6px 0;
    font-size: 13px;
    color: #a3341f;
}
.wb-approve-done {
    margin: 6px 0;
    font-size: 13px;
    color: #1f7a44;
}

/* ── 改进循环:AP 版式 ──────────────────────────────────────────
   叙事顺序,不是数据结构顺序。工程标识收进 .wb-imp-tech 折叠区。 */
.wb-imp-lead {
    font-size: 14.5px;
    line-height: 1.75;
    color: var(--wb-ink);
    max-width: 62ch;
    margin: 4px 0 26px;
}
.wb-imp-sub { color: var(--wb-muted); font-size: 13px; line-height: 1.7;
              max-width: 62ch; margin: 0 0 14px; }
/* 推翻记录:安全方向,给它最强的视觉重量 */
.wb-imp-alert {
    border: 1px solid #a3341f;
    border-left-width: 4px;
    border-radius: var(--wb-radius-sm);
    background: rgba(163, 52, 31, 0.05);
    padding: 14px 18px;
    margin: 0 0 26px;
}
.wb-imp-alert h3 { margin: 0 0 6px; font-size: 14.5px; color: #a3341f; }
.wb-imp-alert p { margin: 0 0 10px; font-size: 13px; line-height: 1.7;
                  color: var(--wb-ink); max-width: 60ch; }
.wb-imp-quote {
    margin: 3px 0 0 2px;
    padding-left: 10px;
    border-left: 2px solid var(--wb-line);
    color: var(--wb-ink);
    line-height: 1.6;
}
.wb-imp-plainlist { margin: 6px 0 0; padding-left: 20px; line-height: 1.8;
                    font-size: 13px; }
/* 一张建议卡 / 一个待定改动 */
.wb-imp-sug, .wb-imp-cand-box {
    border: 1px solid var(--wb-line);
    border-radius: var(--wb-radius-sm);
    padding: 16px 18px;
    margin: 0 0 16px;
    background: var(--wb-bg);
}
.wb-imp-sug-title {
    font-size: 15px;
    font-weight: 600;
    line-height: 1.5;
    margin-bottom: 8px;
    max-width: 58ch;
}
.wb-imp-badges { display: flex; gap: 6px; margin-bottom: 10px; }
.wb-imp-why { font-size: 13.5px; line-height: 1.75; margin: 6px 0;
              max-width: 62ch; }
.wb-imp-k { color: var(--wb-muted); font-size: 12px; display: block; }
.wb-imp-note-sm { color: var(--wb-muted); font-size: 12.5px; line-height: 1.65;
                  margin: 6px 0 0; max-width: 60ch; }
.wb-imp-quotes, .wb-imp-tech, .wb-imp-notes-box {
    margin-top: 10px;
    font-size: 12.5px;
}
.wb-imp-quotes summary, .wb-imp-tech summary, .wb-imp-notes-box summary {
    cursor: pointer;
    color: var(--wb-muted);
    user-select: none;
}
.wb-imp-tech code { font-size: 11.5px; word-break: break-all;
                    color: var(--wb-muted); }
.wb-imp-notegroup { margin: 12px 0 0; }
/* 试算结果:改善与代价并排 */
.wb-imp-evalbox {
    margin: 14px 0;
    padding: 12px 14px;
    background: var(--wb-line-soft);
    border-radius: var(--wb-radius-sm);
}
.wb-imp-was { color: var(--wb-muted); }
.wb-imp-gate.warn { background: rgba(163, 52, 31, 0.07); color: #8a4b20; }


/* 页码切换(多页文档):小签,不占行高 */
.wb-page-tabs { display: inline-flex; gap: 4px; margin-left: 10px; }
.wb-page-tab {
    font-family: var(--wb-font-mono);
    font-size: 11px;
    color: var(--wb-muted);
    background: var(--wb-surface);
    border: 1px solid var(--wb-line);
    border-radius: 5px;
    padding: 1px 8px;
    text-decoration: none;
}
.wb-page-tab:hover { border-color: var(--wb-ink); text-decoration: none; }
.wb-page-tab.active {
    color: var(--wb-action);
    border-color: var(--wb-action-line);
    background: var(--wb-action-wash);
}

/* 入队原因:判定卡顶部,一眼可见;阻断级用红,其余用中性面 */
.wb-why {
    border: 1px solid var(--wb-line);
    background: var(--wb-surface);
    border-radius: var(--wb-radius-sm);
    padding: 7px 11px;
    font-size: 12.5px;
    line-height: 1.5;
    color: var(--wb-ink-soft);
    margin: 6px 0;
}
.wb-why b { color: var(--wb-ink); margin-right: 8px; }
.wb-why.blocked {
    border-color: var(--wb-block-line);
    background: var(--wb-block-wash);
    color: var(--wb-block);
}
.wb-why.blocked b { color: var(--wb-block); }
.wb-compact .wb-why { padding: 5px 10px; font-size: 12px; margin: 4px 0; }
"""
