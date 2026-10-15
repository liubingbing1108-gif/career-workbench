"""The one resume conversion boundary: local bytes -> MarkItDown -> Markdown."""
import io
import zipfile
import threading
from pathlib import Path

_converter = None
_conversion_lock = threading.Lock()

FORMATS = {'.pdf', '.docx', '.txt', '.md', '.pptx', '.xlsx', '.xls', '.csv', '.html', '.htm', '.json', '.xml'}


def convert_document(filename, raw):
    global _converter
    from lab import LabError
    suffix = Path(filename).suffix.lower()
    if suffix not in FORMATS:
        raise LabError('暂不支持此格式转换；请另存为 PDF、DOCX 或文本文件后上传，原文件仍保留。')
    try:
        if suffix in {'.docx', '.pptx', '.xlsx'}:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if sum(i.file_size for i in archive.infolist()) > 64 * 1024 * 1024:
                    raise LabError('文档解压后过大，未开始识别')
        if suffix == '.pdf':
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted:
                raise LabError('加密 PDF 需要先由用户解密')
            if len(reader.pages) > 50:
                raise LabError('最多读取 50 页')
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        from markitdown import MarkItDown, StreamInfo
        # Bytes only. No URL dispatch, plugins, cloud OCR or additional model.
        with _conversion_lock:
            if _converter is None:
                _converter = MarkItDown(enable_plugins=False)
            result = _converter.convert_stream(
                io.BytesIO(raw), stream_info=StreamInfo(extension=suffix, filename=filename))
        markdown = result.text_content
        if len(markdown) > 80000:
            raise LabError('转换后的 Markdown 超过 80000 字符限制')
        return [{'text': markdown, 'location': 'Markdown 全文（MarkItDown 转换）'}]
    except ImportError:
        raise LabError('缺少 MarkItDown 文档转换依赖，请按 requirements.txt 安装后重试')
    except LabError:
        raise
    except Exception:
        raise LabError('MarkItDown 转换失败；原文件保留，请检查文件格式或重新导出后重试')
