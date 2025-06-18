"""
文本分块工具，用于将长文本分割成更小的、语义连贯的块。
这对于 RAG (Retrieval-Augmented Generation) 场景至关重要，
因为它能让向量检索更精确地匹配到文本的特定部分。
"""
from __future__ import annotations
from typing import List, Optional, Sequence, Any
from ..core.config import TEXT_SPLITTER_CONFIG

def _split_text_with_separators(
    text: str, separators: List[str], chunk_size: int
) -> List[str]:
    """Recursively splits text using a list of separators."""
    final_splits = []
    # Get the best separator to use
    separator = None
    for s in separators:
        if s == "":  # Final fallback separator
            separator = s
            break
        if s in text:
            separator = s
            break
    
    # If no separator is found, the text is one big chunk
    if separator is None:
        return [text]

    # If the separator is an empty string, we have to split by characters
    if separator == "":
        return list(text)

    # Split by the separator
    splits = text.split(separator)
    
    # Recursively split any parts that are still too large
    remaining_separators = separators[separators.index(separator) + 1 :]
    for part in splits:
        if len(part) > chunk_size:
            final_splits.extend(
                _split_text_with_separators(part, remaining_separators, chunk_size)
            )
        else:
            final_splits.append(part)
    return final_splits

class RecursiveCharacterTextSplitter:
    """
    Recursively splits text into chunks with overlap.
    
    This implementation first splits the text into smaller pieces using separators,
    and then merges them back into chunks of the desired size with overlap.
    This ensures that overlap is handled correctly and consistently.
    """
    
    def __init__(
        self,
        chunk_size: int = TEXT_SPLITTER_CONFIG["chunk_size"],
        chunk_overlap: int = TEXT_SPLITTER_CONFIG["chunk_overlap"],
        separators: Optional[List[str]] = None,
        keep_separator: bool = True,
    ):
        """
        Initializes the text splitter.
        
        Args:
            chunk_size: Max size of each chunk. Defaults to value in config.
            chunk_overlap: Overlap between chunks. Defaults to value in config.
            separators: A prioritized list of strings to split on.
            keep_separator: Whether to keep the separator in the chunks.
        """
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"Chunk overlap ({chunk_overlap}) must be smaller than "
                f"chunk size ({chunk_size})."
            )
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._keep_separator = keep_separator
        self._separators = separators or [
            "\n\n",  # Double newline (paragraph)
            "\n",    # Newline
            "。 ",   # Chinese period
            "。",    # Chinese period
            "！",    # Chinese exclamation mark
            "？",    # Chinese question mark
            ", ",   # Comma + space
            "，",    # Chinese comma
            " ",     # Space
            "",      # Fallback to characters
        ]

    def _merge_splits(self, splits: List[str], separator: str) -> List[str]:
        """Merges small splits into chunks with overlap."""
        final_chunks: List[str] = []
        current_chunk: List[str] = []
        current_length = 0
        separator_len = len(separator) if self._keep_separator else 0

        for split in splits:
            split_len = len(split)
            # If the current chunk is not empty and adding the next split would
            # exceed the chunk size, finalize the current chunk.
            if current_chunk and current_length + split_len + separator_len > self._chunk_size:
                # Join the splits in the current chunk and add to final list
                final_chunks.append(separator.join(current_chunk))
                
                # Start a new chunk, handling overlap
                # We slide a window over the previous chunk's splits to create overlap
                new_start_index = -1
                overlap_len = 0
                for i in range(len(current_chunk) - 1, -1, -1):
                    # Add the length of the split and the separator
                    overlap_len += len(current_chunk[i]) + separator_len
                    if overlap_len > self._chunk_overlap:
                        new_start_index = i
                        break
                
                if new_start_index != -1:
                    current_chunk = current_chunk[new_start_index:]
                else:
                    current_chunk = []
                
                # Recalculate the length of the new chunk with overlap
                current_length = sum(len(s) for s in current_chunk) + \
                                 max(0, len(current_chunk) - 1) * separator_len
            
            # Add the new split to the current chunk
            current_chunk.append(split)
            current_length += split_len
            if len(current_chunk) > 1:
                current_length += separator_len

        # Add the last remaining chunk
        if current_chunk:
            final_chunks.append(separator.join(current_chunk))
        
        return final_chunks

    def split_text(self, text: str) -> List[str]:
        """
        Splits a given text into a list of appropriately sized chunks.
        
        Args:
            text: The text to be split.
            
        Returns:
            A list of text chunks.
        """
        # Start with the highest-priority separator
        splits = [text]
        for separator in self._separators:
            # If the text is already in small enough chunks, we're done
            if all(len(s) <= self._chunk_size for s in splits):
                break

            # If the separator is empty, we can't split further with this method
            if separator == "":
                break
                
            # Split any chunk that is too large
            new_splits = []
            for split in splits:
                if len(split) > self._chunk_size:
                    new_splits.extend(split.split(separator))
                else:
                    new_splits.append(split)
            splits = new_splits
            
        # Merge the small splits into final chunks with overlap
        final_chunks = self._merge_splits(splits, separator if self._keep_separator else "")

        # As a final fallback, if any chunk is still too large, do a hard split.
        # This can happen if a single split without separators is > chunk_size.
        final_final_chunks: List[str] = []
        for chunk in final_chunks:
            if len(chunk) > self._chunk_size:
                for i in range(0, len(chunk), self._chunk_size - self._chunk_overlap):
                    sub_chunk = chunk[i : i + self._chunk_size]
                    if sub_chunk.strip():
                        final_final_chunks.append(sub_chunk)
            else:
                final_final_chunks.append(chunk)

        return final_final_chunks 