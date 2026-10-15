# 仅发布精选代码

目标仓库：[YSADF/ocr-document-showcase](https://github.com/YSADF/ocr-document-showcase)。本目录是公开仓库的根目录，包含精选算法和案例；不要将它的父项目初始化为此远端或整体推送。

`PUBLISH_MANIFEST.json` 是逐文件发布清单，记录相对路径、字节数及 SHA-256。清单不记录自身哈希；生成目录与缓存不参与发布。发布检查不能替代素材许可和内容审阅。

## 先检查并导出

在本公开目录中运行。导出位置必须是尚不存在的独立目录：

```bash
python -X utf8 -m unittest discover -s tests -v
python -X utf8 tools/verify_demo.py
python -X utf8 tools/check_publication.py
python -X utf8 tools/check_publication.py --export ../ocr-showcase-export
```

导出只复制清单中的文件及清单本身，不复制父项目、Git 历史、模型或现场配置。工具遇到未知文件、哈希变化或不允许的路径会停止。正式编辑后需由维护者审阅变更，再更新相应清单项，不能通过扫描整个业务项目自动放行。

## 使用独立 checkout 提交

以下是 PowerShell 操作示例，从公开目录开始执行。使用新的发布目录，保留本地完整项目及旧发布目录中的未提交工作。

```powershell
git clone https://github.com/YSADF/ocr-document-showcase.git ../ocr-showcase-release
Set-Location ../ocr-showcase-release
git switch -c codex/showcase-refresh

$publicExport = (Resolve-Path ../ocr-showcase-export).Path
$publicManifest = Get-Content -LiteralPath (Join-Path $publicExport PUBLISH_MANIFEST.json) -Raw | ConvertFrom-Json
$publicFiles = @($publicManifest.files.PSObject.Properties.Name) + @('PUBLISH_MANIFEST.json')
foreach ($publicFile in $publicFiles) {
    $publicDestination = Join-Path (Get-Location).Path $publicFile
    New-Item -ItemType Directory -Path (Split-Path $publicDestination -Parent) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $publicExport $publicFile) -Destination $publicDestination
}

python -X utf8 tools/check_publication.py
python -X utf8 tools/verify_demo.py
python -X utf8 -m unittest discover -s tests -v
git status --short
```

若检查报告远端新增文件不在清单中，先审阅并解决差异，不递归删除已有目录。所有检查通过后，在这个独立 checkout 内提交：

```powershell
git add -- @publicFiles
git diff --cached --stat
git diff --cached --check
git commit -m "docs: refresh OCR showcase with verified demos and runnable examples"
git push -u origin codex/showcase-refresh
```

推送分支后在 GitHub 查看差异，再合入 `main`。本地完整项目的暂存区不参与以上操作。

## GitHub 展示信息

- **Name：** `ocr-document-showcase`
- **Description：** OCR 文档处理精选实现：工程字符复核、表格结构、真实案例与可复算评测。
- **Topics：** `ocr`, `paddleocr`, `document-ai`, `table-extraction`, `engineering-drawings`, `vlm`, `python`

公开代码、文档和素材各自沿用 [分项许可](../LICENSE.md)。未公开的完整源码不在授权范围内。
