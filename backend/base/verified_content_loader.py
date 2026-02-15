import os
import json
import logging
import warnings
from typing import List, Dict, Any, Optional

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".json", ".pdf", ".pptx", ".py", ".txt", ".md"}
SKIP_FILES = {".DS_Store", ".keep", ".keep 2", ".gitkeep", "Thumbs.db"}
CONTENT_CATEGORIES = {"Syllabus", "Lectures", "Exercises", "References"}


def scan_courses(base_dir: str) -> List[Dict[str, Any]]:
    """Iterates course folders (pattern: {code}_{name}_{term}), returns list of course metadata dicts."""
    courses = []
    if not os.path.isdir(base_dir):
        logger.warning(f"Verified content directory does not exist: {base_dir}")
        return courses

    for entry in sorted(os.listdir(base_dir)):
        entry_path = os.path.join(base_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        if entry.startswith("."):
            continue

        parts = entry.split("_", 2)
        if len(parts) >= 3:
            course_code = parts[0]
            course_name = parts[1].replace("-", " ")
            term = parts[2].replace("-", " ")
        elif len(parts) == 2:
            course_code = parts[0]
            course_name = parts[1].replace("-", " ")
            term = "unknown"
        else:
            course_code = entry
            course_name = entry
            term = "unknown"

        courses.append({
            "course_code": course_code,
            "course_name": course_name,
            "term": term,
            "directory": entry_path,
        })

    logger.info(f"Found {len(courses)} verified courses in {base_dir}")
    return courses


def load_file(file_path: str) -> List[Document]:
    """Dispatches file loading based on extension. Returns list of Document objects."""
    basename = os.path.basename(file_path)
    if basename in SKIP_FILES or basename.startswith("."):
        return []

    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        return []

    try:
        if ext == ".json":
            return _load_json(file_path)
        elif ext in (".pdf", ".pptx"):
            return _load_with_docling(file_path)
        else:
            return _load_text(file_path)
    except Exception as e:
        logger.error(f"Failed to load file {file_path}: {e}")
        return []


def _load_json(file_path: str) -> List[Document]:
    """Parse JSON file, extract content field, return as Document."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    content = data.get("content", "")
    title = data.get("title", "")
    if not content.strip():
        return []

    doc = Document(
        page_content=content,
        metadata={"title": title, "source": file_path},
    )
    return [doc]


def _load_with_docling(file_path: str) -> List[Document]:
    """Use DoclingLoader for PDF and PPTX files."""
    from langchain_docling import DoclingLoader
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    pipeline_options = PdfPipelineOptions(allow_external_plugins=True)
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )
    loader = DoclingLoader(file_path=file_path, converter=converter)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Token indices sequence length is longer than the specified maximum sequence length",
        )
        docs = loader.load()
    return docs


def _load_text(file_path: str) -> List[Document]:
    """Read plain text files (.py, .txt, .md)."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    if not content.strip():
        return []

    doc = Document(
        page_content=content,
        metadata={"source": file_path},
    )
    return [doc]


def load_course_documents(
    course_dir: str, course_metadata: Dict[str, Any]
) -> List[Document]:
    """Loads files from Syllabus/, Lectures/, Exercises/, References/ subdirectories."""
    documents = []

    for category in CONTENT_CATEGORIES:
        category_dir = os.path.join(course_dir, category)
        if not os.path.isdir(category_dir):
            continue

        for root, _dirs, files in os.walk(category_dir):
            for fname in sorted(files):
                file_path = os.path.join(root, fname)
                docs = load_file(file_path)
                for doc in docs:
                    doc.metadata.update({
                        "source_type": "verified_content",
                        "course_code": course_metadata["course_code"],
                        "course_name": course_metadata["course_name"],
                        "term": course_metadata["term"],
                        "content_category": category,
                        "file_name": fname,
                    })
                documents.extend(docs)

    logger.info(
        f"Loaded {len(documents)} documents from course "
        f"{course_metadata['course_code']} ({course_metadata['course_name']})"
    )
    return documents


def load_all_verified_content(base_dir: str) -> List[Document]:
    """Top-level function returning flat list of Document objects from all courses."""
    courses = scan_courses(base_dir)
    all_documents = []

    for course in courses:
        docs = load_course_documents(course["directory"], course)
        all_documents.extend(docs)

    logger.info(f"Total verified content documents loaded: {len(all_documents)}")
    return all_documents
