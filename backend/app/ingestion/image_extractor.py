import base64
import fitz  # PyMuPDF

class ImageExtractor:
    def __init__(self, llm_client):
        self.llm = llm_client
        # Back-compat alias
        self.nvidia = llm_client

    def extract_and_caption(self, pdf_path: str, doc_id: str) -> list[dict]:
        """Extract embedded images from PDF, generate captions via Gemini VLM."""
        from app.utils import generate_uuid
        doc = fitz.open(pdf_path)
        image_chunks = []

        for page_num, page in enumerate(doc):
            images = page.get_images(full=True)
            for img_index, img in enumerate(images):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    if not base_image:
                        continue
                    
                    img_bytes = base_image["image"]
                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                    
                    ext = base_image.get("ext", "jpeg")
                    # Generate VLM caption
                    caption = self._caption_image(b64, ext)

                    image_chunks.append({
                        "chunk_id": generate_uuid(f"{doc_id}_img_{page_num + 1}_{img_index}"),
                        "modality": "image",
                        "page_num": page_num + 1,
                        "base64": b64,
                        "caption": caption,
                        "text_repr": f"[IMAGE page {page_num + 1}] {caption}",
                    })
                except Exception as e:
                    # Log exception and continue parsing other images
                    print(f"Skipping image {img_index} on page {page_num + 1} due to error: {e}")

        return image_chunks

    def _caption_image(self, b64: str, ext: str) -> str:
        mime = f"image/{ext}" if ext != "jpg" else "image/jpeg"
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"}
                    },
                    {
                        "type": "text",
                        "text": "Describe this image in detail for document retrieval. "
                                "Focus on: type (chart/diagram/figure), key data points, "
                                "labels, and what concept it illustrates."
                    }
                ]
            }
        ]
        resp = self.llm.generate(messages, stream=False)
        return resp.content
