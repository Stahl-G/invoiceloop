# samples/ —— 内嵌示例语料

三份 DocILE 发票 + 已存盘的 DWS 响应 + 读图作答,供
`python3 -m invoiceloop demo --out ws/` 使用。仓库自包含的底气:
评委 clone 后零 API、零外部数据就能跑通全流程。

## 内容

| 文档 | 特性 |
|---|---|
| 002e3cf97973428f905671b3 | 文字层 PDF,常规广播广告发票 |
| 003cc91637994b7d9566ac41 | 文字层 PDF,buyer_name 在版式边缘(Harry Huge 案例) |
| 046e0c4924044de09f6d9e7b | **退化扫描件**:无文字层,OCR 受阻(展品特性);DWS 把买卖双方抽反,第六轮读图作答在 vision/ 里 |

## 来源与边界

- PDF 与标注来自公开基准数据集 [DocILE](https://github.com/rossumai/docile)
  (Rossum,研究用途公开),经校准仓库 `dws-derisk` 精选三份。
- `raw/*.json` 是校准期从 Nutrient DWS API 抽取的存盘响应(先存盘后解释)。
- `vision/answers6.*.tsv` 是第六轮读图作答中这三份文档的行。
  读者 C(GPT 5.6 SOL)的整批作答在校准中因 63.1% 内容出现在别的文档
  被整体作废、不进任何判定 —— 这里保留仅作门禁机制演示,不作校准证据。
- 这些是公开基准数据,不含真人 PII;别把自己的真实发票混进这个目录。
