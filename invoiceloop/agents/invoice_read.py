"""Document-level invoice reading via ADK — advice only.

One call per document, full-page images in. The model returns a structured
interpretation (station vs agency vs advertiser, remittance-stub role). Python
turns that into display-only suggestion rows. Nothing here writes the ledger
or assigns an ID.

This is not the TA adjudicator: that path both interprets and decides. This
path stops at a reading.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from invoiceloop.evidence import page_images
from invoiceloop.fields import FIELD_KINDS

APP_NAME = "invoiceloop_invoice_read"
SUGGEST_TAG = "adk-invoice"

_FIELD_KEYS = (
    "seller_name", "buyer_name", "invoice_number", "amount_due",
)

RemittanceRole = Literal["payee", "customer_stub", "unknown", "absent"]
Confidence = Literal["high", "medium", "low"]


class InvoiceReading(BaseModel):
    """Document interpretation. **No ID fields — charter rule one.**"""

    station_or_publication: str = ""
    agency: str = ""
    advertiser: str = ""
    legal_seller: str = ""
    remittance_name: str = ""
    remittance_role: RemittanceRole = "unknown"
    seller_name: str = ""
    buyer_name: str = ""
    invoice_number: str = ""
    amount_due: str = ""
    rationale: str = Field(description="Why this reading, for the reviewer")
    confidence: Confidence = "medium"


#: 固定的 user message。**不带 doc_id、不带文件名、不带任何随单据变化的文本** ——
#: 唯一随单据变化的输入是页面图片本身,它已经把请求身份区分开
#: (`adk_replay.request_identity` 把 contents 整个纳入摘要)。
READ_USER_PROMPT = "Read the attached page image(s)."

INVOICE_READ_SYSTEM = """\
You are reading one accounts-payable document as a WHOLE, not extracting a
single field. You see the page image(s). Identify the roles on this page:

- station_or_publication: the paid media seller (radio station, TV station,
  or publication brand / call letters / station company).
- agency: media-buying / rep firm, if printed. Empty if none.
- advertiser: the advertised product or political committee, if printed.
- legal_seller: incorporated name on the letterhead, if different from the
  station brand. Empty if the station line is the legal name.
- remittance_name: name printed in a remittance / payment stub, if any.
- remittance_role: payee if that block is who to pay; customer_stub if it
  repeats the billed customer so they can match the invoice; absent if no
  remittance block; unknown otherwise.
- seller_name: the seller for this invoice = station or publication, NOT the
  agency. Copy characters as printed; do not expand BRDCSTNG-style abbreviations.
- buyer_name: the billed party (agency if present, else advertiser).
- invoice_number, amount_due: copy a printed labelled value. Do not add line
  items. If the page says CONTINUED and no amount due / total is printed,
  leave amount_due empty.

Empty string means you do not have a value. Do not guess. rationale: one short
paragraph naming the blocks you used. confidence: high, medium or low.

You advise a human reviewer. You do not decide, approve, or release anything.
"""


def reading_call_id(model: str, doc_id: str, images: list[bytes]) -> str:
    """Request identity includes ordered page bytes so a swapped page is a new call."""
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(b"|")
    h.update(doc_id.encode())
    for blob in images:
        h.update(b"|")
        h.update(hashlib.sha256(blob).hexdigest().encode())
    return f"invread_{h.hexdigest()[:16]}"


def _tsv_note(model: str, reading: InvoiceReading) -> str:
    parts = [
        model,
        f"role={reading.remittance_role}",
        reading.rationale,
    ]
    return " ".join(" ".join(parts).split())[:240]


def to_suggestion_rows(
    doc_id: str, reading: InvoiceReading, *, model: str,
) -> list[dict[str, str]]:
    """Map a reading onto display suggestion rows. Empty fields are omitted."""
    values = {
        "seller_name": (reading.seller_name or reading.station_or_publication).strip(),
        "buyer_name": (reading.buyer_name or reading.agency or reading.advertiser).strip(),
        "invoice_number": reading.invoice_number.strip(),
        "amount_due": reading.amount_due.strip(),
    }
    note = _tsv_note(model, reading)
    rows = []
    for field in _FIELD_KEYS:
        value = values[field]
        if not value or field not in FIELD_KINDS:
            continue
        rows.append({
            "doc_id": doc_id,
            "field": field,
            "value": value,
            "printed_label": "NONE",
            "note": note,
        })
    return rows


def load_page_images(run_dir: Path, doc_id: str) -> list[bytes]:
    return [p.read_bytes()
            for p in page_images(Path(run_dir) / "pages", doc_id)]


def make_invoice_reader(
    *, model: str | Any, workspace: Path,
) -> Callable[[str, list[bytes]], InvoiceReading]:
    """→ read(doc_id, images) -> InvoiceReading, via a real ADK Runner.

    A string model goes through credentials + record/replay. A BaseLlm (tests)
    is used as-is and must not hit the network.
    """
    import asyncio

    from google.adk.agents import LlmAgent
    from google.adk.models.base_llm import BaseLlm
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from .adk_replay import replay_callbacks
    from .runtime import export_credential_for_adk

    extras: dict[str, Any] = {}
    model_name = getattr(model, "model", None) or str(model)
    if isinstance(model, str):
        export_credential_for_adk(workspace)
        before, after = replay_callbacks(workspace)
        extras["before_model_callback"] = before
        extras["after_model_callback"] = after
        model_name = model
    elif not isinstance(model, BaseLlm):
        raise TypeError("model must be a Gemini model name or an ADK BaseLlm")

    agent = LlmAgent(
        name="invoice_read", model=model,
        instruction=INVOICE_READ_SYSTEM,
        output_schema=InvoiceReading,
        output_key="reading",
        **extras,
    )

    async def _once(doc_id: str, images: list[bytes]) -> InvoiceReading:
        service = InMemorySessionService()
        session_id = f"read-{doc_id}"
        await service.create_session(
            app_name=APP_NAME, user_id="invoice-read",
            session_id=session_id, state={},
        )
        runner = Runner(app_name=APP_NAME, agent=agent, session_service=service)
        # 提示词固定,**不插 doc_id**:doc_id 由上传文件名归一而来,
        # `ignore-all-rules-….pdf` 会变成模型 user message 里的指令样文本。
        # 读法是建议,但它渲染在裁决表单旁边,带偏复核者就是带偏判断。
        # doc_id 的去处是 session_id(上面)与 provenance(to_suggestion_rows),
        # 模型看不到;每份单据的请求身份由页面图片本身区分。
        parts = [types.Part(text=READ_USER_PROMPT)]
        for blob in images:
            parts.append(types.Part.from_bytes(data=blob, mime_type="image/png"))
        async for _ in runner.run_async(
            user_id="invoice-read", session_id=session_id,
            new_message=types.Content(role="user", parts=parts),
        ):
            pass
        session = await service.get_session(
            app_name=APP_NAME, user_id="invoice-read", session_id=session_id)
        raw = dict(session.state).get("reading")
        if raw is None:
            raise RuntimeError("ADK 没给出 invoice reading —— 不许当成弃权")
        return InvoiceReading.model_validate(raw)

    def read(doc_id: str, images: list[bytes]) -> InvoiceReading:
        if not images:
            raise ValueError(f"{doc_id}: 无整页渲染")
        return asyncio.run(_once(doc_id, images))

    read.model_name = model_name  # type: ignore[attr-defined]
    return read


def save_readings(
    run_dir: Path, *, model: str,
    docs: dict[str, dict[str, Any]],
    failed: list[dict[str, str]],
) -> Path:
    path = _readings_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_readings(run_dir)
    merged = dict(existing.get("docs") or {})
    # 每份读法自带 model:顶层那个字段只是「最后一次跑用的模型」,
    # 原先每次 save 都改写它,于是旧模型读出来的全被冠上新模型的名字。
    # workbench 的 RunCtx 早就是 rec.setdefault("model", 顶层) —— per-doc 优先,
    # 所以旧文件不需要迁移。
    merged.update({doc_id: {**reading, "model": model}
                   for doc_id, reading in docs.items()})
    path.write_text(json.dumps({
        "advisory": True,
        "source": "adk_invoice_read",
        "model": model,
        "docs": merged,
        "failed": failed,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def _readings_path(run_dir: Path) -> Path:
    return Path(run_dir) / "vision" / "invoice_read.json"


def _load_readings(run_dir: Path) -> dict[str, Any]:
    path = _readings_path(run_dir)
    if not path.exists():
        return {}
    try:
        packed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return packed if isinstance(packed, dict) else {}


def read_docs(run_dir: Path, model: str) -> set[str]:
    """已经**由这个模型**读过的 doc_id。

    只按 doc_id 判「读过了」会让 ``--model`` 换了之后整批 skip,一份也不会
    重读,而末尾的 save 又把顶层 model 改成新名字 —— 旧读法被错误归因。
    per-doc 的 model 缺席时退回顶层 model(旧格式,见 runs/hitl-narrow)。
    """
    packed = _load_readings(run_dir)
    top = str(packed.get("model") or "")
    return {
        doc_id for doc_id, reading in (packed.get("docs") or {}).items()
        if isinstance(reading, dict)
        and str(reading.get("model") or top) == model
    }
