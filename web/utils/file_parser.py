# web/utils/file_parser.py
import io
import re
import docx
import PyPDF2


def parse_file(file_bytes: bytes, file_type: str) -> str:
    """解析上传文件为纯文本"""

    try:
        if file_type == "text/plain":
            text = file_bytes.decode("utf-8")

        elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            doc = docx.Document(io.BytesIO(file_bytes))
            text = "\n".join([p.text for p in doc.paragraphs])

        elif file_type == "application/pdf":
            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])

        else:
            return ""

        # 清理多余空白
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()

    except Exception as e:
        print(f"文件解析错误: {e}")
        return ""
