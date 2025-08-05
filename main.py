from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from PIL import Image
from io import BytesIO
import cloudinary
import cloudinary.uploader
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
import shutil
import psutil
from dotenv import load_dotenv
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

MAX_UPLOAD_SIZE = 10 * 1024 * 1024 

class LimitUploadSizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_UPLOAD_SIZE:
            return Response(
                content="File too large", status_code=413
            )
        return await call_next(request)

load_dotenv()  # Load variables from .env

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

app = FastAPI()
app.add_middleware(LimitUploadSizeMiddleware)

RESIZE_PRESETS = {
    "portrait": (864, 1080 ),
    "square": (1080, 1080),
    "profile": (110, 110),
    "landscape": (1080, 608)
}

executor = ThreadPoolExecutor(max_workers=10)

def get_resource_usage(start_time: float):
    # process = psutil.Process(os.getpid())

    elapsed = time.perf_counter() - start_time
    # memory_info = process.memory_info()
    # cpu_percent = process.cpu_percent(interval=0.1)  # slight delay to get real % usage
    # core_count = psutil.cpu_count(logical=True)

    return {
        "processing_time_ms": round(elapsed * 1000, 2),
        # "memory_usage_mb": round(memory_info.rss / (1024 * 1024), 2),
        # "cpu_usage_percent": cpu_percent,
        # "cpu_cores_used": core_count
    }

def process_image_sync(contents: bytes, target_size: tuple) -> BytesIO:
    try:
        img = Image.open(BytesIO(contents))
        img = img.convert("RGB")
        img.thumbnail(target_size, Image.LANCZOS)
    except Exception:
        raise ValueError("Invalid image file.")

    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=60, optimize=True)
    buffer.seek(0)
    return buffer

def cleanup_pycache():
    for root, dirs, _ in os.walk("."):
        for dir_name in dirs:
            if dir_name == "__pycache__":
                pycache_path = os.path.join(root, dir_name)
                shutil.rmtree(pycache_path, ignore_errors=True)
@app.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    image_type: str = Form("portrait")
):
    start_time = time.perf_counter()

    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are allowed.")

    if image_type not in RESIZE_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid image_type. Choose one of {list(RESIZE_PRESETS.keys())}"
        )

    # ✅ Read and resize before uploading
    contents = await file.read()
    buffer = await asyncio.get_event_loop().run_in_executor(
        executor, process_image_sync, contents, RESIZE_PRESETS[image_type]
    )

    try:
        result = cloudinary.uploader.upload(
            buffer,
            resource_type="image",
            folder="standardized_uploads",
            overwrite=False,
            use_filename=False,
            unique_filename=True
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cloudinary upload failed: {e}")

    usage = get_resource_usage(start_time)
    usage.update({"url": result["secure_url"]})

    cleanup_pycache()
    return JSONResponse(content=usage)
# @app.post("/upload")  
# async def upload_image(
#     file: UploadFile = File(...),
#     image_type: str = Form("portrait")
# ):
#     start_time = time.perf_counter()

#     if not file.content_type.startswith("image/"):
#         raise HTTPException(status_code=400, detail="Only image uploads are allowed.")

#     if image_type not in RESIZE_PRESETS:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Invalid image_type. Choose one of {list(RESIZE_PRESETS.keys())}"
#         )

#     contents = await file.read()
#     await file.close()  # ✅ Explicitly close file

#     try:
#         buffer = await asyncio.get_event_loop().run_in_executor(
#             executor, process_image_sync, contents, RESIZE_PRESETS[image_type]
#         )
#     except ValueError as e:
#         raise HTTPException(status_code=400, detail=str(e))

#     try:
#         result = cloudinary.uploader.upload(
#             buffer,
#             resource_type="image",
#             folder="standardized_uploads",
#             overwrite=False,
#             use_filename=False,
#             unique_filename=True
#         )
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Cloudinary upload failed: {e}")

#     usage = get_resource_usage(start_time)
#     usage.update({
#         # "message": f"{image_type.capitalize()} image uploaded and resized successfully",
#         "url": result["secure_url"],
#         # "public_id": result["public_id"],
#         # "format": result["format"],
#         # "width": result["width"],
#         # "height": result["height"],
#     })

#     cleanup_pycache()  

#     return JSONResponse(content=usage)
