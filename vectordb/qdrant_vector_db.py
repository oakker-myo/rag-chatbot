import os
import json
import logging
import uuid
from typing import List, Dict, Any
from datetime import datetime
from .chunk_docs import DocumentProcessor, DocumentChunk
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

# Configuration file for service settings
CONFIG_FILE = "config.json"

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Vector Search Service using Qdrant and Sentence Transformers
class VectorSearchService:
    def __init__(self, config_path: str = CONFIG_FILE):
        self.config = self._load_config(config_path)
        self.qdrant_client = None
        self.embedding_model = None
        self._initialise_clients()
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        default_config = {
            "qdrant_host": "localhost",
            "qdrant_port": 6333,
            "collection_name": "documents",
            "embedding_model": "all-MiniLM-L6-v2",
            "default_documents_folder": "./documents",
            "chunk_size": 1000,
            "chunk_overlap": 200
        }
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                logger.info(f"Loaded configuration from {config_path}")
                # Merge with default config
                default_config.update(config)
            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {e}")
                logger.info("Using default configuration")
        else:
            # Create default config file
            self._save_config(default_config, config_path)
            logger.info(f"Created default configuration at {config_path}")
        
        return default_config
    
    def _save_config(self, config: Dict[str, Any], config_path: str):
        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
    
    def _initialise_clients(self):
        try:
            # Initialise Qdrant client
            logger.info(f"Connecting to Qdrant at {self.config['qdrant_host']}:{self.config['qdrant_port']}")
            self.qdrant_client = QdrantClient(
                host=self.config['qdrant_host'],
                port=self.config['qdrant_port']
            )
            
            # Test connection
            self.qdrant_client.get_collections()
            logger.info("Successfully connected to Qdrant")
            
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {str(e)}")
            logger.error("Make sure Qdrant is running:")
            logger.error("  Docker: docker run -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant")
            raise
        
        try:
            # Initialise embedding model
            logger.info(f"Loading embedding model: {self.config['embedding_model']}")
            self.embedding_model = SentenceTransformer(self.config['embedding_model'])
            logger.info("Successfully loaded embedding model")
            
        except Exception as e:
            logger.error(f"Failed to load embedding model: {str(e)}")
            raise
    
    def create_index(self, overwrite: bool = False) -> bool:
        try:
            collection_name = self.config['collection_name']
            
            # Check if collection exists
            collections = self.qdrant_client.get_collections()
            collection_exists = any(
                col.name == collection_name 
                for col in collections.collections
            )
            
            if collection_exists:
                if overwrite:
                    logger.warning(f"Deleting existing collection: {collection_name}")
                    self.qdrant_client.delete_collection(collection_name)
                else:
                    logger.info(f"Collection '{collection_name}' already exists")
                    return True
            
            # Get embedding dimension
            sample_embedding = self.embedding_model.encode(["sample text"])
            embedding_dim = len(sample_embedding[0])
            
            # Create collection
            logger.info(f"Creating collection: {collection_name} (dimension: {embedding_dim})")
            self.qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=embedding_dim,
                    distance=Distance.COSINE
                )
            )
            
            logger.info(f"Successfully created collection: {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create index: {str(e)}")
            return False
    
    def index_documents(self, documents_folder: str = None, overwrite: bool = False) -> Dict[str, Any]:
        if documents_folder is None:
            documents_folder = self.config['default_documents_folder']
        
        if not os.path.exists(documents_folder):
            raise FileNotFoundError(f"Documents folder not found: {documents_folder}")
        
        results = {
            "status": "failed",
            "documents_folder": documents_folder,
            "total_chunks": 0,
            "processing_time": 0,
            "error": None
        }
        
        try:
            start_time = datetime.now()
            
            # Create index
            logger.info("Step 1: Creating/checking vector index")
            if not self.create_index(overwrite=overwrite):
                results["error"] = "Failed to create index"
                return results
            
            # Process documents
            logger.info("Step 2: Processing documents")
            doc_processor = DocumentProcessor(documents_folder)
            chunks = doc_processor.process_all_documents()
            
            if not chunks:
                logger.warning("No chunks extracted from documents")
                results["status"] = "no_documents"
                return results
            
            results["total_chunks"] = len(chunks)
            
            # Generate embeddings and store
            logger.info(f"Step 3: Generating embeddings for {len(chunks)} chunks")
            self._store_chunks(chunks)
            
            # Verify
            collection_info = self.qdrant_client.get_collection(self.config['collection_name'])
            
            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds()
            
            results.update({
                "status": "success",
                "processing_time": processing_time,
                "points_in_collection": collection_info.points_count
            })
            
            logger.info(f"Indexing completed successfully!")
            logger.info(f"Processed: {len(chunks)} chunks")
            logger.info(f"Time: {processing_time:.2f} seconds")
            logger.info(f"Total points in collection: {collection_info.points_count}")
            
            return results
            
        except Exception as e:
            results["error"] = str(e)
            logger.error(f"Indexing failed: {str(e)}")
            return results
    
    def _store_chunks(self, chunks: List[DocumentChunk]):
        # Prepare texts for embedding
        texts = [chunk.chunk_content for chunk in chunks]
        
        # Generate embeddings in batches
        logger.info("Generating embeddings...")
        embeddings = self.embedding_model.encode(
            texts,
            show_progress_bar=True,
            batch_size=32
        )
        
        # Prepare points for Qdrant
        points = []
        for chunk, embedding in zip(chunks, embeddings):
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding.tolist(),
                payload={
                    "file_name": chunk.file_name,
                    "document_title": chunk.document_title,
                    "chunk_content": chunk.chunk_content,
                    "chunk_index": chunk.chunk_index,
                    "timestamp": datetime.now().isoformat(),
                    "content_length": len(chunk.chunk_content)
                }
            )
            points.append(point)
        
        # Store in Qdrant
        logger.info(f"Storing {len(points)} points in vector database...")
        self.qdrant_client.upsert(
            collection_name=self.config['collection_name'],
            points=points
        )
    
    def search(self, query: str, limit: int = 5, score_threshold: float = 0.2) -> List[Dict[str, Any]]:
        try:
            # Check if collection exists
            try:
                collection_info = self.qdrant_client.get_collection(self.config['collection_name'])
                if collection_info.points_count == 0:
                    logger.warning("Collection is empty. Run indexing first.")
                    return []
            except Exception:
                logger.error("Collection not found. Run indexing first.")
                return []
            
            # Generate query embedding
            query_embedding = self.embedding_model.encode([query])[0].tolist()
            
            # Search in Qdrant
            search_results = self.qdrant_client.search(
                collection_name=self.config['collection_name'],
                query_vector=query_embedding,
                limit=limit,
                score_threshold=score_threshold
            )
            
            # Format results
            results = []
            for result in search_results:
                results.append({
                    "score": float(result.score),
                    "file_name": result.payload["file_name"],
                    "document_title": result.payload["document_title"],
                    "chunk_content": result.payload["chunk_content"],
                    "chunk_index": result.payload["chunk_index"],
                    "content_length": result.payload["content_length"]
                })
            
            logger.info(f"Found {len(results)} results for query: '{query[:50]}{'...' if len(query) > 50 else ''}'")
            return results
            
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            return []

def search_documents(query: str, limit: int = 5, score_threshold: float = 0.5, config_path: str = CONFIG_FILE) -> List[Dict[str, Any]]:
    try:
        service = VectorSearchService(config_path)
        return service.search(query, limit, score_threshold)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return []

def index_documents_standalone(documents_folder: str, overwrite: bool = False, config_path: str = CONFIG_FILE) -> Dict[str, Any]:
    try:
        service = VectorSearchService(config_path)
        return service.index_documents(documents_folder, overwrite)
    except Exception as e:
        logger.error(f"Indexing failed: {e}")
        return {"status": "failed", "error": str(e)}