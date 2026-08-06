# SEALED-2 抽取状态(待预算授权)

名单已冻结:`docs/sealed2_doc_list.json`(drand round 6352483,
context=`sealed2-v1`,与暴露清单 / SEALED-1 / 旧 heldout 零重叠,pool=5131)。

**尚未授权 DWS 抽取。** 在明确预算(~5k credits / 200 次双模式调用)前,
禁止执行:

```bash
python3 -m invoiceloop sealed extract --workspace runs/sealed2-workspace
INVOICELOOP_CORPUS=runs/sealed2-workspace python3 -m invoiceloop run \
  --out runs/sealed2 --doc-ids <docs/sealed2_doc_list.json>
```

抽取并评测通过后,在目标 improve workspace 放置资格标记:

```bash
python3 -c "from pathlib import Path; from invoiceloop.improve import mark_sealed2_qualified; \
  print(mark_sealed2_qualified(Path('runs/hitl-sealed')))"
```

此后 scored promote 的 `basis` 升为 `sealed2_qualified`(见 `improve.promote`)。
