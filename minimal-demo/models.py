"""定义 PP-V5 各处理阶段共用的文档数据模型。

OCR 引擎把识别结果写成 ``TextLine``，版面分析把文本行组织成 ``LayoutBlock``，
页面处理器再组装 ``PageResult`` 和 ``DocumentResult``。翻译、渲染、质量检查及
API 序列化都围绕这些对象交换数据，因此这里同时约定坐标、原文/译文、表格、
图片和处理错误的稳定含义。模型只依赖 Python 标准库，并使用 ``slots`` 降低
多页文档中大量细粒度对象的内存占用。
"""

# 推迟解析类型注解，使数据类可以安全引用稍后声明的模型类型。
from __future__ import annotations

# dataclass 生成模型初始化等样板代码，field 为列表和字典创建独立默认值。
from dataclasses import dataclass, field
# Enum 为输入类型、输出类型和版面块类型提供稳定的字符串协议值。
from enum import Enum
# Any 承载后端扩展元数据；Optional 保持旧调用兼容；TYPE_CHECKING 隔离纯注解导入。
from typing import Any, Optional, TYPE_CHECKING

# Path 只参与类型注解，运行时无需为模型模块额外导入文件系统实现。
if TYPE_CHECKING:
    # 文档结果使用 Path 表示源文件和输出文件，但推迟到类型检查阶段解析。
    from pathlib import Path


# ============================================================
# 枚举类型
# ============================================================


class BlockType(str, Enum):
    """标识版面分析后每个页面区域的业务类型。

    字符串枚举值会写入 JSON、任务报告和渲染路由，调用方据此选择正文、表格、
    图形或页眉页脚的专用处理方式。
    """

    # 普通正文或尚未细分语义的文本区域。
    TEXT = "text"
    # 文档标题或章节标题，渲染时通常使用更突出的字体层级。
    TITLE = "title"
    # 项目符号、编号或其他列表内容，需要保持缩进和编号关系。
    LIST = "list"
    # 页面顶部重复出现的页眉，正文阅读顺序通常会单独处理。
    HEADER = "header"
    # 页面底部重复出现的页脚。
    FOOTER = "footer"
    # 位于正文下方的小字号脚注内容。
    FOOTNOTE = "footnote"
    # 具有行列拓扑、单元格或 HTML 结构的表格区域。
    TABLE = "table"
    # CAD、PDF 或图片中检测到的几何形状。
    SHAPE = "shape"
    # 照片、插图或需要保留原始像素的图像区域。
    FIGURE = "figure"
    # 带坐标轴、图例或数据标注的图表区域。
    CHART = "chart"
    # 印章、公章等不应当按普通正文重排的视觉元素。
    SEAL = "seal"
    # 数学公式或需要公式渲染器处理的表达式。
    EQUATION = "equation"
    # 与图片或表格关联的图题、表题等说明文字。
    CAPTION = "caption"
    # 参考文献条目或引用列表。
    REFERENCE = "reference"
    # 摘要区域，渲染时可与普通正文使用不同样式。
    ABSTRACT = "abstract"
    # 目录区域，需要保留条目层级和页码关系。
    CATALOGUE = "catalogue"
    # 独立识别出的页码文本。
    PAGE_NUMBER = "page_number"
    # 后端无法可靠分类时使用的兜底类型。
    UNKNOWN = "unknown"


class InputKind(str, Enum):
    """描述页面内容来自哪种输入形态。

    PDF 分类器和图片处理器写入该值，后续 OCR 决策及 DOCX/PDF 渲染器据此选择
    复用文字层、执行整页 OCR 或保留原图背景。
    """

    # 原生 PDF 页面已经包含可提取文字层，可优先避免重复 OCR。
    TEXT_PDF = "text_pdf"
    # 扫描版 PDF 页面主要由像素组成，需要执行 OCR 和版面恢复。
    SCAN_PDF = "scan_pdf"
    # 同一 PDF 同时包含有效文字层和扫描/图片内容，需要混合处理。
    MIXED_PDF = "mixed_pdf"
    # 独立图片或多帧图片解码得到的页面。
    IMAGE = "image"
    # 尚未完成分类或旧数据未记录来源时使用的默认值。
    UNKNOWN = "unknown"


class OutputKind(str, Enum):
    """标识文档结果最终准备交付的产物类型。"""

    # 可编辑 Word 文档。
    DOCX = "docx"
    # 浏览器可打开的 HTML 文档。
    HTML = "html"
    # 在原页面图像上叠加可搜索文字层的 PDF。
    SEARCHABLE_PDF = "searchable_pdf"
    # 根据结构块重新排版生成的 PDF。
    REBUILT_PDF = "rebuilt_pdf"
    # 保留完整页面、块和元数据的结构化 JSON。
    JSON = "json"
    # 只保留按阅读顺序拼接文本的纯文本文件。
    TXT = "txt"
    # 用于人工核对检测框和识别结果的 OCR 可视化图片。
    OCR_VISUAL = "ocr_visual"
    # 已擦除原文并回绘译文的图片交付物。
    TRANSLATED_IMAGE = "translated_image"


# ============================================================
# 坐标类型
# ============================================================

# 页面坐标统一使用左上角和右下角四个整数像素：``(x1, y1, x2, y2)``。
BBox = tuple[int, int, int, int]


def normalize_bbox(bbox: tuple[float, float, float, float]) -> BBox:
    """把模型或 PDF 返回的浮点边界框转换成统一整数像素坐标。

    Args:
        bbox: 按 ``x1, y1, x2, y2`` 排列的浮点坐标。

    Returns:
        对四个边界分别四舍五入后的 ``BBox``；坐标顺序和方向保持不变。
    """
    # 拆出四条边，避免调用方因索引顺序不同造成坐标含义混淆。
    x1, y1, x2, y2 = bbox
    # 每条边独立四舍五入，使 OCR、版面分析和像素裁剪共享整数坐标协议。
    return (int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2)))


# ============================================================
# 核心数据类
# ============================================================


# 字符观测数量可能很大，使用 slots 减少高保真重建时的对象内存开销。
@dataclass(slots=True)
class CharacterObservation:
    """保存源文本行中单个字符或字符簇的像素级证据。

    OCR 后处理和高保真 DOCX/图片渲染使用这些观测恢复字符宽度、基线、旋转、
    字距以及连字关系；缺少精确证据时字段可保留默认值并由渲染器估算。
    """

    # 当前观测对应的字符、连字或组合字形文本。
    text: str
    # 字符在页面或所属文本行坐标系中的轴对齐边界框。
    bbox: BBox
    # 原始检测四边形，用于保留倾斜或旋转文字的真实轮廓。
    quad: tuple[tuple[float, float], ...] = ()
    # 字符所在文本基线的纵坐标；未知时由行级几何推断。
    baseline_y: float | None = None
    # OCR 对该字符观测的置信度，供修复和候选筛选使用。
    confidence: float = 1.0
    # 字符相对页面水平方向的旋转角度。
    rotation_deg: float = 0.0
    # 排版时字符占用的前进宽度，用于还原相邻字符位置。
    advance_px: float = 0.0
    # 字符与前后字形之间的字偶距修正量。
    kerning_px: float = 0.0
    # OCR 观测到的额外字符间距，用于保持扫描件疏密程度。
    tracking_px: float = 0.0
    # 标记观测是精确字符、估算字符、连字还是粘连字符簇。
    cluster_kind: str = "exact"  # 依次表示精确、估算、连字或粘连字符簇。
    # 记录该观测由哪些连通域合成，便于渲染质量审计追溯。
    source_component_ids: tuple[int, ...] = ()


# 文档中绝大多数对象都是文本行，slots 可显著降低长文档的常驻内存。
@dataclass(slots=True)
class TextLine:
    """表示一条可定位、可翻译并可重新渲染的 OCR 文本行。

    ``text`` 是当前处理阶段读取的文本，``source_text`` 固化 OCR 原文，
    ``translated_text`` 保存译文。边界框、字体和字符观测把文本内容与源页面像素
    关联起来，供版面分析、图片擦除回绘和 DOCX 高保真重建共同使用。
    """

    # 当前阶段使用的文本；渲染视图中可能暂时投影为译文。
    text: str
    # 文本行在页面坐标系中的整数边界框。
    bbox: BBox
    # OCR 行级置信度，质量门和补救策略会据此选择更可靠候选。
    confidence: float = 1.0
    # 从像素高度估算或从文字层读取的字号，供 DOCX 和图片回绘使用。
    font_size: float = 12.0
    # 优先使用的字体族；找不到字体时渲染器会按候选或回退规则选择。
    font_family: str = "宋体"
    # 指示源文字是否表现为粗体。
    is_bold: bool = False
    # 指示源文字是否表现为斜体。
    is_italic: bool = False
    # 保存左对齐、居中、右对齐或两端对齐等段落方向证据。
    alignment: str = "left"  # 取左对齐、居中、右对齐或两端对齐。
    # 以 OpenCV 的 BGR 顺序记录源文字颜色，图片回绘时复用。
    text_color: tuple[int, int, int] = (0, 0, 0)  # 通道顺序为蓝、绿、红。
    # 记录估算行距倍率，帮助流式 DOCX 保持段落疏密。
    line_spacing: float = 1.5
    # 记录文本行相对水平方向的旋转角度。
    text_angle: float = 0.0
    # 区分横排、竖排或后端提供的其他书写方向。
    text_direction: str = "horizontal"
    # 以 BGR 保存文字区域背景色，擦除原文和填补背景时作为参考。
    bg_color: tuple[int, int, int] = (255, 255, 255)

    # 稳定标识在深拷贝和渲染派生行之间保持不变，使质量检查能把输出行追溯到
    # OCR 源行，而不依赖仅在当前进程有效的 ``id()``。
    stable_id: str = ""
    # 固化 OCR 原文，避免译文视图覆盖 ``text`` 后丢失源语言内容。
    source_text: str = ""
    # 保存与当前源行对应的译文；空字符串表示尚未翻译或被策略保护。
    translated_text: str = ""
    # 记录文本行语言代码，供字体、翻译和残留字符检查选择规则。
    language: str = "unknown"
    # 记录语言识别置信度，低置信度时允许路由器回退到文档级语言。
    language_confidence: float = 0.0
    # 按书写系统统计字符数量，帮助判断中日韩、拉丁、阿拉伯等文字分布。
    script_counts: dict[str, int] = field(default_factory=dict)
    # 控制译文在原文字框中靠上、居中或靠下放置。
    vertical_alignment: str = "center"  # 取靠上、居中或靠下。
    # 扫描件高保真重建所需的非破坏性几何和字体证据。
    # 保存原始四边形，避免旋转文字只剩轴对齐矩形后丢失方向。
    source_quad: tuple[tuple[float, float], ...] = ()
    # 保存文字基线纵坐标，使不同字符能沿同一视觉基线排布。
    baseline_y: float | None = None
    # 字体上升部像素高度，用于换算 Word 字号和垂直位置。
    font_ascent_px: float = 0.0
    # 字体下降部像素高度，用于避免下行字符被文本框裁切。
    font_descent_px: float = 0.0
    # 大写字母或同类字形的高度证据。
    cap_height_px: float = 0.0
    # 小写主体高度证据，辅助字体匹配和行高估算。
    x_height_px: float = 0.0
    # 按匹配度保存候选字体及证据，渲染器从中选择可用字体。
    font_candidates: list[dict[str, Any]] = field(default_factory=list)
    # 保存行内字符级几何，供高保真重建精细恢复字距。
    character_observations: list[CharacterObservation] = field(default_factory=list)
    # 记录 OCR 补救、坐标修正和渲染修复过程，供质量报告追溯。
    repair_audit: dict[str, Any] = field(default_factory=dict)

    @property
    def center_y(self) -> float:
        """返回文本框的垂直中心坐标，供阅读顺序和区域归属判断使用。"""
        # 对上下边界取平均值，保持亚像素中心以减少排序抖动。
        return (self.bbox[1] + self.bbox[3]) / 2

    @property
    def center_x(self) -> float:
        """返回文本框的水平中心坐标，供分栏和覆盖区域判断使用。"""
        # 对左右边界取平均值，供列检测和表格/图片归属比较。
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def height(self) -> int:
        """返回文本框像素高度，供字号估算和重叠计算使用。"""
        # 使用下边界减上边界，沿用全项目的半开像素框约定。
        return self.bbox[3] - self.bbox[1]

    @property
    def width(self) -> int:
        """返回文本框像素宽度，供排版容量和重叠计算使用。"""
        # 使用右边界减左边界，结果直接供文本适配和裁剪逻辑使用。
        return self.bbox[2] - self.bbox[0]

    @property
    def display_text(self) -> str:
        """返回面向最终读者的文本，优先使用已生成的译文。"""
        # 没有译文时保留当前 OCR 文本，确保受保护或翻译失败的行仍可显示。
        return self.translated_text or self.text

    @property
    def original_text(self) -> str:
        """返回可追溯的 OCR 原文，不受渲染视图中的译文覆盖影响。"""
        # 新结果优先使用固化的 source_text，旧结果则兼容回退到 text。
        return self.source_text or self.text


# 表格单元格会在大表中大量创建，使用 slots 控制对象开销。
@dataclass(slots=True)
class TableCell:
    """表示表格拓扑中的一个可翻译、可渲染单元格。

    行列索引及跨行跨列信息描述逻辑结构，边界框和多边形描述页面位置；
    原文、识别置信度、边框、填充和内边距共同支持 DOCX/HTML 表格重建。
    """

    # 当前阶段展示的单元格文本；翻译后可能保存目标语言内容。
    text: str = ""
    # 单元格在页面或表格裁剪图坐标系中的轴对齐边界框。
    bbox: BBox = (0, 0, 0, 0)
    # 单元格起始行索引，使用从零开始的表格拓扑坐标。
    row: int = 0
    # 单元格起始列索引，使用从零开始的表格拓扑坐标。
    col: int = 0
    # 单元格纵向占用的行数，用于恢复合并单元格。
    rowspan: int = 1
    # 单元格横向占用的列数，用于恢复合并单元格。
    colspan: int = 1
    # 标记表头单元格，HTML 和 DOCX 渲染可据此采用表头样式。
    is_header: bool = False
    # 保存非矩形或透视单元格的原始轮廓点。
    polygon: list[tuple[float, float]] = field(default_factory=list)
    # 固化 OCR 原文，使表格翻译后仍能进行双语映射和质量核对。
    source_text: str = ""
    # 表格识别器对该单元格内容或结构的置信度。
    confidence: float = 1.0
    # 标记单元格来自文字层、OCR、RapidTable 或其他后端，便于追溯。
    source: str = ""
    # 按上、右、下、左保存边框样式和检测证据。
    borders: dict[str, dict[str, Any]] = field(default_factory=dict)
    # 保存左上到右下或右上到左下的对角线方向。
    diagonal: str = ""  # 取左上到右下或右上到左下，空值表示没有对角线。
    # 保存单元格填充颜色，供 Word/HTML 渲染还原底色。
    fill_color: str = ""
    # 保存单元格内容的水平对齐方式。
    horizontal_alignment: str = "left"
    # 保存单元格内容的垂直对齐方式。
    vertical_alignment: str = "center"
    # 依次记录上、右、下、左内边距像素，控制重建后的文字留白。
    padding_px: tuple[float, float, float, float] = (2.0, 3.0, 2.0, 3.0)
    # 保存嵌套在当前单元格内的子表格结构。
    nested_tables: list["TableBlock"] = field(default_factory=list)
    # 保留后端未标准化的扩展字段，供诊断或专用渲染策略使用。
    raw: dict[str, Any] = field(default_factory=dict)
    # 保存单元格内逐行 OCR 几何，图片翻译可据此精确擦除和回绘。
    text_lines: list[TextLine] = field(default_factory=list)


# 表格块作为页面结构节点频繁传递，slots 可避免额外实例字典。
@dataclass(slots=True)
class TableBlock:
    """保存一张表格的单元格、网格边界和结构验证结果。

    版面分析或表格识别器生成该对象，翻译阶段按单元格映射原文和译文，
    DOCX/HTML 渲染器使用行列拓扑、边界线及 HTML 结构重建可编辑表格。
    """

    # 按识别结果保存全部单元格及其行列位置。
    cells: list[TableCell] = field(default_factory=list)
    # 表格逻辑行数，包含跨行单元格覆盖的网格行。
    rows: int = 0
    # 表格逻辑列数，包含跨列单元格覆盖的网格列。
    cols: int = 0
    # 后端提供或项目重建的 HTML 表格，作为结构回退和 API 输出。
    html: str = ""
    # 页面坐标系中的纵向网格边界，用于恢复各列宽度。
    x_edges: list[float] = field(default_factory=list)
    # 页面坐标系中的横向网格边界，用于恢复各行高度。
    y_edges: list[float] = field(default_factory=list)
    # 保留 RapidTable 返回的单元格多边形，供结构审计和透视校正使用。
    rapidtable_polygons: list[list[tuple[float, float]]] = field(default_factory=list)
    # 表格拓扑质量分数，质量门据此决定是否信任可编辑结构。
    topology_confidence: float = 0.0
    # 标记行列和合并关系是否通过结构验证。
    topology_valid: bool = False
    # 保存拓扑验证失败原因，供回退策略和最终质量报告使用。
    topology_error: str = ""
    # 记录生成分析数据时使用的模式版本，避免旧缓存被新逻辑误读。
    analysis_schema_version: str = ""
    # 保留表格后端的扩展诊断字段，不影响统一渲染协议。
    raw: dict[str, Any] = field(default_factory=dict)


# 图片块可能携带较大的二进制数据，slots 避免额外属性字典占用。
@dataclass(slots=True)
class ImageBlock:
    """保存页面中的图片像素以及需要叠加的可编辑文字。

    ``image_data`` 通常是从源页面裁剪出的原图，``overlay_text`` 保存图片内部的
    OCR 文本；图片翻译完成后，``modified_data`` 可承载已擦除原文并回绘译文的版本。
    """

    # 保存 PNG/JPEG 等编码后的原始图片字节，避免模型层依赖 OpenCV 数组。
    image_data: bytes = b""
    # 记录图片字节对应的文件扩展名，供解码和媒体类型判断使用。
    ext: str = "png"
    # 保存位于图片区域内部、渲染时需要叠加或翻译的文本行。
    overlay_text: list[TextLine] = field(default_factory=list)
    # 保存完成文字替换后的图片字节；为空时继续使用原始 image_data。
    modified_data: bytes = b""


# 链接对象只保存协议字段，slots 使多链接 PDF 的模型更轻量。
@dataclass(slots=True)
class Link:
    """表示从 PDF 页面提取出的可点击超链接区域。"""

    # 链接指向的 URI，渲染到 DOCX/HTML 时作为实际跳转目标。
    uri: str
    # 链接在 PDF 页面坐标系中的浮点矩形范围。
    bbox: tuple[float, float, float, float]
    # 链接覆盖的可见文字；源文件未提供时允许为空。
    text: str = ""
    # 链接所在的零基或后端约定页号，由提取器统一填充。
    page: int = 0


# PDF 注释可能成批出现，slots 降低保存审阅信息时的内存占用。
@dataclass(slots=True)
class Annotation:
    """保存 PDF 批注、便签或标记的内容和页面位置。"""

    # 标记批注类型，例如文本便签、高亮或下划线。
    annot_type: str = ""
    # 保存后端提取的简要显示文本。
    text: str = ""
    # 批注在 PDF 页面坐标系中的矩形范围。
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)
    # 批注所属页号。
    page: int = 0
    # PDF 批注作者或标题字段。
    title: str = ""
    # PDF 批注主题字段。
    subject: str = ""
    # 批注的完整正文内容。
    content: str = ""


# 表单字段对象保持轻量，便于从交互式 PDF 批量提取。
@dataclass(slots=True)
class FormField:
    """表示交互式 PDF 中一个表单控件及其当前值。"""

    # 控件类型，例如文本框、复选框或下拉列表。
    field_type: str = ""
    # PDF 表单内部用于提交和关联数据的字段名。
    name: str = ""
    # 当前表单字段显示或提交的值。
    value: str = ""
    # 控件在页面上的浮点边界框。
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)
    # 控件所属页号。
    page: int = 0
    # 保留 PDF 字段标志位，用于判断只读、必填等属性。
    flags: int = 0


# 单条绘图指令结构简单且数量可能很大，因此使用 slots。
@dataclass(slots=True)
class DrawItem:
    """描述 PDF 矢量路径中的一条基础绘图指令。"""

    # 指令类型用于区分直线、曲线、矩形或其他路径片段。
    item_type: str = ""
    # 保存该指令使用的页面坐标点序列。
    points: list[tuple[float, float]] = field(default_factory=list)
    # 路径填充颜色；None 表示没有填充。
    fill: str | None = None
    # 路径描边颜色；None 表示没有描边。
    stroke: str | None = None
    # 标记路径是否在末尾闭合。
    close: bool = False


# Drawing 汇总页面矢量路径，slots 减少工程图和复杂 PDF 中的模型开销。
@dataclass(slots=True)
class Drawing:
    """保存 PDF 页面中的一组矢量绘图或路径信息。"""

    # 标识当前绘图属于线条、填充区域或后端定义的其他类别。
    drawing_type: str = ""
    # 保留后端原始路径指令，供重建和工程图分析使用。
    items: list[dict] = field(default_factory=list)
    # 整组绘图在页面上的外接矩形。
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)
    # 绘图所属页号。
    page: int = 0
    # 整组路径的填充颜色。
    fill_color: str | None = None
    # 整组路径的描边颜色。
    stroke_color: str | None = None
    # 描边线宽，重建 PDF 或 DOCX 图形时作为视觉参考。
    line_width: float = 1.0


# 页面通常包含大量版面块，使用 slots 控制跨页结果的内存占用。
@dataclass(slots=True)
class LayoutBlock:
    """表示页面中一个具有统一边界和语义类型的版面区域。

    文本段落、标题、表格、图片和公式都通过该模型进入后续流程。普通文字保存在
    ``text_lines``，表格和图片分别挂载 ``table`` 与 ``image``；翻译、阅读顺序、
    DOCX/PDF/HTML 渲染和质量检查由 ``block_type`` 选择相应处理策略。
    """

    # 标记该区域是正文、表格、图片、标题还是其他版面语义。
    block_type: BlockType
    # 区域在整页坐标系中的整数边界框。
    bbox: BBox
    # 版面检测器对区域类型和位置的综合置信度。
    confidence: float = 1.0
    # 保存区域内按行组织的 OCR 文本；表格或图片也可携带辅助文本行。
    text_lines: list[TextLine] = field(default_factory=list)

    # 表格区域在这里挂载可编辑行列拓扑；非表格块保持 None。
    table: Optional[TableBlock] = None
    # 图片或图形区域在这里挂载编码像素和叠加文本；非图片块保持 None。
    image: Optional[ImageBlock] = None

    # 公式区域保存可供公式渲染器使用的 LaTeX 表达式。
    formula_latex: str = ""
    # 保存区域背景色，图片擦除和文档样式重建时作为填充参考。
    bg_color: tuple[int, int, int] = (255, 255, 255)
    # 标记区域是否检测到外边框，帮助区分文本框、表格和普通段落。
    has_border: bool = False

    # 保留后端原始结果和修复审计字段，供专用策略及问题追溯使用。
    raw: dict[str, Any] = field(default_factory=dict)
    # 保存页面阅读顺序索引，渲染和纯文本导出据此排列区域。
    order: int = 0

    @property
    def width(self) -> int:
        """返回版面块像素宽度，供覆盖率和排版容量计算使用。"""
        # 统一按右边界减左边界计算，保持与 TextLine.width 相同坐标约定。
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        """返回版面块像素高度，供重叠和页面布局计算使用。"""
        # 统一按下边界减上边界计算，结果可直接用于裁剪和面积统计。
        return self.bbox[3] - self.bbox[1]

    @property
    def is_structured(self) -> bool:
        """判断该块是否应由表格、图形或公式专用流程处理。"""
        # 这些类型不能像普通正文一样直接合并，否则会丢失网格、像素或公式结构。
        return self.block_type in (
            # 表格需要保留单元格拓扑和边框。
            BlockType.TABLE,
            # 几何形状需要保留矢量或视觉关系。
            BlockType.SHAPE,
            # 插图需要保留原始图像及内部叠加文字。
            BlockType.FIGURE,
            # 图表需要保护坐标轴、图例和数据标记。
            BlockType.CHART,
            # 印章通常作为不可重排的视觉元素处理。
            BlockType.SEAL,
            # 公式需要使用专用数学排版。
            BlockType.EQUATION,
        )


# 每个输入页面对应一个结果对象，slots 控制多页文档的内存开销。
@dataclass(slots=True)
class PageResult:
    """汇总一个页面的尺寸、来源、版面块和 PDF 附加对象。

    PDF 或图片处理器创建该对象，翻译器遍历其中的文本行和表格单元格，渲染器
    使用页面尺寸及块坐标恢复版面，任务报告从 ``metadata`` 读取耗时和质量指标。
    """

    # 页面在文档中的业务页码，通常从 1 开始供日志和输出展示。
    page_number: int
    # 原页面宽度；图片通常使用像素，PDF 处理器会统一到渲染坐标系。
    width: float
    # 原页面高度，与 width 共同定义所有块坐标的页面范围。
    height: float
    # 记录页面来自文字型 PDF、扫描 PDF、混合 PDF 或独立图片。
    input_kind: InputKind = InputKind.UNKNOWN
    # 保存按页面坐标组织的正文、标题、表格、图片等版面块。
    blocks: list[LayoutBlock] = field(default_factory=list)
    # 保存页面中的可点击超链接，供 DOCX/HTML/PDF 输出复用。
    links: list[Link] = field(default_factory=list)
    # 保存源 PDF 批注，避免文档转换时无声丢失审阅信息。
    annotations: list[Annotation] = field(default_factory=list)
    # 保存交互式 PDF 表单控件及当前值。
    form_fields: list[FormField] = field(default_factory=list)
    # 保存页面矢量绘图，供工程图识别和高保真重建使用。
    drawings: list[Drawing] = field(default_factory=list)
    # 保存 OCR 路由、版面后端、耗时、质量和补救诊断等页面级信息。
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text_lines(self) -> list[TextLine]:
        """按版面块顺序汇总页面直接挂载的文本行。

        Returns:
            一个新的文本行列表；不会包含 ``ImageBlock.overlay_text``，调用方需要
            图片内部文字时应显式遍历图片块，避免重复统计。
        """
        # 创建新列表，防止调用方修改结果时破坏各版面块原有文本行容器。
        result: list[TextLine] = []
        # 按 blocks 当前顺序遍历，保留页面处理器确定的阅读次序。
        for b in self.blocks:
            # 跳过没有直接文本行的纯图片、空表格或结构占位块。
            if b.text_lines:
                # 追加现有 TextLine 对象，保持翻译和渲染共享同一行级状态。
                result.extend(b.text_lines)
        # 返回扁平列表，供翻译、统计或纯文本导出使用。
        return result

    @property
    def tables(self) -> list[TableBlock]:
        """返回页面中实际挂载的全部表格模型。"""
        # 以 table 是否存在为准，兼容后端尚未正确标记 block_type 的历史结果。
        return [b.table for b in self.blocks if b.table is not None]

    @property
    def images(self) -> list[ImageBlock]:
        """返回页面中实际挂载的全部图片模型。"""
        # 以 image 是否存在为准，确保图形块和兼容数据也能被图片渲染器发现。
        return [b.image for b in self.blocks if b.image is not None]


# 一次任务只产生少量文档结果，但 slots 可保持与其他模型一致的受控字段集合。
@dataclass(slots=True)
class DocumentResult:
    """表示一次文档处理从输入到交付的统一结果。

    页面处理器把成功页面和局部错误累积到该对象；翻译阶段原位补充译文，渲染
    阶段写入输出类型与路径，API、CLI 和任务服务最终都从这里生成响应和报告。
    """

    # 保存用户输入文件路径，用于文件类型判断、命名输出和问题追溯。
    source_path: Optional[Path] = None
    # 按文档顺序保存所有成功组装的页面结果。
    pages: list[PageResult] = field(default_factory=list)
    # 标记当前结果准备交付的格式，默认使用 DOCX。
    output_kind: OutputKind = OutputKind.DOCX
    # 渲染完成后的产物路径；仅分析模式或失败时可以为空。
    output_path: Optional[Path] = None
    # 保存文档级语言、OCR 模式、总耗时、质量和路由等扩展信息。
    metadata: dict[str, Any] = field(default_factory=dict)
    # 收集页面或阶段错误；允许部分页面成功后继续交付并向用户告警。
    errors: list[str] = field(default_factory=list)

    @property
    def total_pages(self) -> int:
        """返回已组装到结果中的页面数量。"""
        # 直接以 pages 容器为准，包含成功保留下来的所有页面。
        return len(self.pages)

    @property
    def has_errors(self) -> bool:
        """判断文档处理过程中是否记录过任何错误。"""
        # errors 非空即表示存在局部或整体失败，CLI 会据此返回非零退出码。
        return len(self.errors) > 0


# 统计模型结构固定，slots 防止运行时意外写入未约定指标。
@dataclass(slots=True)
class ProcessingStats:
    """保存一次文档处理的基础数量、耗时和后端摘要。"""

    # 成功参与统计的页面数量。
    page_count: int = 0
    # 页面中普通文本版面块的总数。
    text_block_count: int = 0
    # 识别并保留的表格总数。
    table_count: int = 0
    # 检测或提取的图片/图形总数。
    image_count: int = 0
    # 整个处理过程的墙钟耗时秒数。
    elapsed_seconds: float = 0.0
    # 实际使用的 OCR 或处理后端名称，供性能和质量对比使用。
    backend: str = ""
    # 保存回退、警告或其他不适合固定字段表达的简要说明。
    notes: list[str] = field(default_factory=list)


# ============================================================
# 向后兼容别名 (方便渐进迁移)
# ============================================================

# 让仍导入 LayoutType 的旧调用方继续使用新的块类型枚举，避免一次性迁移全部模块。
LayoutType = BlockType

# 让旧代码中的 LayoutRegion 指向统一 LayoutBlock；调用旧字段名的代码仍需注意
# text_lines、table 和 image 的结构映射差异。
LayoutRegion = LayoutBlock
