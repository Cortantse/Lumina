# app/models/image.py 数据类，存储 image 相关的 dataclass
from dataclasses import dataclass, field
import time


@dataclass
class ImageInput:
    """
    前端上传的图像消息，用于 OCR / 视觉理解。
    """
    data: bytes               # 图片二进制
    format: str               # e.g. "png", "jpeg"
    timestamp: float = field(default_factory=lambda: time.time())

    short_description: str = field(default="") # 大致描述内容


