"""Database helper for persistent storage using SQLite."""

import os
import sqlite3
from datetime import datetime
from contextlib import contextmanager


class DatabaseManager:
    """Manage SQLite database for file processing history."""
    
    def __init__(self, db_path=None):
        if db_path is None:
            app_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            db_path = os.path.join(app_dir, 'keong_mas.db')
        
        self.db_path = db_path
        self._init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_database(self):
        """Initialize database tables."""
        with self.get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS processing_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    output_location TEXT
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS processed_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    file_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size INTEGER,
                    status TEXT NOT NULL,
                    output_path TEXT,
                    error_message TEXT,
                    processed_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES processing_sessions(id)
                )
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_session_id 
                ON processed_files(session_id)
            ''')
    
    def create_session(self, output_location=None):
        """Create a new processing session."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                'INSERT INTO processing_sessions (created_at, output_location) VALUES (?, ?)',
                (datetime.now().isoformat(), output_location)
            )
            return cursor.lastrowid
    
    def add_file(self, session_id, file_path, file_size):
        """Add a file to the session."""
        file_name = os.path.basename(file_path)
        with self.get_connection() as conn:
            cursor = conn.execute(
                '''INSERT INTO processed_files 
                   (session_id, file_path, file_name, file_size, status) 
                   VALUES (?, ?, ?, ?, ?)''',
                (session_id, file_path, file_name, file_size, 'pending')
            )
            return cursor.lastrowid
    
    def update_file_status(self, file_id, status, output_path=None, error_message=None):
        """Update file processing status."""
        with self.get_connection() as conn:
            conn.execute(
                '''UPDATE processed_files 
                   SET status = ?, output_path = ?, error_message = ?, processed_at = ?
                   WHERE id = ?''',
                (status, output_path, error_message, datetime.now().isoformat(), file_id)
            )
    
    def get_session_files(self, session_id):
        """Get all files in a session."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                'SELECT * FROM processed_files WHERE session_id = ? ORDER BY id',
                (session_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def clear_old_sessions(self, days=30):
        """Clear sessions older than specified days."""
        with self.get_connection() as conn:
            cutoff_date = datetime.now().replace(day=datetime.now().day - days)
            conn.execute(
                'DELETE FROM processing_sessions WHERE created_at < ?',
                (cutoff_date.isoformat(),)
            )
