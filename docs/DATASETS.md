# External dataset assessment and layout (2026-08-02)

Selection criteria (this project's acceptance yardstick): **document images + field-level annotations
(value + box) + independently producible OCR + PII clean + usable license**. Answers are used only for
calibration/verification, never needed at runtime (see the README's "no answers" section).

Download layout (outside the repo, not in git):

```
~/Developer/invoiceloop-data/
  cuad/         CUAD_v1.zip (Zenodo 105.9MB, CC BY 4.0)
  xfund-zh/     zh.train/val.{json,zip} (GitHub release, CC BY-NC-SA 4.0 non-commercial)
  midv-lait/    (FTP blocked by this machine's network; see "MIDV blocked" below)
```

## Downloaded (measured and ingested 2026-08-02; structure spot-checked)

| Dataset | Domain | Measured contents | Use |
|---|---|---|---|
| [CUAD](https://zenodo.org/records/4595826) ([paper](https://arxiv.org/abs/2103.06268)) | contracts | 105.9MB zip (checksum OK): **510 full-text txt files**, master_clauses.csv, SQuAD-style CUAD_v1.json (clause QA; structure spot-checked), full_contract_pdf, CC BY 4.0 | **Honesty-boundary demo**: clauses can be pinned to pages (the traceability layer holds), clause risk cannot be verified (the semantic layer does not) |
| [XFUND-zh](https://github.com/doc-analysis/XFUND) ([release](https://github.com/doc-analysis/XFUND/releases/tag/v1.0)) | forms | val extracted: **50 documents**, entity annotations with box/text/label/words/linking (spot-checked) + 50 jpgs; train json downloaded (4.7MB), train.zip (206MB) on hand but not extracted. CC BY-NC-SA 4.0 (**non-commercial**) | **Measured testbed for the §8b tokenization boundary**: non-ASCII text is currently dropped by the tokenizer — a known limitation |

## MIDV blocked (not downloaded; reasons recorded)

MIDV-LAIT / MIDV-2020 are officially FTP-only (`ftp://smartengines.com/...`,
[official page](https://smartengines.ru/science/dataset/)); this machine's network blocks FTP,
and no HTTP mirror exists (three tried, all 404). Alternatives: the TC-11 mirror (no LAIT found),
Kaggle/HF third-party mirrors (the license chain turns murky; not taken for now). **IDs act two is not
blocked by this**: synthetic ID generation (following the SIDTD idea) or Symage synthetic forms can stand
in; if MRZ check digits are truly needed, MIDV-2020's transcriptions are the necessary ground truth, and
the channel gets solved then.

## Remaining candidates (not downloaded; for reference)

| Dataset | Domain | Notes |
|---|---|---|
| [FUNSD](https://github.com/crcresearch/FUNSD) | forms | 199 noisy English forms; the minimal testbed for mechanism transfer |
| [CORD v2](https://huggingface.co/datasets/naver-clova-ix/cord-v2) | receipts | 1,000 images, CC BY 4.0; another domain for line-item → total arithmetic |
| [hcfa-1500](https://huggingface.co/datasets/catochris/hcfa-1500) | claims | 500 synthetic CMS-1500, CC BY 4.0, **no boxes**, value-level |
| [Symage coherent-forms](https://huggingface.co/datasets/Symage/coherent-forms-1040-cms1500-i9) | claims/forms | 3,000 pages with tokens+bboxes, gated, internal commercial use allowed |
| [DUDE](https://zenodo.org/records/7763635) | multi-domain | 4,974 documents / 41k QA; out-of-distribution stress test |
| [FATURA](https://arxiv.org/abs/2311.11856) | invoices | 10,000 synthetic invoices, 50 layouts; layout generalization at zero annotation cost |
| [SIDTD](https://github.com/Oriolrt/SIDTD_Dataset) | IDs | ~74GB synthetic IDs + forgeries; unnecessary unless doing an anti-forgery act |

PII discipline: for IDs, only synthetic/public test data; no real-person documents.
