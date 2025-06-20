"""
文本分块工具，用于将长文本分割成更小的、语义连贯的块。
这对于 RAG (Retrieval-Augmented Generation) 场景至关重要，
因为它能让向量检索更精确地匹配到文本的特定部分。
"""
from __future__ import annotations
import re
from typing import List, Optional, Any
from ..core.config import TEXT_SPLITTER_CONFIG

class RecursiveCharacterTextSplitter:
    """
    Splits text into chunks of a specified size, trying to preserve semantic
    units by splitting on a prioritized list of separators.

    This implementation is a robust, simplified version inspired by standard
    libraries like LangChain, designed to handle separators and overlap correctly.
    """
    
    def __init__(
        self,
        chunk_size: int = TEXT_SPLITTER_CONFIG["chunk_size"],
        chunk_overlap: int = TEXT_SPLITTER_CONFIG["chunk_overlap"],
        separators: Optional[List[str]] = None,
    ):
        if chunk_overlap > chunk_size:
            raise ValueError(
                f"Chunk overlap ({chunk_overlap}) cannot be larger than "
                f"chunk size ({chunk_size})."
            )
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._separators = separators or [
            "\n\n",  # Paragraphs
            "\n",    # Lines
            "。|！|？", # Chinese sentences
            r"\. ",   # English sentences
            "，",    # Chinese phrases
            ",",     # English phrases
            " ",     # Words
            "",      # Characters
        ]

    def split_text(self, text: str) -> List[str]:
        """Splits a given text into a list of appropriately sized chunks."""
        if not text:
            return []

        # Start with the highest-priority separator
        final_splits = self._split(text, self._separators)
        
        # Merge the splits into chunks
        return self._merge_splits(final_splits)

    def _split(self, text: str, separators: List[str]) -> List[str]:
        """Recursively splits text by a list of separators."""
        final_chunks: List[str] = []
        
        if not text or not separators:
            if text:
                final_chunks.append(text)
            return final_chunks

        # Get the next separator to use
        separator = separators[0]
        remaining_separators = separators[1:]
        
        # Split by the separator using regex to keep the separator
        try:
            # Use a lookbehind assertion to keep the separator with the preceding part
            splits = re.split(f"(?<={separator})", text)
        except re.error:
            # If the separator is not a valid regex, do a normal split
            splits = text.split(separator)
        
        for split in splits:
            if not split:
                continue
            
            if len(split) > self._chunk_size:
                # If a split is still too large, recurse with the next separators
                final_chunks.extend(self._split(split, remaining_separators))
            else:
                final_chunks.append(split)
        
        return final_chunks

    def _merge_splits(self, splits: List[str]) -> List[str]:
        """Merges small text splits into chunks with correct size and overlap."""
        final_chunks: List[str] = []
        current_chunk_splits: List[str] = []
        current_length = 0

        for split in splits:
            split_len = len(split)
            if not split:
                continue
            
            # If adding the next split would make the chunk too big, finalize the current one
            if current_length + split_len > self._chunk_size and current_chunk_splits:
                # Join the current splits to form a chunk
                chunk = "".join(current_chunk_splits)
                final_chunks.append(chunk)

                # Handle overlap: slide back from the end of the just-formed chunk
                if self._chunk_overlap > 0:
                    overlap_text = chunk[-self._chunk_overlap:]
                    # Start the new chunk with the overlap text
                    current_chunk_splits = [overlap_text]
                    current_length = len(overlap_text)
                else:
                    # No overlap, start fresh
                    current_chunk_splits = []
                    current_length = 0
            
            # Add the current split to the list for the next chunk
            current_chunk_splits.append(split)
            current_length += split_len

        # Add the last remaining chunk
        if current_chunk_splits:
            chunk = "".join(current_chunk_splits)
            final_chunks.append(chunk)
            
        return [c for c in final_chunks if c.strip()] 