import logging
from pathlib import Path
import pypdf
from docx import Document
from typing import List, Dict, Any
from dataclasses import dataclass

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class DocumentChunk:
    file_name: str
    document_title: str
    chunk_content: str
    chunk_index: int

# Handles processing of PDF and DOCX documents for vector indexing
class DocumentProcessor:
    def __init__(self, folder_path: str):
        self.folder_path = Path(folder_path)
        self.chunk_delimiter = "---CHUNK_BOUNDARY---"
        self.supported_extensions = {'.pdf', '.docx'}
        
    def extract_text_from_pdf(self, file_path: Path) -> str:
        try:
            with open(file_path, 'rb') as file:
                reader = pypdf.PdfReader(file)
                text = ""
                
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                    
                return text.strip()
                
        except Exception as e:
            logger.error(f"Error reading PDF {file_path}: {str(e)}")
            return ""
    
    def extract_text_from_docx(self, file_path: Path) -> str:
        try:
            doc = Document(file_path)
            paragraphs = []
            
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    paragraphs.append(paragraph.text)
                    
            return "\n".join(paragraphs)
            
        except Exception as e:
            logger.error(f"Error reading DOCX {file_path}: {str(e)}")
            return ""
    
    def extract_text_from_file(self, file_path: Path) -> str:
        extension = file_path.suffix.lower()
        
        if extension == '.pdf':
            return self.extract_text_from_pdf(file_path)
        elif extension == '.docx':
            return self.extract_text_from_docx(file_path)
        else:
            logger.warning(f"Unsupported file type: {extension}")
            return ""
    
    def parse_document_content(self, text: str) -> tuple[str, List[str]]:
        if not text.strip():
            return "", []
        
        lines = text.split('\n')
        
        # First line is the title
        document_title = lines[0].strip() if lines else ""
        
        # Join remaining lines and split by chunk delimiter
        remaining_content = '\n'.join(lines[1:]) if len(lines) > 1 else ""
        
        if self.chunk_delimiter in remaining_content:
            chunks = [chunk.strip() for chunk in remaining_content.split(self.chunk_delimiter)]
            # Filter out empty chunks
            chunks = [chunk for chunk in chunks if chunk]
        else:
            # Add - alternative chunking strategies
            # If no delimiter found, treat entire remaining content as one chunk for now
            chunks = [remaining_content.strip()] if remaining_content.strip() else []
        
        return document_title, chunks
    
    def process_single_file(self, file_path: Path) -> List[DocumentChunk]:
        logger.info(f"Processing file: {file_path.name}")
        
        # Extract text from file
        text = self.extract_text_from_file(file_path)
        
        if not text:
            logger.warning(f"No text extracted from {file_path.name}")
            return []
        
        # Parse document content
        document_title, chunks = self.parse_document_content(text)
        
        if not document_title:
            logger.warning(f"No title found in {file_path.name}")
            document_title = file_path.stem  # Use filename as fallback
        
        # Create DocumentChunk objects
        chunk_objects = []
        for i, chunk_content in enumerate(chunks):
            chunk_obj = DocumentChunk(
                file_name=file_path.name,
                document_title=document_title,
                chunk_content=chunk_content,
                chunk_index=i
            )
            chunk_objects.append(chunk_obj)
        
        logger.info(f"Extracted {len(chunk_objects)} chunks from {file_path.name}")
        return chunk_objects
    
    def process_all_documents(self) -> List[DocumentChunk]:
        if not self.folder_path.exists():
            raise FileNotFoundError(f"Folder not found: {self.folder_path}")
        
        all_chunks = []
        processed_files = 0
        
        # Get all supported files
        supported_files = [
            f for f in self.folder_path.iterdir() 
            if f.is_file() and f.suffix.lower() in self.supported_extensions
        ]
        
        if not supported_files:
            logger.warning(f"No supported files found in {self.folder_path}")
            return []
        
        logger.info(f"Found {len(supported_files)} supported files")
        
        for file_path in supported_files:
            try:
                chunks = self.process_single_file(file_path)
                all_chunks.extend(chunks)
                processed_files += 1
                
            except Exception as e:
                logger.error(f"Failed to process {file_path.name}: {str(e)}")
                continue
        
        logger.info(f"Successfully processed {processed_files} files, extracted {len(all_chunks)} total chunks")
        return all_chunks
    
    def export_chunks_to_dict(self, chunks: List[DocumentChunk]) -> List[Dict[str, Any]]:
        return [
            {
                'file_name': chunk.file_name,
                'document_title': chunk.document_title,
                'chunk_content': chunk.chunk_content,
                'chunk_index': chunk.chunk_index
            }
            for chunk in chunks
        ]
