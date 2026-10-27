from typing import List
import logfire

def chunk_text(text: str, chunk_size: int = 1500, overlap_size: int = 250) -> List[str]:
    """
    Chunks text with a sliding window overlap to maintain context across boundaries.
    Attempts to break cleanly at paragraphs, sentences, or spaces.
    """
    with logfire.span("✂️ Text Chunking", text_length=len(text)):
        if not text.strip():
            return []

        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + chunk_size

            # If the remaining text fits in one chunk, grab it and finish
            if end >= text_len:
                final_chunk = text[start:].strip()
                if final_chunk:
                    chunks.append(final_chunk)
                break

            # Find a natural breakpoint to avoid cutting words in half
            # Prioritize: Paragraph -> Newline -> Sentence -> Space
            break_point = end
            for separator in ["\n\n", "\n", ". ", " "]:
                last_sep_index = text.rfind(separator, start, end)
                # Ensure the breakpoint isn't too far back (creating tiny chunks)
                if last_sep_index != -1 and last_sep_index > start + (chunk_size // 2):
                    break_point = last_sep_index + len(separator)
                    break

            chunk = text[start:break_point].strip()
            if chunk:
                chunks.append(chunk)

            # Shift the start pointer backward by the overlap size to maintain context
            # Ensure we always move forward to prevent infinite loops
            start = max(break_point - overlap_size, start + 1)

        valid_chunks = [c for c in chunks if c.strip()]
        logfire.info(f"✅ Generated {len(valid_chunks)} chunks with {overlap_size}-char overlap")
        return valid_chunks