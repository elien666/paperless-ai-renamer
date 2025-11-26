from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from threading import Lock
import uuid
from datetime import datetime
from typing import Dict, Any

# Global progress tracking
progress_lock = Lock()
# jobs structure: { job_id: { "status": "running"|"completed"|"failed", "total": 0, "processed": 0, "created_at": timestamp, "newer_than": str } }
jobs: Dict[str, Any] = {}

from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
import logging
from app.config import get_settings
from app.services.paperless import PaperlessClient
from app.services.ai import AIService

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

# Initialize Services (Lazy loading might be better, but global for simplicity here)
paperless_client = PaperlessClient()
ai_service = AIService()

def process_document(doc_id: int):
    """Core logic to process a single document."""
    logger.info(f"Processing document {doc_id}...")
    
    # 1. Fetch Document
    doc = paperless_client.get_document(doc_id)
    if not doc:
        logger.error(f"Could not find document {doc_id}")
        return

    content = doc.get("content", "")
    original_title = doc.get("title", "")
    
    logger.info(f"Document {doc_id}: '{original_title}'")
    
    if not content:
        logger.warning(f"Document {doc_id} '{original_title}' has no content. Skipping.")
        return

    # 2. Generate New Title
    new_title = ai_service.generate_title(content, original_title)
    
    # 3. Update Paperless
    if new_title is None:
        logger.error(f"Document {doc_id} '{original_title}': Generation failed.")
    elif new_title and new_title != original_title:
        if settings.DRY_RUN:
            logger.info(f"[DRY RUN] Would update document {doc_id} from '{original_title}' to '{new_title}'")
        else:
            paperless_client.update_document(doc_id, new_title)
            # 4. Index the document with the NEW title for future RAG
            ai_service.add_document_to_index(str(doc_id), content, new_title)
    elif new_title == original_title:
        logger.info(f"Document {doc_id} '{original_title}': LLM thinks title is good enough.")
    else:
        # Empty or whitespace-only response
        logger.warning(f"Document {doc_id} '{original_title}': LLM returned empty title.")

def scheduled_search_job(newer_than: str = None, job_id: str = None):
    """Periodic job to find and process documents with bad titles."""
    logger.info(f"Running search for documents... (newer_than={newer_than}, job_id={job_id})")
    
    try:
        # Fetch all documents (with optional date filter)
        # We can't use Paperless search with regex, so we fetch and filter locally
        all_docs = paperless_client.get_all_documents_filtered(newer_than=newer_than)
        logger.info(f"Fetched {len(all_docs)} documents from Paperless.")
        
        # Filter by BAD_TITLE_REGEX
        import re
        bad_title_pattern = re.compile(settings.BAD_TITLE_REGEX)
        matching_docs = [doc for doc in all_docs if bad_title_pattern.match(doc.get("title", ""))]
        
        logger.info(f"Found {len(matching_docs)} documents matching BAD_TITLE_REGEX: {settings.BAD_TITLE_REGEX}")

        # Initialize progress tracking for this job
        if job_id:
            with progress_lock:
                if job_id in jobs:
                    jobs[job_id]["total"] = len(matching_docs)
                    jobs[job_id]["processed"] = 0
        
        for doc in matching_docs:
            logger.info(f"Queuing document {doc['id']}: '{doc.get('title', 'N/A')}'")
            process_document(doc["id"])
            # Update processed count
            if job_id:
                with progress_lock:
                    if job_id in jobs:
                        jobs[job_id]["processed"] += 1
        
        # Mark job as completed
        if job_id:
            with progress_lock:
                if job_id in jobs:
                    jobs[job_id]["status"] = "completed"
                    
    except Exception as e:
        logger.error(f"Error in scheduled_search_job: {e}")
        if job_id:
            with progress_lock:
                if job_id in jobs:
                    jobs[job_id]["status"] = "failed"
                    jobs[job_id]["error"] = str(e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up Paperless AI Renamer...")
    
    # Initialize Scheduler
    scheduler = BackgroundScheduler()
    
    if settings.ENABLE_SCHEDULER:
        logger.info("Starting scheduler...")
        # Note: Scheduler jobs won't have a job_id unless we generate one here, 
        # but for now we keep it simple as the scheduler is for background automation.
        # If we want to track scheduled jobs, we'd need to wrap the job function.
        scheduler.add_job(scheduled_search_job, 'cron', minute=settings.CRON_SCHEDULE.split()[0].replace('*/', '')) 
        scheduler.start()
    else:
        logger.info("Scheduler is disabled. Use /scan to trigger manually.")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    if scheduler.running:
        scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post("/scan")
async def trigger_scan(background_tasks: BackgroundTasks, newer_than: str = None):
    """
    Manually trigger a scan for documents with bad titles.
    Optionally filter by date (YYYY-MM-DD) using 'newer_than'.
    Returns a job_id to track progress.
    """
    job_id = str(uuid.uuid4())
    
    with progress_lock:
        jobs[job_id] = {
            "status": "running",
            "total": 0,
            "processed": 0,
            "created_at": datetime.now().isoformat(),
            "newer_than": newer_than
        }
    
    background_tasks.add_task(scheduled_search_job, newer_than, job_id)
    return {"status": "scan_started", "job_id": job_id, "newer_than": newer_than}

@app.post("/index")
async def trigger_index(background_tasks: BackgroundTasks, older_than: str = None):
    """
    Manually trigger bulk indexing of existing documents.
    Optionally filter by date (YYYY-MM-DD) using 'older_than'.
    """
    background_tasks.add_task(run_bulk_index, older_than)
    return {"status": "indexing_started", "older_than": older_than}

@app.get("/find-outliers")
async def find_outliers(k_neighbors: int = 5, limit: int = 50):
    """
    Find documents that are outliers in the vector space.
    Returns documents sorted by their isolation score (distance to nearest neighbors).
    
    Args:
        k_neighbors: Number of neighbors to consider for outlier detection (default: 5)
        limit: Maximum number of outliers to return (default: 50)
    """
    try:
        outliers = ai_service.find_outlier_documents(k_neighbors=k_neighbors, limit=limit)
        return {
            "status": "success",
            "count": len(outliers),
            "outliers": outliers
        }
    except Exception as e:
        logger.error(f"Error finding outliers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process-documents")
async def process_documents(background_tasks: BackgroundTasks, request: Request):
    """
    Process a list of document IDs for renaming.
    Accepts JSON body: {"document_ids": [123, 456, 789]}
    """
    try:
        payload = await request.json()
        document_ids = payload.get("document_ids", [])
        
        if not document_ids:
            raise HTTPException(status_code=400, detail="No document_ids provided")
        
        # Queue each document for processing
        for doc_id in document_ids:
            background_tasks.add_task(process_document, doc_id)
        
        return {
            "status": "processing_started",
            "document_count": len(document_ids),
            "document_ids": document_ids
        }
    except Exception as e:
        logger.error(f"Error processing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

import re

def run_bulk_index(older_than: str = None):
    """Fetch all documents and index them if they have good titles."""
    logger.info(f"Starting bulk index... (older_than={older_than})")
    
    # 1. Fetch all documents
    all_docs = paperless_client.get_all_documents(older_than=older_than)
    logger.info(f"Fetched {len(all_docs)} documents from Paperless.")
    
    # 2. Filter and Index
    count = 0
    skipped_scan = 0
    cleaned = 0
    
    # Patterns for different date formats
    full_date_pattern = re.compile(r'^(\d{4})-(\d{2})-(\d{2})\s*')  # YYYY-MM-DD (with day)
    year_month_pattern = re.compile(r'^(\d{4})-(\d{2})\s+(.+)$')    # YYYY-MM (without day)
    year_only_pattern = re.compile(r'^(\d{4})\s+(.+)$')             # YYYY only
    
    for doc in all_docs:
        title = doc.get("title", "")
        content = doc.get("content", "")
        doc_id = doc.get("id")
        
        if not content or not title:
            continue
        
        # Skip documents starting with "Scan"
        if title.startswith("Scan"):
            skipped_scan += 1
            continue
        
        # Clean up titles with leading dates
        cleaned_title = title
        
        # Check for full date with day (YYYY-MM-DD) - remove entirely
        full_date_match = full_date_pattern.match(title)
        if full_date_match:
            cleaned_title = title[full_date_match.end():].strip()
            if cleaned_title:
                logger.info(f"Removed full date for doc {doc_id}: '{title}' -> '{cleaned_title}'")
                cleaned += 1
            else:
                cleaned_title = title  # Keep original if cleaning results in empty string
        else:
            # Check for year-month (YYYY-MM) - flip to MM-YYYY and move to end
            year_month_match = year_month_pattern.match(title)
            if year_month_match:
                year = year_month_match.group(1)
                month = year_month_match.group(2)
                rest = year_month_match.group(3)
                cleaned_title = f"{rest} {month}-{year}"
                logger.info(f"Moved year-month to end for doc {doc_id}: '{title}' -> '{cleaned_title}'")
                cleaned += 1
            else:
                # Check for year-only (YYYY) - move to end
                year_match = year_only_pattern.match(title)
                if year_match:
                    year = year_match.group(1)
                    rest = year_match.group(2)
                    cleaned_title = f"{rest} {year}"
                    logger.info(f"Moved year to end for doc {doc_id}: '{title}' -> '{cleaned_title}'")
                    cleaned += 1
        
        # Index the document with the cleaned title
        try:
            ai_service.add_document_to_index(str(doc_id), content, cleaned_title)
            count += 1
        except Exception as e:
            logger.error(f"Failed to index document {doc_id}: {e}")
    
    logger.info(f"Bulk index complete. Indexed {count} documents (skipped {skipped_scan} 'Scan' docs, cleaned {cleaned} date prefixes).")

@app.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle incoming webhooks from Paperless."""
    try:
        payload = await request.json()
        logger.info(f"Received webhook: {payload}")
        
        # Paperless webhook payload structure:
        # { "task_id": "...", "document_id": 123, ... }
        # Note: Check actual Paperless webhook docs. Usually it sends document_id.
        
        doc_id = payload.get("document_id")
        if doc_id:
            background_tasks.add_task(process_document, doc_id)
            return {"status": "processing_started", "document_id": doc_id}
        else:
            # It might be a different event type or payload
            logger.warning("Webhook payload missing document_id")
            return {"status": "ignored", "reason": "missing_document_id"}
            
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/progress")
def get_progress(job_id: str = None):
    """
    Get progress of scan jobs.
    If job_id is provided, returns details for that specific job.
    If no job_id is provided, returns a list of all jobs.
    """
    with progress_lock:
        if job_id:
            job = jobs.get(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            return job
        else:
            return {"jobs": jobs}
