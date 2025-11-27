import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from threading import Lock
import logging

logger = logging.getLogger(__name__)

# Thread-safe database access
db_lock = Lock()

def get_db_path() -> str:
    """Get the path to the archive database."""
    # Try to get from environment or use default
    chroma_path = os.getenv("CHROMA_DB_PATH")
    
    # If not set, use relative path from project root
    if not chroma_path:
        # Get project root (parent of app directory)
        # __file__ is app/services/archive.py, so:
        # os.path.dirname(__file__) = app/services
        # os.path.dirname(os.path.dirname(__file__)) = app
        # os.path.dirname(os.path.dirname(os.path.dirname(__file__))) = project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        base_dir = os.path.join(project_root, "data")
    else:
        # If chroma_path is set, use the same directory as chroma
        if chroma_path.endswith("/chroma") or chroma_path.endswith("chroma"):
            base_dir = os.path.dirname(chroma_path)
            if not base_dir or base_dir == "/":
                # Fallback to project root data directory
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                base_dir = os.path.join(project_root, "data")
        else:
            base_dir = chroma_path
    
    # Fallback to relative path if base_dir is empty or root
    if not base_dir or base_dir == "/":
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        base_dir = os.path.join(project_root, "data")
    
    db_path = os.path.join(base_dir, "archive.db")
    # Ensure directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return db_path

def init_database():
    """Initialize the SQLite database with required tables."""
    db_path = get_db_path()
    
    with db_lock:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()
        
        # Create index_jobs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS index_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                documents_indexed INTEGER NOT NULL
            )
        """)
        
        # Create scan_jobs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scan_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                total_documents INTEGER NOT NULL,
                bad_title_documents INTEGER NOT NULL
            )
        """)
        
        # Create title_renames table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS title_renames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                document_id INTEGER NOT NULL,
                old_title TEXT NOT NULL,
                new_title TEXT NOT NULL
            )
        """)
        
        # Create webhook_triggers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS webhook_triggers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                document_id INTEGER NOT NULL
            )
        """)
        
        # Create indexes for better query performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_index_jobs_timestamp ON index_jobs(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_jobs_timestamp ON scan_jobs(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_title_renames_timestamp ON title_renames(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_title_renames_document_id ON title_renames(document_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_triggers_timestamp ON webhook_triggers(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_triggers_document_id ON webhook_triggers(document_id)")
        
        conn.commit()
        conn.close()
        logger.info(f"Archive database initialized at {db_path}")

def archive_index_job(documents_indexed: int, timestamp: Optional[str] = None):
    """Archive a completed index job."""
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    
    db_path = get_db_path()
    
    with db_lock:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO index_jobs (timestamp, documents_indexed) VALUES (?, ?)",
            (timestamp, documents_indexed)
        )
        conn.commit()
        conn.close()

def archive_scan_job(total_documents: int, bad_title_documents: int, timestamp: Optional[str] = None):
    """Archive a completed scan job."""
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    
    db_path = get_db_path()
    
    with db_lock:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO scan_jobs (timestamp, total_documents, bad_title_documents) VALUES (?, ?, ?)",
            (timestamp, total_documents, bad_title_documents)
        )
        conn.commit()
        conn.close()

def archive_title_rename(document_id: int, old_title: str, new_title: str, timestamp: Optional[str] = None):
    """Archive a title rename action."""
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    
    db_path = get_db_path()
    
    with db_lock:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO title_renames (timestamp, document_id, old_title, new_title) VALUES (?, ?, ?, ?)",
            (timestamp, document_id, old_title, new_title)
        )
        conn.commit()
        conn.close()

def archive_webhook_trigger(document_id: int, timestamp: Optional[str] = None):
    """Archive a webhook trigger."""
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    
    db_path = get_db_path()
    
    with db_lock:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO webhook_triggers (timestamp, document_id) VALUES (?, ?)",
            (timestamp, document_id)
        )
        conn.commit()
        conn.close()

def query_archive(
    archive_type: str,
    page: int = 1,
    limit: int = 50,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Query the archive with pagination.
    
    Args:
        archive_type: One of 'index', 'scan', 'rename', 'webhook'
        page: Page number (1-indexed)
        limit: Number of results per page
        start_date: Optional start date filter (ISO format)
        end_date: Optional end date filter (ISO format)
    
    Returns:
        Dictionary with 'items', 'total', 'page', 'limit', 'has_more'
    """
    db_path = get_db_path()
    offset = (page - 1) * limit
    
    table_map = {
        'index': 'index_jobs',
        'scan': 'scan_jobs',
        'rename': 'title_renames',
        'webhook': 'webhook_triggers'
    }
    
    if archive_type not in table_map:
        raise ValueError(f"Invalid archive_type: {archive_type}. Must be one of: {', '.join(table_map.keys())}")
    
    table = table_map[archive_type]
    
    with db_lock:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        cursor = conn.cursor()
        
        # Build WHERE clause for date filtering
        where_clauses = []
        params = []
        
        if start_date:
            where_clauses.append("timestamp >= ?")
            params.append(start_date)
        
        if end_date:
            where_clauses.append("timestamp <= ?")
            params.append(end_date)
        
        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM {table} {where_sql}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]
        
        # Get paginated results
        query = f"SELECT * FROM {table} {where_sql} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params_with_pagination = params + [limit, offset]
        cursor.execute(query, params_with_pagination)
        
        rows = cursor.fetchall()
        items = [dict(row) for row in rows]
        
        conn.close()
    
    has_more = (page * limit) < total
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "has_more": has_more
    }

