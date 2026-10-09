"""将 OCR 文档结果序列化为与协议无关的 JSON 兼容载荷。

服务层只持久化基础类型，HTTP 适配器可再使用 Pydantic 校验；模块不依赖 API，
保证工作进程和队列进程可以独立导入。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from core.document_reading import block_line_views, block_reading_lines, document_orientation, page_reading_lines
from core.document_payload import original_ocr_text, table_payload, text_confidence_source


class TextLinePayload(TypedDict):
    """API/worker 共享的文本行序列化字段。"""

    text: str
    source_text: str | None
    translated_text: str | None
    confidence: float
    confidence_source: str
    x1: int
    y1: int
    x2: int
    y2: int
    font_size: float
    language: str
    language_confidence: float
    script_counts: dict[str, int]
    engineering_review: dict[str, Any]


class LayoutRegionPayload(TypedDict):
    """API/worker 共享的版面区域及其文本行字段。"""

    layout_type: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int
    text_lines: list[TextLinePayload]
    image_overlay_text: list[TextLinePayload]
    table: dict | None
    formula_latex: str | None


def document_blocks(result: Any) -> list:
    """按页面顺序展平所有 LayoutBlock，供统计和响应序列化使用。"""

    return [block for page in result.pages for block in page.blocks]


def document_text(result: Any) -> str:
    """按阅读顺序拼接去重后的可见原文/译文。"""

    return "\n".join(line.display_text for line in document_output_lines(result))


def document_output_lines(result: Any) -> list:
    """收集页面可见文本行，并依据文本和坐标删除空间重复项。"""

    return [line for page in result.pages for line in page_reading_lines(page)]


def serialize_text_line(line: Any) -> TextLinePayload:
    """将领域文本行转换为兼容历史 API 的扁平字段结构。"""

    return {
        "text": line.display_text,
        "source_text": original_ocr_text(line),
        "translated_text": line.translated_text or None,
        "confidence": round(line.confidence, 3),
        "confidence_source": text_confidence_source(line),
        "x1": line.bbox[0],
        "y1": line.bbox[1],
        "x2": line.bbox[2],
        "y2": line.bbox[3],
        "font_size": round(line.font_size, 1),
        "language": str(getattr(line, "language", "unknown") or "unknown"),
        "language_confidence": round(
            float(getattr(line, "language_confidence", 0.0) or 0.0),
            4,
        ),
        "script_counts": dict(getattr(line, "script_counts", {}) or {}),
        "engineering_review": (getattr(line, "repair_audit", {}) or {}).get("engineering_review", {}),
    }


def serialize_region_results(blocks: Any) -> list[LayoutRegionPayload]:
    """序列化版面块，但不让 worker 依赖 FastAPI/Pydantic schema。"""

    results: list[LayoutRegionPayload] = []
    for block in blocks:
        overlay_lines = block_line_views(block, overlay=True)
        results.append(
            {
                "layout_type": block.block_type.value,
                "confidence": round(block.confidence, 3),
                "x1": block.bbox[0],
                "y1": block.bbox[1],
                "x2": block.bbox[2],
                "y2": block.bbox[3],
                "text_lines": [serialize_text_line(line) for line in block_line_views(block)],
                "image_overlay_text": [serialize_text_line(line) for line in overlay_lines],
                "table": table_payload(block),
                "formula_latex": getattr(block, "formula_latex", None),
            }
        )
    return results


def page_fallback_reasons(metadata: dict[str, Any]) -> list[str]:
    """按出现顺序提取并去重可公开的降级原因。"""

    reasons: list[str] = []
    layout = metadata.get("layout_engine")
    if isinstance(layout, dict):
        reason = str(layout.get("layout_fallback_reason") or "")
        if reason and reason != "ok":
            reasons.append(reason)
        if (layout.get('source_ocr_inventory') or {}).get('unresolved_regions'):
            reasons.append('primary_ocr_word_unresolved')
    preflight = metadata.get("ocr_preflight")
    if isinstance(preflight, dict) and preflight.get("skip_ocr"):
        reason = str(preflight.get("reason") or "ocr_preflight")
        if reason not in reasons:
            reasons.append(reason)
    structure = metadata.get("structure_detection")
    if isinstance(structure, dict) and structure.get("figures_skipped"):
        reason = str(structure.get("figures_skip_reason") or "structure_skipped")
        if reason and reason not in reasons:
            reasons.append(reason)
    digit_review = metadata.get("arabic_digit_diagnostics") or {}
    if digit_review.get("needs_review"):
        reasons.append("arabic_digit_review")
    for field, reason in (('source_region_review', 'source_ocr_region_unresolved'),
                          ('source_numeric_review', 'source_numeric_review'),
                          ('engineering_review', 'engineering_character_review')):
        if (metadata.get(field) or {}).get('needs_review'):
            reasons.append(reason)
    if document_orientation(metadata).get("needs_review"):
        reasons.append("document_orientation_review")
    if metadata.get("status") == "failed" and metadata.get("error"):
        reasons.append("page_failed")
    return reasons


def serialize_page_results(result: Any) -> list[dict[str, Any]]:
    """序列化页面/帧，同时保留源页索引和输入格式身份。"""

    pages: list[dict[str, Any]] = []
    for page in getattr(result, "pages", []) or []:
        metadata = getattr(page, "metadata", {}) or {}
        quality = metadata.get("quality") if isinstance(metadata.get("quality"), dict) else {}
        timing = metadata.get("timing") if isinstance(metadata.get("timing"), dict) else {}
        language = (
            metadata.get("text_language") if isinstance(metadata.get("text_language"), dict) else {}
        )
        pages.append(
            {
                "page_number": int(getattr(page, "page_number", 0) or 0),
                "frame_index": metadata.get("frame_index"),
                "page_index": metadata.get("page_index"),
                "source_page_index": metadata.get("source_page_index"),
                "source_format": metadata.get("source_format"),
                "status": str(metadata.get("status") or "completed"),
                "error": metadata.get("error"),
                "width": float(getattr(page, "width", 0) or 0),
                "height": float(getattr(page, "height", 0) or 0),
                "text": "\n".join(line.display_text for line in page_reading_lines(page)),
                "arabic_digit_diagnostics": metadata.get("arabic_digit_diagnostics") or {},
                "source_region_review": metadata.get("source_region_review") or {},
                "source_numeric_review": metadata.get("source_numeric_review") or {},
                "engineering_review": metadata.get("engineering_review") or {},
                "source_ocr_inventory": (metadata.get("layout_engine") or {}).get("source_ocr_inventory") or {},
                "document_orientation": document_orientation(metadata),
                "ocr_configuration": (metadata.get("layout_engine") or {}).get("ocr_configuration") or {},
                "language": language,
                "quality": quality,
                "timing": timing,
                "fallback_reasons": page_fallback_reasons(metadata),
                "regions": serialize_region_results(getattr(page, "blocks", []) or []),
            }
        )
    return pages


def response_stats(blocks: Any, *, result: Any = None) -> dict[str, float | int]:
    """汇总区域数量、去重文本行数量和平均 OCR 置信度。"""

    if result is not None:
        output_lines = document_output_lines(result)
    else:
        from types import SimpleNamespace
        output_lines = page_reading_lines(SimpleNamespace(blocks=blocks))
    total_lines = len(output_lines)
    average = (
        round(sum(line.confidence for line in output_lines) / total_lines, 3)
        if total_lines
        else 0.0
    )
    return {
        "region_count": len(blocks),
        "line_count": total_lines,
        "avg_confidence": average,
    }


def result_page_timings(result: Any) -> list[dict[str, Any]]:
    """公开页面耗时、重试、语言和降级诊断信息。"""

    timings: list[dict[str, Any]] = []
    for page in getattr(result, "pages", []) or []:
        metadata = getattr(page, "metadata", {}) or {}
        page_timing = metadata.get("timing") if isinstance(metadata.get("timing"), dict) else {}
        quality = metadata.get("quality") if isinstance(metadata.get("quality"), dict) else {}
        timings.append(
            {
                "page_number": getattr(page, "page_number", 0),
                "input_kind": getattr(getattr(page, "input_kind", None), "value", ""),
                "timing": page_timing,
                "line_count": quality.get("line_count", 0),
                "char_count": quality.get("char_count", 0),
                "avg_confidence": quality.get("avg_confidence", 0.0),
                "used_retry": bool(metadata.get("used_retry", False)),
                "used_layout": bool(metadata.get("used_layout", False)),
                "render_dpi": metadata.get("render_dpi"),
                "ocr_mode_policy": metadata.get("ocr_mode_policy") or {},
                "adaptive_retry": metadata.get("adaptive_retry") or {},
                "frame_index": metadata.get("frame_index"),
                "page_index": metadata.get("page_index"),
                "source_page_index": metadata.get("source_page_index"),
                "source_format": metadata.get("source_format"),
                "status": metadata.get("status", "completed"),
                "error": metadata.get("error"),
                "language": metadata.get("text_language") or {},
                "fallback_reasons": page_fallback_reasons(metadata),
            }
        )
    return timings


def common_ocr_result_fields(
    result: Any,
    *,
    conversion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成同步与异步 OCR 输出共用的 JSON 字段。"""

    fields = {
        "ocr_language": result.metadata.get("ocr_language"),
        "ocr_mode": result.metadata.get("ocr_mode"),
        "ocr_scene": result.metadata.get("ocr_scene", "general"),
        "vlm_fallback": result.metadata.get("vlm_fallback", "off"),
        "engineering_status": result.metadata.get("engineering_status"),
        "ocr_mode_policy": result.metadata.get("ocr_mode_policy"),
        "quality": result.metadata.get("quality"),
        "page_timings": result_page_timings(result),
        "ocr_model": result.metadata.get("ocr_model"),
        "text_language": result.metadata.get("text_language"),
        "pages": serialize_page_results(result),
        "errors": result.errors,
    }
    if conversion is not None:
        fields["conversion"] = conversion
    if (result.metadata.get("ocr_scene") == "engineering" and (not result.pages or result.errors)) or any((page.metadata.get("arabic_digit_diagnostics") or {}).get("needs_review")
           or (page.metadata.get('source_region_review') or {}).get('needs_review')
           or (page.metadata.get('source_numeric_review') or {}).get('needs_review')
           or (page.metadata.get('engineering_review') or {}).get('needs_review')
           or ((page.metadata.get('layout_engine') or {}).get('source_ocr_inventory') or {}).get('unresolved_regions')
           or document_orientation(page.metadata).get("needs_review")
           for page in result.pages):
        fields["needs_review"] = True
        fields["disposition"] = "review"
    return fields


def collect_image_texts(result: Any) -> tuple[list, list]:
    """收集图片文本行及与原文不同的译文，供重绘阶段替换。"""

    text_lines = []
    replacements = []
    for page in result.pages:
        for block in page.blocks:
            candidates = (
                block.image.overlay_text
                if block.image is not None and block.image.overlay_text
                else block.text_lines
                if block.block_type.value != "table"
                else []
            )
            for line in candidates:
                if not _has_real_translation(line):
                    continue
                text_lines.append(line)
                replacements.append(line.translated_text)
    return text_lines, replacements


def download_filename(task: Any, ext: str) -> str:
    """按历史规则生成安全的任务下载文件名。"""

    stem = Path(task.filename or "document").stem or "document"
    stem = "".join(
        character
        if character.isalnum() or character in ("-", "_", " ", ".", "(", ")", "[", "]")
        else "_"
        for character in stem
    )
    stem = stem.strip(" ._")[:120] or "document"
    suffix = "translated" if task.params.get("task_type") == "translate" else "ocr"
    return f"{stem}_{suffix}{ext}"


def _block_output_lines(block: Any) -> list:
    """合并普通文本行和图像 overlay 文本行。"""

    return block_reading_lines(block)


def _has_real_translation(line: Any) -> bool:
    """判断文本行是否存在非空且不同于原文的真实译文。"""

    translated = (getattr(line, "translated_text", "") or "").strip()
    if not translated:
        return False
    source = (getattr(line, "source_text", "") or getattr(line, "text", "") or "").strip()
    return translated != source


__all__ = [
    "LayoutRegionPayload",
    "TextLinePayload",
    "collect_image_texts",
    "common_ocr_result_fields",
    "document_blocks",
    "document_output_lines",
    "document_text",
    "download_filename",
    "page_fallback_reasons",
    "response_stats",
    "result_page_timings",
    "serialize_page_results",
    "serialize_region_results",
    "serialize_text_line",
]
