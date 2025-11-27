#!/usr/bin/env python3
"""
Script to populate the archive database with fake data for screenshots.
This creates compelling, realistic data for all three tabs: Renaming, Jobs, and Issues.
"""

import sys
import os
from datetime import datetime, timezone, timedelta
import random

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.archive import (
    init_database,
    archive_index_job,
    archive_scan_job,
    archive_title_rename,
    archive_error,
    get_db_path
)

def generate_fake_rename_data():
    """Generate realistic rename entries."""
    rename_examples = [
        ("Scan 2024-01-15", "Invoice from Acme Corp - January 2024"),
        ("2024-03-22 Receipt", "Receipt - Coffee Shop Purchase - March 22, 2024"),
        ("Document 12345", "Employment Contract - John Doe"),
        ("Scan 2024-02-10", "Medical Bill - Dr. Smith - February 2024"),
        ("2024-01-05 Invoice", "Invoice #INV-2024-001 - Tech Solutions Inc"),
        ("Scan 2023-12-20", "Holiday Receipt - Electronics Store - December 2023"),
        ("Document 9876", "Rental Agreement - 123 Main Street"),
        ("2024-02-28 Statement", "Bank Statement - Checking Account - February 2024"),
        ("Scan 2024-03-05", "Insurance Claim - Auto Accident - March 2024"),
        ("2024-01-18 Receipt", "Receipt - Restaurant Dinner - January 18, 2024"),
        ("Document 5432", "Tax Document - W-2 Form - 2023"),
        ("Scan 2024-02-14", "Valentine's Day Receipt - Flower Shop"),
        ("2024-03-10 Invoice", "Invoice #INV-2024-045 - Consulting Services"),
        ("Scan 2024-01-30", "Utility Bill - Electricity - January 2024"),
        ("Document 7890", "Lease Agreement - Office Space - 2024"),
    ]
    
    # Generate timestamps spread over the last 30 days
    base_time = datetime.now(timezone.utc)
    
    for i, (old_title, new_title) in enumerate(rename_examples):
        # Spread entries over the last 30 days, most recent first
        days_ago = random.randint(0, 30)
        hours_ago = random.randint(0, 23)
        minutes_ago = random.randint(0, 59)
        timestamp = base_time - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)
        
        # Use realistic document IDs
        document_id = random.randint(1000, 9999)
        
        archive_title_rename(
            document_id=document_id,
            old_title=old_title,
            new_title=new_title,
            timestamp=timestamp.isoformat()
        )
        print(f"✓ Added rename: '{old_title}' → '{new_title}'")

def generate_fake_jobs():
    """Generate fake index and scan jobs."""
    base_time = datetime.now(timezone.utc)
    
    # Index jobs - mix of recent and older
    index_jobs = [
        (247, "completed", None, 0),  # Recent successful
        (189, "completed", None, 2),
        (312, "completed", None, 5),
        (156, "completed", None, 8),
        (423, "completed", None, 12),
        (98, "failed", "Connection timeout to vector database", 15),
    ]
    
    for documents_indexed, status, error, days_ago in index_jobs:
        timestamp = base_time - timedelta(days=days_ago, hours=random.randint(0, 23))
        archive_index_job(
            documents_indexed=documents_indexed,
            timestamp=timestamp.isoformat(),
            status=status,
            error=error
        )
        if status == "completed":
            print(f"✓ Added index job: Indexed {documents_indexed} documents ({days_ago} days ago)")
        else:
            print(f"✓ Added failed index job: {error}")
    
    # Scan jobs - mix of recent and older
    scan_jobs = [
        (1234, 23, "completed", None, 0),  # Recent
        (856, 12, "completed", None, 1),
        (2100, 45, "completed", None, 3),
        (567, 8, "completed", None, 6),
        (1890, 34, "completed", None, 9),
        (432, 5, "completed", None, 14),
        (1500, 28, "failed", "API rate limit exceeded", 18),
    ]
    
    for total_docs, bad_titles, status, error, days_ago in scan_jobs:
        timestamp = base_time - timedelta(days=days_ago, hours=random.randint(0, 23))
        archive_scan_job(
            total_documents=total_docs,
            bad_title_documents=bad_titles,
            timestamp=timestamp.isoformat(),
            status=status,
            error=error
        )
        if status == "completed":
            print(f"✓ Added scan job: Found {total_docs} documents, {bad_titles} bad titles ({days_ago} days ago)")
        else:
            print(f"✓ Added failed scan job: {error}")

def generate_fake_errors():
    """Generate fake error entries for the Issues tab."""
    base_time = datetime.now(timezone.utc)
    
    errors = [
        ("process", "Document 5432: Generation failed.\nLLM API returned empty response", "process-abc123", 5432, 0),
        ("process", "Document 7890: Vision model failed to generate title.\nImage processing timeout", "process-def456", 7890, 1),
        ("index", "Connection timeout to vector database after 30 seconds", "index", None, 2),
        ("scan", "API rate limit exceeded. Please try again later", "scan-xyz789", None, 3),
        ("process", "Document 1234: Could not find document 1234", "process-ghi789", 1234, 5),
        ("process", "Document 5678: Generation failed.\nInvalid API key", "process-jkl012", 5678, 7),
    ]
    
    for job_type, error_message, job_id, document_id, days_ago in errors:
        timestamp = base_time - timedelta(days=days_ago, hours=random.randint(0, 23))
        archive_error(
            job_type=job_type,
            error_message=error_message,
            job_id=job_id,
            document_id=document_id,
            timestamp=timestamp.isoformat()
        )
        print(f"✓ Added error: {job_type} - {error_message[:50]}...")

def main():
    """Main function to populate all fake data."""
    print("=" * 60)
    print("Populating fake data for screenshots...")
    print("=" * 60)
    print()
    
    # Initialize database (creates tables if they don't exist)
    print("Initializing database...")
    init_database()
    print(f"Database initialized at: {get_db_path()}")
    print()
    
    # Generate fake data for each tab
    print("Generating fake rename entries...")
    generate_fake_rename_data()
    print()
    
    print("Generating fake jobs (index and scan)...")
    generate_fake_jobs()
    print()
    
    print("Generating fake errors...")
    generate_fake_errors()
    print()
    
    print("=" * 60)
    print("✓ Fake data population complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Start the application: uvicorn app.main:app --reload")
    print("2. To simulate running progress, call the dev endpoint:")
    print("   curl -X POST http://localhost:8000/api/dev/fake-progress")
    print("   Or use the helper script: python scripts/create_fake_progress.py")
    print("3. Take screenshots of each tab with the compelling data!")

if __name__ == "__main__":
    main()

