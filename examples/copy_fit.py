"""Selected bounded copy-fit search. Default font widths are estimates, not Word rendering."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
import math
import re

class FontMetrics(Protocol):
    def measure(self, text: str, family: str, size: float, bold: bool, italic: bool) -> float: ...

@dataclass(frozen=True)
class CopyFitResult:
    """记录一次忠实文字框适配的最终参数和可交付状态。

    对象不可变，避免写入 VML 后审计数据又被后续候选搜索改写。
    """
    text: str
    font_size: float
    width_scale: float
    tracking_pt: float
    line_count: int
    required_width_pt: float
    fits: bool

    def to_dict(self) -> dict[str, object]:
        """转换为可写入 DOCX 元数据或质量报告的稳定字典。

        Returns:
            浮点值按三位小数舍入的 JSON 安全结构。
        """
        return {'text': self.text, 'font_size_pt': round(self.font_size, 3), 'width_scale': round(self.width_scale, 3), 'tracking_pt': round(self.tracking_pt, 3), 'line_count': self.line_count, 'required_width_pt': round(self.required_width_pt, 3), 'fits': self.fits}

def _solve_copy_fit(text: str, width_pt: float, height_pt: float, base_size: float, *, expected_lines: int=1, max_lines: int | None=None, latin_width_factor: float=0.52, font_metrics: FontMetrics | None=None, font_family: str='', is_bold: bool=False, is_italic: bool=False, line_height_factor: float=1.15) -> CopyFitResult:
    """在不静默改变文字层级的前提下把译文适配进忠实布局文字框。

    对每个候选行数，依次尝试字号、字距及从 100% 到 72% 的横向缩放；
    源字号最多降低 0.5 磅。``fits`` 是估算质量信号；调用方不得把最后一个失败候选
    当作成功适配。

    Args:
        text: 准备写入忠实文字框的源文或译文。
        width_pt: 文字框可用宽度，单位为磅。
        height_pt: 文字框可用高度，单位为磅。
        base_size: 源文排版字号。
        expected_lines: 首选的显式/源行数。
        max_lines: 允许手工拆分到的最大行数。
        latin_width_factor: 拉丁字母平均宽度相对字号的后备比例。
        font_metrics: 可选真实字体测量器。
        font_family: 实际嵌入/映射后的字体家族。
        is_bold: 是否按粗体度量。
        is_italic: 是否按斜体度量。
        line_height_factor: 估算每行垂直占用的字号倍率。

    Returns:
        包含最佳候选参数和硬适配状态的 ``CopyFitResult``。
    """
    source_size = max(3.0, min(float(base_size or 9.0), 96.0))
    available_width = max(4.0, float(width_pt) - 0.5)
    available_height = max(4.0, float(height_pt))
    requested_lines = max(1, int(expected_lines or 1))
    maximum_lines = max(requested_lines, int(max_lines or requested_lines))
    tracking_values = (0.0, -0.1, -0.2, -0.25)
    width_scales = tuple((value / 100.0 for value in range(100, 71, -2)))
    font_sizes = tuple((size for size in (source_size, source_size - 0.25, source_size - 0.5) if size >= 3.0))
    last_width = 0.0
    fitted_text = str(text or '')
    parts = fitted_text.splitlines() or [fitted_text]
    for requested in range(requested_lines, maximum_lines + 1):
        candidate_text = _manual_line_breaks(str(text or ''), requested, source_size, latin_width_factor)
        candidate_parts = candidate_text.splitlines() or [candidate_text]
        for font_size in font_sizes:
            if len(candidate_parts) * font_size * max(1.0, float(line_height_factor or 1.15)) > available_height + 0.01:
                continue
            for tracking in tracking_values:
                raw_widths = [_measure_copy_width(part, font_size, latin_width_factor, font_metrics=font_metrics, font_family=font_family, is_bold=is_bold, is_italic=is_italic) + max(0, len(part) - 1) * tracking for part in candidate_parts]
                for width_scale in width_scales:
                    last_width = max(raw_widths, default=0.0) * width_scale
                    if last_width <= available_width + 1.25:
                        return CopyFitResult(text=candidate_text, font_size=font_size, width_scale=width_scale, tracking_pt=tracking, line_count=len(candidate_parts), required_width_pt=last_width, fits=True)
        fitted_text = candidate_text
        parts = candidate_parts
    return CopyFitResult(text=fitted_text, font_size=max(3.0, source_size - 0.5), width_scale=0.72, tracking_pt=-0.25, line_count=len(parts), required_width_pt=last_width, fits=False)

def _measure_copy_width(text: str, font_size: float, latin_width_factor: float, *, font_metrics: FontMetrics | None, font_family: str, is_bold: bool, is_italic: bool) -> float:
    """测量一行文字在 Word 定位框中的保守所需宽度。

    Args:
        text: 单行源文或译文。
        font_size: 候选字号，单位为磅。
        latin_width_factor: 无真实字体时拉丁字符宽度的经验比例。
        font_metrics: 可选字体度量器。
        font_family: 候选实际字体家族。
        is_bold: 是否按粗体测量。
        is_italic: 是否按斜体测量。

    Returns:
        加入 Word/VML 渲染余量后的行宽，单位为磅。
    """
    has_cjk = any(('\u3040' <= character <= 'ヿ' or '㐀' <= character <= '鿿' or '豈' <= character <= '\ufaff' for character in text))
    word_vml_allowance = 1.06 if has_cjk else 1.04
    if font_metrics is not None and font_family:
        measured = font_metrics.measure(text, font_family, font_size, is_bold, is_italic)
        if measured > 0:
            return measured * word_vml_allowance
    return word_vml_allowance * sum((_character_width_pt(char, font_size, latin_width_factor) for char in text))

def _manual_line_breaks(text: str, line_count: int, font_size: float, latin_width_factor: float) -> str:
    """在源框允许更多行时，为译文生成稳定且宽度均衡的手工换行。

    Args:
        text: 待分行文字，可能已有显式换行。
        line_count: 目标行数。
        font_size: 用于估算单词/字符宽度的字号。
        latin_width_factor: 拉丁字符平均宽度相对字号的比例。

    Returns:
        保留已有换行并均衡新增行宽的文本；无法合法拆分时返回原文。
    """
    if line_count <= 1:
        return text
    if '\n' in text:
        source_lines = text.splitlines()
        if line_count <= len(source_lines):
            return text
        allocations = [1] * len(source_lines)
        remaining = line_count - len(source_lines)
        line_widths = [sum((_character_width_pt(char, font_size, latin_width_factor) for char in source_line)) for source_line in source_lines]
        while remaining > 0 and allocations:
            index = max(range(len(allocations)), key=lambda item: line_widths[item] / allocations[item])
            allocations[index] += 1
            remaining -= 1
        return '\n'.join((_manual_line_breaks(source_line, allocation, font_size, latin_width_factor) for source_line, allocation in zip(source_lines, allocations)))
    characters = list(text)
    if len(characters) > 1 and any(('㐀' <= character <= '鿿' for character in characters)):
        count = min(line_count, len(characters))
        base, remainder = divmod(len(characters), count)
        lines: list[str] = []
        offset = 0
        for index in range(count):
            length = base + (1 if index < remainder else 0)
            lines.append(''.join(characters[offset:offset + length]).strip())
            offset += length
        return '\n'.join(lines)
    words = text.split()
    if len(words) <= 1:
        return text
    requested = min(line_count, len(words))
    separator_width = font_size * 0.28
    word_widths = [sum((_character_width_pt(char, font_size, latin_width_factor) for char in word)) for word in words]
    prefix = [0.0]
    for width in word_widths:
        prefix.append(prefix[-1] + width)

    def segment_width(start: int, end: int) -> float:
        """计算半开区间单词段包含分隔空格后的估算宽度。"""
        return prefix[end] - prefix[start] + separator_width * max(0, end - start - 1)
    word_count = len(words)
    infinity = float('inf')
    previous = [infinity] * (word_count + 1)
    previous[0] = 0.0
    backtrack = [[0] * (word_count + 1) for _ in range(requested + 1)]
    for line_number in range(1, requested + 1):
        current = [infinity] * (word_count + 1)
        for end in range(line_number, word_count + 1):
            best_score = infinity
            best_start = line_number - 1
            for start in range(line_number - 1, end):
                score = max(previous[start], segment_width(start, end))
                if score < best_score:
                    best_score = score
                    best_start = start
            current[end] = best_score
            backtrack[line_number][end] = best_start
        previous = current
    boundaries = [word_count]
    end = word_count
    for line_number in range(requested, 0, -1):
        end = backtrack[line_number][end]
        boundaries.append(end)
    boundaries.reverse()
    return '\n'.join((' '.join(words[boundaries[index]:boundaries[index + 1]]) for index in range(requested)))

def _wrapped_line_count(text: str, width_pt: float, font_size: float, latin_width_factor: float) -> int:
    """保守估算混合拉丁/CJK 文字在 Word 框中的自动换行数。

    空文本仍按一行；其他内容以逐字符经验宽度除以可用行宽并向上取整。
    """
    if not text:
        return 1
    estimated_width = sum((_character_width_pt(char, font_size, latin_width_factor) for char in text))
    return max(1, int(math.ceil(estimated_width / max(width_pt, 1.0))))

def _character_width_pt(char: str, font_size: float, latin_width_factor: float) -> float:
    """按脚本类别估算单个字符在候选字号下的排版宽度。

    该函数是缺少真实字体度量时的后备，分别处理空格、东亚全宽字符、ASCII 字母数字
    和其他标点符号。
    """
    if char.isspace():
        return font_size * 0.28
    if '\u3040' <= char <= 'ヿ' or '㐀' <= char <= '䶿' or '一' <= char <= '鿿' or ('가' <= char <= '\ud7af') or ('豈' <= char <= '\ufaff'):
        return font_size
    if char.isascii() and (char.isalpha() or char.isdigit()):
        return font_size * latin_width_factor
    return font_size * max(0.42, latin_width_factor * 0.8)
