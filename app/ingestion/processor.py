import os
import sys
import uuid
import json
import time
import re
import random
import logfire

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.config import settings
from app.services.retrieval.embedding import embed_texts, get_embedding_dim
from app.ingestion.loaders.pdf import parse_pdf
from app.ingestion.loaders.html import parse_html
from app.ingestion.loaders.text import parse_text
from app.ingestion.chunking.splitter import chunk_text

logfire.configure(service_name="enterprise-ingestion-service")

PROCESSED_DATA_DIR = "processed_data"

qdrant_client = QdrantClient(
    url=settings.QDRANT_URL,
    api_key=settings.QDRANT_API_KEY,
    timeout=60,
)


def save_processed_locally(data: dict, source_type: str, filename: str) -> str:
    """Save parsed chunk metadata as JSON in processed_data/<source_type>/."""
    folder = os.path.join(PROCESSED_DATA_DIR, source_type)
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, f"{filename}.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return dest


def safe_embed_with_retry(chunks_batch: list, max_retries: int = 5) -> list:
    """Embeds a batch of chunks with exponential backoff and retryDelay extraction."""
    attempt = 0
    while attempt < max_retries:
        try:
            return embed_texts(chunks_batch)
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                # Attempt to extract exact retryDelay from Google RPC error payload
                delay_match = re.search(r'retryDelay["\']?\s*[:=]\s*["\']?(\d+)', error_msg, re.IGNORECASE)
                if delay_match:
                    wait_time = int(delay_match.group(1))
                    logfire.warning(f"API requested wait time. Sleeping for {wait_time} seconds...")
                else:
                    # Fallback to exponential backoff (starts at ~2s, then ~4s, ~8s, etc. up to 60s)
                    wait_time = min(60, (2 ** attempt) + random.uniform(0, 1))
                    logfire.warning(f"Rate limited. Exponential backoff: sleeping for {wait_time:.2f} seconds...")
                
                time.sleep(wait_time)
                attempt += 1
            else:
                # Re-raise if the error is not a rate limit
                raise e
                
    raise RuntimeError(f"Failed to embed batch after {max_retries} attempts due to persistent rate limits.")


def process_file(file_path: str, filename: str, source_type: str):
    """Parse → chunk → save locally → embed → index in Qdrant."""
    with logfire.span("Processing File", file=filename, source=source_type):
        try:
            # 1. Extract text
            ext = filename.lower().rsplit(".", 1)[-1]
            if ext == "pdf":
                full_text = parse_pdf(file_path)
            elif ext in ("html", "htm"):
                full_text = parse_html(file_path)
            elif ext == "txt":
                full_text = parse_text(file_path)
            elif ext in ("docx", "pptx"):
                from app.ingestion.loaders.office import parse_office
                full_text = parse_office(file_path)
            else:
                logfire.warning(f"Skipping unsupported file type: {filename}")
                return

            if not full_text or not full_text.strip():
                logfire.warning(f"No text extracted from {filename} — skipping.")
                return

            # 2. Chunk text
            chunks = chunk_text(full_text)
            if not chunks:
                return

            # 3. Save processed metadata locally
            processed_data = {
                "filename": filename,
                "source_type": source_type,
                "chunks": chunks,
            }
            local_path = save_processed_locally(processed_data, source_type, filename)
            logfire.info(f"Saved processed data → {local_path}")

            # 4. Embed in paced batches to avoid overloading the API
            embeddings = []
            EMBED_BATCH_SIZE = 10  # Reduced payload size per request
            
            with logfire.span("Vectorizing"):
                for i in range(0, len(chunks), EMBED_BATCH_SIZE):
                    chunk_batch = chunks[i:i + EMBED_BATCH_SIZE]
                    batch_embeddings = safe_embed_with_retry(chunk_batch)
                    embeddings.extend(batch_embeddings)
                    
                    # Inter-batch pacing to keep RPM stable
                    time.sleep(1)

            # 5. Index in Qdrant
            with logfire.span("Indexing"):
                points = [
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload={
                            "text": chunk,
                            "source": filename,
                            "source_type": source_type,
                        },
                    )
                    for chunk, vector in zip(chunks, embeddings)
                ]

                # BATCH UPSERT for Qdrant
                QDRANT_BATCH_SIZE = 100
                for i in range(0, len(points), QDRANT_BATCH_SIZE):
                    batch = points[i:i + QDRANT_BATCH_SIZE]
                    qdrant_client.upsert(
                        collection_name=settings.QDRANT_COLLECTION,
                        points=batch,
                    )
                
                logfire.info(f"Indexed {len(points)} points to Qdrant from {filename}.")

        except Exception as e:
            logfire.error(f"Failed to process {filename}: {e}")


def process_directory(dir_path: str, source_type: str):
    """Process every file in a directory."""
    with logfire.span("Scanning Directory", path=dir_path, source=source_type):
        files = [f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))]
        logfire.info(f"Found {len(files)} files in {dir_path}.")
        for filename in files:
            process_file(os.path.join(dir_path, filename), filename, source_type)
            # Maintain a minor buffer between whole files
            time.sleep(2)


def run_universal_ingestion(base_dir: str, explicit_source_type: str = None, wipe: bool = False):
    """
    Scan base_dir, map sub-folders to source types, and ingest all documents.
    """
    with logfire.span("Universal Ingestion Started", base_directory=base_dir):
        if wipe:
            with logfire.span("Wiping Collection"):
                if qdrant_client.collection_exists(settings.QDRANT_COLLECTION):
                    qdrant_client.delete_collection(settings.QDRANT_COLLECTION)
                    logfire.info(f"Collection '{settings.QDRANT_COLLECTION}' deleted.")

        if not qdrant_client.collection_exists(settings.QDRANT_COLLECTION):
            dim = get_embedding_dim()
            qdrant_client.create_collection(
                collection_name=settings.QDRANT_COLLECTION,
                vectors_config=models.VectorParams(
                    size=dim,
                    distance=models.Distance.COSINE,
                ),
            )
            logfire.info(f"Created collection '{settings.QDRANT_COLLECTION}' ({dim}-dim, Cosine).")

        subdirs = [
            d for d in os.listdir(base_dir)
            if os.path.isdir(os.path.join(base_dir, d))
        ]

        if not subdirs:
            if explicit_source_type:
                source_type = explicit_source_type
            else:
                base_name = os.path.basename(os.path.normpath(base_dir)).lower()
                source_type = (
                    "true" if "true" in base_name
                    else "noisy" if "noisy" in base_name
                    else "general"
                )
            logfire.info(f"No sub-folders found — processing '{base_dir}' as '{source_type}'.")
            process_directory(base_dir, source_type)
        else:
            for subdir in subdirs:
                source_type = (
                    "true" if "true" in subdir.lower()
                    else "noisy" if "noisy" in subdir.lower()
                    else subdir
                )
                process_directory(os.path.join(base_dir, subdir), source_type)

if __name__ == "__main__":
    wipe_requested = "--wipe" in sys.argv
    clean_args = [a for a in sys.argv if a != "--wipe"]

    target_dir = clean_args[1] if len(clean_args) > 1 else "DATA"
    explicit_type = clean_args[2] if len(clean_args) > 2 else None

    if not os.path.exists(target_dir):
        print(f"Error: path '{target_dir}' does not exist.")
        sys.exit(1)

    run_universal_ingestion(target_dir, explicit_source_type=explicit_type, wipe=wipe_requested)
    logfire.info("Ingestion job completed.")
    print("Ingestion job completed.")