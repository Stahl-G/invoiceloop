"""workbench_style.py —— H1 复核工作台的全部样式。

服务器把 CSS 常量内联进每个页面:无构建、无框架、无外部资源、系统字体栈。
改样式只改这里,重跑即生效。

语义色纪律来自 briefloop-prototypes README 的 Visual System v1,必须守住
(这是产品的诚实性,不是装饰):

- 蓝 = action / info;人的裁决当前状态(accept/reject/correct/abstain)也是蓝 ——
  human-confirmed 不是 deterministic pass,不许用绿。
- 紫 = advisory:DWS / 模型来源的值与提示,永不表示"通过"。
- 绿 = 仅确定性通过(门禁 pass、bundle 校验 ok)。
- 红 = deterministic block / 阻断;.wb-rejected / .wb-blocking 沿用此色。
- 黄 = attention(warning、口径争议、两步确认的武装态)。
- 灰 = unavailable / 待复核。
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
    margin-right: auto;
    white-space: nowrap;
}
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
}
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
/* 字段裁剪图,限宽 360px */
.wb-crop { margin: 8px 0; }
.wb-crop img {
    display: block;
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
    .wb-crop img { max-width: 100%; }
    .wb-kv th { width: 130px; }
    .wb-msg-page { margin: 32px 14px; padding: 20px; }
}

/* ---- 打印:不苛求,去掉交互件即可读 ---- */
@media print {
    .wb-topbar, .wb-filters, .wb-decide, .wb-btn { display: none; }
    .wb-row, .wb-banner { box-shadow: none; }
    .wb-evidence > div, .wb-evidence > section { display: block; }
}

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { transition-duration: 0.01ms !important; }
}
"""
