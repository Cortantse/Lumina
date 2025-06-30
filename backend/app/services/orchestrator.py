# app/services/orchestrator.py 组织 diagloue 的 service
from __future__ import annotations
import logging
from typing import List

from ..models.image import ImageInput
from ..models.dialogue import Dialogue
from ..protocols.memory import MemoryType
from ..memory.store import get_memory_manager
from ..utils.util import save_blob_and_get_uri

logger = logging.getLogger(__name__)

class Orchestrator:
    """
    编排器，负责协调处理流程。
    """

    async def process_multimedia_input(
        self,
        image_inputs: List[ImageInput],
        related_dialogue: Dialogue,
    ) -> None:
        """
        处理多媒体输入（当前为图片），将其信息存入记忆。

        Args:
            image_inputs: 包含图片数据的输入列表。
            related_dialogue: 与这些图片相关的对话对象，用于关联元数据。
        """
        if not image_inputs:
            return

        memory_manager = await get_memory_manager()

        for image in image_inputs:
            try:
                # 1. 将图片的二进制数据保存到文件，并获取 URI
                blob_uri = save_blob_and_get_uri(
                    data=image.data,
                    file_format=image.format,
                    subfolder="images"
                )

                # 2. 准备要存入记忆的文本和元数据
                #    - 使用 short_description 作为核心记忆文本
                #    - 将对话ID等信息存入元数据
                text_to_store = image.short_description or "一张图片"
                metadata = {
                    "dialogue_id": related_dialogue.id,
                    "source": "image_upload"
                }

                # 3. 调用记忆存储
                await memory_manager.store(
                    original_text=text_to_store,
                    mem_type=MemoryType.IMAGE,
                    blob_uri=blob_uri,
                    metadata=metadata
                )
                logger.info(f"图片记忆已存储, URI: {blob_uri}")

            except Exception as e:
                logger.error(f"处理图片输入时发生错误: {e}", exc_info=True)


# --- 单例模式 ---
_default_orchestrator: Orchestrator | None = None

def get_orchestrator() -> Orchestrator:
    """
    获取编排器服务的单例。
    """
    global _default_orchestrator
    if _default_orchestrator is None:
        _default_orchestrator = Orchestrator()
    return _default_orchestrator