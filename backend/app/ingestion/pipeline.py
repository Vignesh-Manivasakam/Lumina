import os
from pathlib import Path
from typing import Optional

from app.ingestion.adaptive_parser import AdaptiveDocumentParser
from app.ingestion.audio_pipeline import AudioPipeline
from app.ingestion.contextual_headers import ContextualHeaderGenerator
from app.ingestion.document_analyzer import DocumentAnalyzer
from app.ingestion.embedder import MultimodalEmbedder
from app.ingestion.fast_embedder import LocalEmbedder
from app.ingestion.image_extractor import ImageExtractor
from app.ingestion.parent_child_chunker import ParentChildChunker
from app.ingestion.video_pipeline import VideoPipeline
from app.ingestion.chunking import MultimodalChunk
from app.retrieval.qdrant_store import QdrantStore
from app.services.llm_client import LLMClient
from app.services.supabase_client import SupabaseService


class IngestionPipeline:
    def __init__(self):
        self.llm = LLMClient()
        self.doc_parser = AdaptiveDocumentParser()
        self.analyzer = DocumentAnalyzer()
        self.img_extractor = ImageExtractor(self.llm)
        self.audio_pipeline = AudioPipeline()
        self.video_pipeline = VideoPipeline(self.llm)
        # Phase 3: hierarchical chunker replaces the legacy ChunkingService
        self.chunker = ParentChildChunker()
        self.contextual = ContextualHeaderGenerator(self.llm)
        self.embedder = MultimodalEmbedder(LocalEmbedder())
        self.qdrant = QdrantStore()
        self.supabase = SupabaseService()
        # Back-compat alias for code paths still reading pipeline.nvidia
        self.nvidia = self.llm

    def run(
        self,
        file_path: str,
        dept: str = "General",
        doc_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Run the Phase 3 ingestion pipeline.

        Stages:
        1. Adaptive parse (PDF/DOCX/PPTX/text)
        2. Document strategy analysis & parent-child chunking
        3. Image extraction (PDF only)
        4. Audio/video pipelines (existing)
        5. Contextual header generation (Anthropic pattern)
        6. Embedding (BGE-large-en-v1.5, local CPU)
        7. Qdrant upsert (parent_id / is_parent / child_ids payload)
        8. Supabase chunk metadata + status update
        """
        filename = os.path.basename(file_path)
        file_ext = Path(file_path).suffix.lower().replace(".", "")

        print(f"Ingesting file: {filename} ({file_ext}) session={session_id or '<shared>'}")
        if not doc_id:
            doc_record = self.supabase.create_document(
                filename=filename,
                file_type=file_ext,
                dept=dept,
            )
            doc_id = doc_record.get("id")
        else:
            self.supabase.update_document_status(doc_id, "processing")

        try:
            chunks: list[MultimodalChunk] = []
            full_doc_text = ""

            # --- 1. Parse + 2. Parent-child chunk (PDF/DOCX/PPTX/CSV/TSV/JSON/text) ---
            if file_ext in ["pdf", "docx", "pptx", "doc", "ppt", "txt", "md", "html", "csv", "tsv", "json"]:
                parsed_doc = self.doc_parser.parse(file_path)
                full_doc_text = parsed_doc.get("text_markdown", "") or ""

                strategy = self.analyzer.analyze(parsed_doc)
                print(f"Selected chunking strategy: {strategy.name}")

                chunks = self.chunker.chunk_pages(
                    parsed_doc=parsed_doc,
                    doc_id=doc_id,
                    dept=dept,
                    strategy=strategy,
                )

                # For PDFs, also extract embedded images
                if file_ext == "pdf":
                    print("Extracting images from PDF...")
                    img_chunks = self.img_extractor.extract_and_caption(file_path, doc_id)
                    for img in img_chunks:
                        img["doc_id"] = doc_id
                        img["metadata"] = {
                            "title": parsed_doc["metadata"].get("title", ""),
                            "dept": dept,
                            "file_type": file_ext,
                        }
                        chunks.append(MultimodalChunk(**img))

            elif file_ext in ["png", "jpg", "jpeg", "webp", "bmp", "gif"]:
                import base64
                print(f"Processing image file: {filename}...")
                with open(file_path, "rb") as img_f:
                    b64 = base64.b64encode(img_f.read()).decode("utf-8")
                
                try:
                    caption = self.img_extractor._caption_image(b64, file_ext)
                except Exception as exc:
                    print(f"VLM image captioning fallback: {exc}")
                    caption = f"Uploaded architecture / diagram image: {filename}"

                from app.utils import generate_uuid
                from app.ingestion.chunking import Modality
                img_chunk = MultimodalChunk(
                    chunk_id=generate_uuid(f"{doc_id}_img_1"),
                    doc_id=doc_id,
                    modality=Modality.IMAGE,
                    page_num=1,
                    base64=b64,
                    caption=caption,
                    text_repr=f"[IMAGE {filename}] {caption}",
                    metadata={"title": filename, "dept": dept, "file_type": file_ext},
                )
                chunks.append(img_chunk)
                full_doc_text = img_chunk.text_repr

            elif file_ext in ["mp3", "wav", "m4a"]:
                print("Processing audio transcript...")
                audio_chunks = self.audio_pipeline.process(file_path, doc_id)
                for chunk in audio_chunks:
                    chunk["metadata"] = {"dept": dept, "file_type": file_ext}
                    chunks.append(MultimodalChunk(**chunk))
                full_doc_text = " ".join(c.text_repr for c in chunks if c.text_repr)

            elif file_ext in ["mp4", "avi", "mov"]:
                print("Processing video frames...")
                video_chunks = self.video_pipeline.process(file_path, doc_id)
                for chunk in video_chunks:
                    chunk["metadata"] = {"dept": dept, "file_type": file_ext}
                    chunks.append(MultimodalChunk(**chunk))
                full_doc_text = " ".join(c.text_repr for c in chunks if c.text_repr)

            else:
                raise ValueError(f"Unsupported file format: {file_ext}")

            if not chunks:
                print("No chunks generated.")
                self.supabase.update_document_status(doc_id, "failed")
                return doc_id

            # --- Phase 2: tag every chunk with the uploader's session ----
            if session_id:
                for c in chunks:
                    c.session_id = session_id
                    c.metadata.setdefault("session_id", session_id)

            # --- 3. Contextual header generation (Anthropic pattern) ----
            doc_metadata = {
                "title": filename,
                "file_type": file_ext,
                "dept": dept,
            }
            self.contextual.enrich_chunks(
                chunks=chunks,
                full_document_text=full_doc_text,
                doc_metadata=doc_metadata,
            )

            # --- 4. Embedding ------------------------------------------
            print(f"Generating embeddings for {len(chunks)} chunks...")
            chunks = self.embedder.embed_chunks(chunks)

            # --- 5. Upsert to Qdrant ------------------------------------
            print("Upserting chunks to Qdrant...")
            self.qdrant.upsert(chunks, session_id=session_id)

            # --- 6. Supabase metadata -----------------------------------
            print("Saving metadata to Supabase...")
            supabase_chunks = [
                {
                    "id": c.chunk_id,
                    "doc_id": c.doc_id,
                    "modality": c.modality.value,
                    "page_num": c.page_num,
                    "timestamp_sec": c.timestamp_sec,
                    "text_repr": c.text_repr,
                    "has_image": c.base64 is not None,
                }
                for c in chunks
            ]
            self.supabase.insert_chunks(supabase_chunks)

            self.supabase.update_document_status(doc_id, "ready", num_chunks=len(chunks))
            print(f"Successfully ingested document {filename}!")
            return doc_id

        except Exception as e:
            print(f"Pipeline ingestion failed for {filename}: {e}")
            self.supabase.update_document_status(doc_id, "failed")
            raise e
