import logging
from typing import List, Dict, Any, Optional, Union

from omegaconf import DictConfig
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
from langchain_text_splitters.base import TextSplitter

from base.embedder_factory import EmbedderFactory
from base.rag_factory import TextSplitterFactory, VectorStoreFactory
from base.verified_content_loader import load_all_verified_content, scan_courses
from utils.config import ensure_config_dict

logger = logging.getLogger(__name__)


class VerifiedContentManager:

    def __init__(
        self,
        embedder: Embeddings,
        text_splitter: TextSplitter,
        persist_directory: str = "./data/vectorstore",
        collection_name: str = "verified_content",
    ):
        self.embedder = embedder
        self.text_splitter = text_splitter
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.vectorstore: VectorStore = VectorStoreFactory.create(
            vectorstore_type="chroma",
            collection_name=collection_name,
            persist_directory=persist_directory,
            embedder=embedder,
        )

    @staticmethod
    def from_config(
        config: Union[DictConfig, Dict[str, Any]],
    ) -> "VerifiedContentManager":
        config = ensure_config_dict(config)
        embedder = EmbedderFactory.create(
            model=config.get("embedder", {}).get("model_name", "sentence-transformers/all-mpnet-base-v2"),
            model_provider=config.get("embedder", {}).get("provider", "huggingface"),
        )
        verified_cfg = config.get("verified_content", {})
        text_splitter = TextSplitterFactory.create(
            splitter_type=config.get("rag", {}).get("text_splitter_type", "recursive_character"),
            chunk_size=verified_cfg.get("chunk_size", 500),
            chunk_overlap=config.get("rag", {}).get("chunk_overlap", 0),
        )
        return VerifiedContentManager(
            embedder=embedder,
            text_splitter=text_splitter,
            persist_directory=config.get("vectorstore", {}).get("persist_directory", "./data/vectorstore"),
            collection_name=verified_cfg.get("collection_name", "verified_content"),
        )

    def index_verified_content(self, base_dir: str) -> int:
        """Loads, splits, and adds verified content to vectorstore. Skips if collection already has documents."""
        existing_count = self.vectorstore._collection.count()
        if existing_count > 0:
            logger.info(
                f"Verified content collection '{self.collection_name}' already has "
                f"{existing_count} documents. Skipping indexing."
            )
            return existing_count

        documents = load_all_verified_content(base_dir)
        if not documents:
            logger.warning("No verified content documents found to index.")
            return 0

        documents = [doc for doc in documents if len(doc.page_content.strip()) > 0]
        split_docs = self.text_splitter.split_documents(documents)

        for doc in split_docs:
            if "source_type" not in doc.metadata:
                doc.metadata["source_type"] = "verified_content"
            # ChromaDB only accepts str, int, float, bool, or None metadata values.
            # Docling injects complex nested dicts/lists — strip them out.
            doc.metadata = {
                k: v for k, v in doc.metadata.items()
                if isinstance(v, (str, int, float, bool)) or v is None
            }

        self.vectorstore.add_documents(split_docs, embedding_function=self.embedder)
        final_count = self.vectorstore._collection.count()
        logger.info(
            f"Indexed {len(split_docs)} verified content chunks into "
            f"'{self.collection_name}' (total: {final_count})"
        )
        return final_count

    def retrieve(self, query: str, k: int = 5) -> List[Document]:
        """Similarity search against the verified content collection."""
        try:
            count = self.vectorstore._collection.count()
            if count == 0:
                return []
            results = self.vectorstore.similarity_search(query, k=min(k, count))
            return results
        except Exception as e:
            logger.error(f"Error retrieving from verified content: {e}")
            return []

    def list_courses(self, base_dir: str = "resources/verified-course-content") -> List[Dict[str, Any]]:
        """Return list of course metadata dicts from the verified content directory."""
        return scan_courses(base_dir)
