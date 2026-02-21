import logging
import logging.handlers
import re
import uuid
import shutil
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from PyPDF2 import PdfReader, PdfWriter

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

_log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

_file_handler = logging.handlers.TimedRotatingFileHandler(
    LOG_DIR / "app.log", when="midnight", backupCount=30, encoding="utf-8",
)
_file_handler.setFormatter(_log_fmt)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_fmt)

logger = logging.getLogger("pdf-tools")
logger.setLevel(logging.INFO)
logger.addHandler(_file_handler)
logger.addHandler(_console_handler)


def sanitize_filename(raw_name: str) -> str:
    """Strip directory components and replace unsafe characters."""
    name = Path(raw_name).name
    name = re.sub(r'[^\w\u4e00-\u9fff.\-]', '_', name)
    return name or "unnamed.pdf"

app = FastAPI(title="PDF 工具集", description="Web 端 PDF 处理服务集合")

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

app.add_middleware(NoCacheStaticMiddleware)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/pdf/split-odd-even")
async def split_odd_even(
    file: UploadFile = File(...),
    start_page: int = Form(1),
    end_page: int = Form(0),
):
    if not file.filename.lower().endswith(".pdf"):
        logger.warning("奇偶页拆分: 拒绝非 PDF 文件 %s", file.filename)
        return JSONResponse(status_code=400, content={"error": "请上传 PDF 文件"})

    task_id = uuid.uuid4().hex[:12]
    safe_name = sanitize_filename(file.filename)
    upload_path = UPLOAD_DIR / f"{task_id}_{safe_name}"

    with open(upload_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = upload_path.stat().st_size
    logger.info("奇偶页拆分: [%s] 上传 %s (%.2f MB), 页码 %d-%d",
                task_id, safe_name, file_size / 1048576, start_page, end_page)

    try:
        reader = PdfReader(str(upload_path))
        total_pages = len(reader.pages)

        if start_page < 1:
            start_page = 1
        if end_page <= 0 or end_page > total_pages:
            end_page = total_pages
        if start_page > end_page:
            logger.warning("奇偶页拆分: [%s] 无效页码范围 %d-%d", task_id, start_page, end_page)
            return JSONResponse(status_code=400, content={"error": f"起始页({start_page})不能大于结束页({end_page})"})

        odd_writer = PdfWriter()
        even_writer = PdfWriter()

        for i in range(start_page - 1, end_page):
            page_num = i + 1
            if page_num % 2 == 1:
                odd_writer.add_page(reader.pages[i])
            else:
                even_writer.add_page(reader.pages[i])

        base_name = Path(safe_name).stem
        odd_filename = f"{task_id}_{base_name}_奇数页.pdf"
        even_filename = f"{task_id}_{base_name}_偶数页.pdf"

        odd_path = OUTPUT_DIR / odd_filename
        even_path = OUTPUT_DIR / even_filename

        result_files = []

        if len(odd_writer.pages) > 0:
            with open(odd_path, "wb") as f:
                odd_writer.write(f)
            result_files.append({
                "name": f"{base_name}_奇数页.pdf",
                "download_url": f"/api/pdf/download/{odd_filename}",
                "page_count": len(odd_writer.pages),
            })

        if len(even_writer.pages) > 0:
            with open(even_path, "wb") as f:
                even_writer.write(f)
            result_files.append({
                "name": f"{base_name}_偶数页.pdf",
                "download_url": f"/api/pdf/download/{even_filename}",
                "page_count": len(even_writer.pages),
            })

        logger.info("奇偶页拆分: [%s] 完成, 共 %d 页, 范围 %d-%d, 生成 %d 个文件",
                    task_id, total_pages, start_page, end_page, len(result_files))

        return {
            "success": True,
            "total_pages": total_pages,
            "range": f"{start_page}-{end_page}",
            "files": result_files,
        }

    except Exception as e:
        logger.exception("奇偶页拆分: [%s] 处理失败", task_id)
        return JSONResponse(status_code=500, content={"error": f"处理失败: {str(e)}"})


@app.post("/api/pdf/a3-to-a4")
async def a3_to_a4(
    file: UploadFile = File(...),
    split_direction: str = Form("horizontal"),
    page_order: str = Form("left-right"),
    start_page: int = Form(1),
    end_page: int = Form(0),
):
    """将 A3 页面沿中线切分为两个 A4 页面"""
    if not file.filename.lower().endswith(".pdf"):
        logger.warning("A3转A4: 拒绝非 PDF 文件 %s", file.filename)
        return JSONResponse(status_code=400, content={"error": "请上传 PDF 文件"})

    task_id = uuid.uuid4().hex[:12]
    safe_name = sanitize_filename(file.filename)
    upload_path = UPLOAD_DIR / f"{task_id}_{safe_name}"

    with open(upload_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = upload_path.stat().st_size
    logger.info("A3转A4: [%s] 上传 %s (%.2f MB), 方向=%s, 顺序=%s, 页码 %d-%d",
                task_id, safe_name, file_size / 1048576,
                split_direction, page_order, start_page, end_page)

    try:
        reader = PdfReader(str(upload_path))
        total_pages = len(reader.pages)

        if start_page < 1:
            start_page = 1
        if end_page <= 0 or end_page > total_pages:
            end_page = total_pages
        if start_page > end_page:
            logger.warning("A3转A4: [%s] 无效页码范围 %d-%d", task_id, start_page, end_page)
            return JSONResponse(status_code=400, content={"error": f"起始页({start_page})不能大于结束页({end_page})"})

        writer = PdfWriter()
        output_page_count = 0

        for i in range(start_page - 1, end_page):
            page = reader.pages[i]
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)

            if split_direction == "horizontal":
                half_w = width / 2
                if page_order == "left-right":
                    first_crop = (0, 0, half_w, height)
                    second_crop = (half_w, 0, width, height)
                else:
                    first_crop = (half_w, 0, width, height)
                    second_crop = (0, 0, half_w, height)
            else:
                half_h = height / 2
                if page_order == "top-bottom":
                    first_crop = (0, half_h, width, height)
                    second_crop = (0, 0, width, half_h)
                else:
                    first_crop = (0, 0, width, half_h)
                    second_crop = (0, half_h, width, height)

            for crop in (first_crop, second_crop):
                new_page = deepcopy(page)
                new_page.mediabox.lower_left = (crop[0], crop[1])
                new_page.mediabox.upper_right = (crop[2], crop[3])
                if hasattr(new_page, 'cropbox'):
                    new_page.cropbox.lower_left = (crop[0], crop[1])
                    new_page.cropbox.upper_right = (crop[2], crop[3])
                writer.add_page(new_page)
                output_page_count += 1

        base_name = Path(safe_name).stem
        out_filename = f"{task_id}_{base_name}_A4.pdf"
        out_path = OUTPUT_DIR / out_filename

        with open(out_path, "wb") as f:
            writer.write(f)

        logger.info("A3转A4: [%s] 完成, 共 %d 页, 范围 %d-%d, 输出 %d 页",
                    task_id, total_pages, start_page, end_page, output_page_count)

        return {
            "success": True,
            "total_pages": total_pages,
            "range": f"{start_page}-{end_page}",
            "files": [{
                "name": f"{base_name}_A4.pdf",
                "download_url": f"/api/pdf/download/{out_filename}",
                "page_count": output_page_count,
            }],
        }

    except Exception as e:
        logger.exception("A3转A4: [%s] 处理失败", task_id)
        return JSONResponse(status_code=500, content={"error": f"处理失败: {str(e)}"})


@app.get("/api/pdf/download/{filename}")
async def download_file(filename: str):
    file_path = (OUTPUT_DIR / filename).resolve()
    if not file_path.is_relative_to(OUTPUT_DIR.resolve()):
        logger.warning("下载: 路径遍历尝试 %s", filename)
        return JSONResponse(status_code=403, content={"error": "非法路径"})
    if not file_path.exists():
        logger.warning("下载: 文件不存在 %s", filename)
        return JSONResponse(status_code=404, content={"error": "文件不存在"})

    display_name = "_".join(filename.split("_")[1:])
    logger.info("下载: %s -> %s", filename, display_name)
    return FileResponse(
        path=str(file_path),
        filename=display_name,
        media_type="application/pdf",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=1234, reload=True)
