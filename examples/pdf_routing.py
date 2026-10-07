"""Selected PDF route and risk policy from PP-V5. Optional PyMuPDF for real files."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import logging
logger=logging.getLogger(__name__)
DIRECT_TEXT_MIN_CHARS_PER_PAGE=40
DIRECT_TEXT_MIN_PAGES_RATIO=0.6
DEFAULT_SCAN_WARN_PAGES=6
DEFAULT_SCAN_LONG_TASK_PAGES=20
DEFAULT_SCAN_MAX_SYNC_PAGES=5

@dataclass(frozen=True)
class PdfConversionDecision:
    """描述 PDF 最终采用的转换路径及支撑该决策的文本统计。"""
    mode: str
    reason: str
    page_count: int = 0
    text_pages: int = 0
    total_text_chars: int = 0

    def to_dict(self, *, settings: Any | None=None) -> dict[str, Any]:
        """序列化路由决定，并附加基于当前配置计算的扫描件风险。"""
        data: dict[str, Any] = {'mode': self.mode, 'reason': self.reason, 'page_count': self.page_count, 'text_pages': self.text_pages, 'total_text_chars': self.total_text_chars}
        data.update(pdf_scan_risk(self, settings=settings).to_dict())
        return data

@dataclass(frozen=True)
class PdfScanRisk:
    """面向 API/UI 的扫描 PDF 耗时风险与同步执行建议。"""
    estimated_ocr_pages: int
    is_scanned_pdf: bool
    time_level: str
    sync_recommended: bool
    max_sync_pages: int
    warn_pages: int
    long_task_pages: int
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """转换为保持历史字段名的可 JSON 序列化字典。"""
        return {'estimated_ocr_pages': self.estimated_ocr_pages, 'is_scanned_pdf': self.is_scanned_pdf, 'estimated_time_level': self.time_level, 'sync_recommended': self.sync_recommended, 'max_sync_pages': self.max_sync_pages, 'warn_pages': self.warn_pages, 'long_task_pages': self.long_task_pages, 'warnings': list(self.warnings)}

def _settings_value(settings: Any | None, name: str, default: int) -> int:
    """读取页数阈值配置并容错转换为整数。"""
    if settings is None:
        return default
    try:
        return int(getattr(settings, name, default) or default)
    except (TypeError, ValueError):
        return default

def pdf_scan_risk(decision: PdfConversionDecision, *, settings: Any | None=None) -> PdfScanRisk:
    """根据路由决策和可配置页数阈值评估 OCR 工作量。

    阈值会被容错转换为整数；返回值同时给出耗时级别、同步建议和用户可读告警。
    """
    warn_pages = _settings_value(settings, 'PDF_SCAN_WARN_PAGES', DEFAULT_SCAN_WARN_PAGES)
    long_task_pages = _settings_value(settings, 'PDF_SCAN_LONG_TASK_PAGES', DEFAULT_SCAN_LONG_TASK_PAGES)
    max_sync_pages = _settings_value(settings, 'PDF_SCAN_MAX_SYNC_PAGES', DEFAULT_SCAN_MAX_SYNC_PAGES)
    estimated_ocr_pages = 0
    if decision.mode == 'ocr' and decision.reason != 'not_pdf':
        estimated_ocr_pages = max(int(decision.page_count or 0) - int(decision.text_pages or 0), 0)
    is_scanned_pdf = estimated_ocr_pages > 0
    warnings: list[str] = []
    time_level = 'none'
    if is_scanned_pdf:
        time_level = 'normal'
        if estimated_ocr_pages >= warn_pages:
            time_level = 'long'
            warnings.append('scan_pdf_long_task')
        if estimated_ocr_pages >= long_task_pages:
            time_level = 'very_long'
            warnings.append('scan_pdf_very_long_task')
    sync_recommended = not is_scanned_pdf or estimated_ocr_pages <= max_sync_pages
    if is_scanned_pdf and (not sync_recommended):
        warnings.append('sync_not_recommended')
    return PdfScanRisk(estimated_ocr_pages=estimated_ocr_pages, is_scanned_pdf=is_scanned_pdf, time_level=time_level, sync_recommended=sync_recommended, max_sync_pages=max_sync_pages, warn_pages=warn_pages, long_task_pages=long_task_pages, warnings=tuple(dict.fromkeys(warnings)))

def normalize_conversion_mode(value: str | None) -> str:
    """规范化用户转换模式，并拒绝 auto、direct、ocr 之外的值。"""
    mode = str(value or 'auto').strip().lower()
    aliases = {'': 'auto', 'native': 'direct', 'text': 'direct', 'pdf': 'direct', 'pdf_to_word': 'direct', 'pdf-to-word': 'direct', 'ocr_word': 'ocr', 'ocr-word': 'ocr'}
    mode = aliases.get(mode, mode)
    if mode not in {'auto', 'direct', 'ocr'}:
        return 'auto'
    return mode

def should_auto_route_pdf_to_direct(path: Path, *, requested_mode: str | None='auto', output_format: str='docx') -> PdfConversionDecision:
    """选择 PDF 直接转换或 OCR 路径。

    显式模式优先；自动模式仅在足够多页面含有足量原生文本时选择直接转换，
    探测失败则保守返回 OCR 决策。
    """
    mode = normalize_conversion_mode(requested_mode)
    suffix = Path(path).suffix.lower()
    fmt = str(output_format or '').strip().lower()
    if suffix != '.pdf':
        return PdfConversionDecision('ocr', 'not_pdf')
    if fmt != 'docx':
        try:
            metrics = pdf_text_metrics(path)
        except Exception as exc:
            logger.debug(f'PDF scan-risk preflight failed: {exc}')
            return PdfConversionDecision('ocr', 'not_docx')
        return PdfConversionDecision('ocr', 'not_docx', page_count=metrics.page_count, text_pages=metrics.text_pages, total_text_chars=metrics.total_text_chars)
    if mode == 'direct':
        return PdfConversionDecision('direct', 'forced_direct')
    if mode == 'ocr':
        return PdfConversionDecision('ocr', 'forced_ocr')
    try:
        metrics = pdf_text_metrics(path)
    except Exception as exc:
        logger.debug(f'PDF direct-route preflight failed: {exc}')
        return PdfConversionDecision('ocr', 'preflight_failed')
    if metrics.page_count <= 0:
        return PdfConversionDecision('ocr', 'empty_pdf')
    text_page_ratio = metrics.text_pages / max(metrics.page_count, 1)
    avg_chars = metrics.total_text_chars / max(metrics.page_count, 1)
    if text_page_ratio >= DIRECT_TEXT_MIN_PAGES_RATIO and avg_chars >= DIRECT_TEXT_MIN_CHARS_PER_PAGE:
        return PdfConversionDecision('direct', 'text_pdf', page_count=metrics.page_count, text_pages=metrics.text_pages, total_text_chars=metrics.total_text_chars)
    return PdfConversionDecision('ocr', 'low_text_density', page_count=metrics.page_count, text_pages=metrics.text_pages, total_text_chars=metrics.total_text_chars)

@dataclass(frozen=True)
class PdfTextMetrics:
    """记录 PDF 总页数、有效文本页数及累计文本字符数。"""
    page_count: int
    text_pages: int
    total_text_chars: int

def pdf_text_metrics(path: Path) -> PdfTextMetrics:
    """使用 PyMuPDF 统计 PDF 原生文本覆盖率，供自动路由使用。"""
    import fitz
    page_count = 0
    text_pages = 0
    total_text_chars = 0
    with fitz.open(str(path)) as doc:
        page_count = doc.page_count
        for page in doc:
            text = page.get_text('text') or ''
            chars = len(''.join(text.split()))
            total_text_chars += chars
            if chars >= DIRECT_TEXT_MIN_CHARS_PER_PAGE:
                text_pages += 1
    return PdfTextMetrics(page_count=page_count, text_pages=text_pages, total_text_chars=total_text_chars)
