import os
import logging
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import contextmanager
from psycopg2.extras import RealDictCursor, Json
from psycopg2.pool import ThreadedConnectionPool

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database config
class DatabaseConfig:
    def __init__(self):
        self.host = os.getenv('DB_HOST', 'localhost')
        self.port = os.getenv('DB_PORT', '5432')
        self.database = os.getenv('DB_NAME', 'rag_chatbot')
        self.user = os.getenv('DB_USER', 'rag_user')
        self.password = os.getenv('DB_PASSWORD', 'rag_password')
        self.min_connections = int(os.getenv('DB_MIN_CONNECTIONS', '1'))
        self.max_connections = int(os.getenv('DB_MAX_CONNECTIONS', '10'))

# Database connection and operations manager
class DatabaseManager:
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.pool = None
        self._initialize_pool()
    
    def _initialize_pool(self):
        try:
            self.pool = ThreadedConnectionPool(
                self.config.min_connections,
                self.config.max_connections,
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password,
                cursor_factory=RealDictCursor
            )
            logger.info("Database connection pool initialised successfully")
        except Exception as e:
            logger.error(f"Failed to initialise database pool: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database operation failed: {e}")
            raise
        finally:
            if conn:
                self.pool.putconn(conn)
    
    def close_pool(self):
        if self.pool:
            self.pool.closeall()
            logger.info("Database connection pool closed")

# Data Access Object for sessions
class SessionDAO:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def create_session(self, session_id: str, metadata: Dict = None) -> Dict:
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO sessions (session_id, metadata)
                    VALUES (%s, %s)
                    RETURNING *
                """, (session_id, Json(metadata or {})))
                
                result = cur.fetchone()
                conn.commit()
                return dict(result)
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM sessions WHERE session_id = %s
                """, (session_id,))
                
                result = cur.fetchone()
                return dict(result) if result else None
    
    def update_session(self, session_id: str, conversation_data: List = None, end_timestamp: datetime = None, metadata: Dict = None) -> Optional[Dict]:
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                # Build dynamic update query
                set_clauses = []
                params = []
                
                if conversation_data is not None:
                    set_clauses.append("conversation_data = %s")
                    params.append(Json(conversation_data))
                
                if end_timestamp is not None:
                    set_clauses.append("end_timestamp = %s")
                    params.append(end_timestamp)
                
                if metadata is not None:
                    set_clauses.append("metadata = %s")
                    params.append(Json(metadata))
                
                if not set_clauses:
                    return self.get_session(session_id)
                
                params.append(session_id)
                
                cur.execute(f"""
                    UPDATE sessions 
                    SET {', '.join(set_clauses)}
                    WHERE session_id = %s
                    RETURNING *
                """, params)
                
                result = cur.fetchone()
                conn.commit()
                return dict(result) if result else None

# Data Access Object for messages  
class MessageDAO:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def create_message(self, message_data: Dict) -> Dict:
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                # Get session UUID for foreign key
                cur.execute("""
                    SELECT id FROM sessions WHERE session_id = %s
                """, (message_data['session_id'],))
                
                session_result = cur.fetchone()
                if not session_result:
                    raise ValueError(f"Session {message_data['session_id']} not found")
                
                session_uuid = session_result['id']
                
                cur.execute("""
                    INSERT INTO messages (
                        message_id, session_id, session_uuid, message_count,
                        question, answer, sources, history, duration, 
                        timestamp, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                """, (
                    message_data['id'],
                    message_data['session_id'],
                    session_uuid,
                    message_data['message_count'],
                    message_data['question'],
                    message_data['answer'],
                    Json(message_data.get('sources', [])),
                    Json(message_data.get('history', [])),
                    message_data.get('duration', 0),
                    datetime.fromisoformat(message_data['timestamp'].replace('Z', '+00:00')) if isinstance(message_data['timestamp'], str) else message_data['timestamp'],
                    Json(message_data.get('metadata', {}))
                ))
                
                result = cur.fetchone()
                conn.commit()
                return dict(result)
    
    def get_messages_by_session(self, session_id: str) -> List[Dict]:
        """Get all messages for a session"""
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM messages 
                    WHERE session_id = %s 
                    ORDER BY message_count ASC
                """, (session_id,))
                
                return [dict(row) for row in cur.fetchall()]
       
# Global database manager instance
db_config = DatabaseConfig()
db_manager = DatabaseManager(db_config)
session_dao = SessionDAO(db_manager)
message_dao = MessageDAO(db_manager)

# Initialise database connection
def init_database():
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                logger.info("Database connection test successful")
        return True
    except Exception as e:
        logger.error(f"Database initialisation failed: {e}")
        return False

# Close database connection
def close_database():
    db_manager.close_pool()