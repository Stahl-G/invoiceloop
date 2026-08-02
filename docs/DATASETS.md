# 外部数据集评估与布局(2026-08-02)

选集标准(这个项目的验收尺子):**文档图像 + 字段级标注(值+框)+ 可独立产出 OCR
+ PII 干净 + 许可可用**。答案只用于校准/验证,运行时不需要(见 README「没有答案」一节)。

下载布局(仓库外,不进 git):

```
~/Developer/invoiceloop-data/
  cuad/         CUAD_v1.zip(Zenodo 105.9MB,CC BY 4.0)
  xfund-zh/     zh.train/val.{json,zip}(GitHub release,CC BY-NC-SA 4.0 非商用)
  midv-lait/    (FTP 被本机网络拦,见下「MIDV 受阻」)
```

## 已下载(2026-08-02 实测入库,结构已抽查)

| 数据集 | 场景 | 实测内容 | 用途 |
|---|---|---|---|
| [CUAD](https://zenodo.org/records/4595826)([论文](https://arxiv.org/abs/2103.06268)) | contracts | 105.9MB zip(校验 OK):**510 份全文 txt**、master_clauses.csv、SQuAD 式 CUAD_v1.json(条款 QA,已抽查结构)、full_contract_pdf,CC BY 4.0 | **诚实边界演示**:条款能钉到页(追溯层成立),条款风险验不了(语义层不成立) |
| [XFUND-zh](https://github.com/doc-analysis/XFUND)([release](https://github.com/doc-analysis/XFUND/releases/tag/v1.0)) | forms | val 已解压:**50 篇**,实体标注含 box/text/label/words/linking(已抽查)+ 50 张 jpg;train json 已下(4.7MB),train.zip(206MB)备而未解。CC BY-NC-SA 4.0(**非商用**) | **§8b 分词边界的实测场**:非 ASCII 文字当前被分词器丢弃,这是已知限制 |

## MIDV 受阻(未下载,记录原因)

MIDV-LAIT / MIDV-2020 官方只走 FTP(`ftp://smartengines.com/...`,
[官方页](https://smartengines.ru/science/dataset/)),本机网络拦 FTP,
HTTP 镜像不存在(试过三种,均 404)。备选:TC-11 镜像(未找到 LAIT)、
Kaggle/HF 第三方镜像(许可链变浑,暂不走)。**IDs 第二幕未因此阻塞**:
可用合成证件生成(仿 SIDTD 思路)或 Symage 合成表单先顶;真要 MRZ 校验位,
MIDV-2020 的转写是必要真值,到时再解决通道。

## 其余候选(未下载,备查)

| 数据集 | 场景 | 备注 |
|---|---|---|
| [FUNSD](https://github.com/crcresearch/FUNSD) | forms | 199 张英文噪声表格,机制平移最小测试床 |
| [CORD v2](https://huggingface.co/datasets/naver-clova-ix/cord-v2) | receipts | 1,000 张,CC BY 4.0,明细→合计算术的另一域 |
| [hcfa-1500](https://huggingface.co/datasets/catochris/hcfa-1500) | claims | 500 张合成 CMS-1500,CC BY 4.0,**无框**,值级 |
| [Symage coherent-forms](https://huggingface.co/datasets/Symage/coherent-forms-1040-cms1500-i9) | claims/forms | 3,000 页带 tokens+bboxes,gated,内部商用允许 |
| [DUDE](https://zenodo.org/records/7763635) | 多域 | 4,974 文档/41k QA,分布外压力测试 |
| [FATURA](https://arxiv.org/abs/2311.11856) | invoices | 10,000 张合成发票,50 版式,版式泛化零标注成本 |
| [SIDTD](https://github.com/Oriolrt/SIDTD_Dataset) | IDs | ~74GB 合成证件+伪造,除非做防伪幕,否则不必 |

PII 纪律:IDs 只用合成/公开测试数据,不碰真人证件。
