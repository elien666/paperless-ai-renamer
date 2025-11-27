#!/usr/bin/env python3
"""
Script to clear all data from the archive database.
"""

import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.archive import get_db_path
import sqlite3

def clear_database():
    """Clear all data from archive database tables."""
    db_path = get_db_path()
    
    print(f"Clearing database at: {db_path}")
    
    if not os.path.exists(db_path):
        print("Database does not exist. Nothing to clear.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Clear all tables
    tables = ['index_jobs', 'scan_jobs', 'title_renames', 'webhook_triggers', 'error_archive']
    
    for table in tables:
        cursor.execute(f"DELETE FROM {table}")
        count = cursor.rowcount
        print(f"  Cleared {count} rows from {table}")
    
    conn.commit()
    conn.close()
    
    print("✓ Database cleared successfully!")

if __name__ == "__main__":
    clear_database()

