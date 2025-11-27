from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from threading import Lock, Event as ThreadEvent
import uuid
import mimetypes
from datetime import datetime
from typing import Dict, Any, Optional
import asyncio
import time
import re

# Global progress tracking
progress_lock = Lock()
# jobs structure: { job_id: { "status": "running"|"completed"|"failed", "total": 0, "processed": 0, "created_at": timestamp, "newer_than": str, "last_reported": float } }
jobs: Dict[str, Any] = {}
# Progress events for long-polling: { job_id: (asyncio.Event, threading.Event) }
# We use both: threading.Event for thread-safe signaling, asyncio.Event for async waiting
progress_events: Dict[str, tuple] = {}
# Store reference to the main event loop for thread-safe callbacks
_main_event_loop: Optional[asyncio.AbstractEventLoop] = None

from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
import logging
from app.config import get_settings
from app.services.paperless import PaperlessClient
from app.services.ai import AIService
from app.services.archive import (
    init_database,
    archive_index_job,
    archive_scan_job,
    archive_title_rename,
    archive_webhook_trigger,
    archive_error,
    query_archive,
    clear_error_archive
)

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
logger.info(f"Configuration loaded - LLM_MODEL: {settings.LLM_MODEL}, VISION_MODEL: {settings.VISION_MODEL}, LANGUAGE: {settings.LANGUAGE}")

# Initialize Services (Lazy loading might be better, but global for simplicity here)
paperless_client = PaperlessClient()
ai_service = AIService()

def process_document(doc_id: int, job_id: str = None):
    """Core logic to process a single document."""
    logger.info(f"Processing document {doc_id}...")
    error_message = None
    
    try:
        # 1. Fetch Document
        doc = paperless_client.get_document(doc_id)
        if not doc:
            error_message = f"Could not find document {doc_id}"
            logger.error(error_message)
            if job_id:
                _update_document_job_error(job_id, doc_id, error_message)
            return

        content = doc.get("content", "")
        original_title = doc.get("title", "")
        
        # Try multiple possible field names for MIME type
        mime_type = (
            doc.get("original_mime_type") or 
            doc.get("mime_type") or 
            doc.get("media_type") or
            ""
        )
        
        # If not found in document response, try to get it from download headers
        if not mime_type:
            mime_type = paperless_client.get_document_mime_type(doc_id) or ""
        
        # If still not found, try to infer from original_filename extension
        if not mime_type:
            original_filename = doc.get("original_file_name", "") or doc.get("original_filename", "")
            if original_filename:
                guessed_type, _ = mimetypes.guess_type(original_filename)
                if guessed_type:
                    mime_type = guessed_type
                    logger.info(f"Inferred MIME type from filename for document {doc_id}: {mime_type}")
        
        logger.info(f"Document {doc_id}: '{original_title}' (MIME: {mime_type})")
        
        # Check if this is an image document
        if mime_type and mime_type.startswith("image/"):
            logger.info(f"Document {doc_id} '{original_title}': Image document detected, using vision model...")
            
            # Download original image
            original_image = paperless_client.get_document_original(doc_id)
            if not original_image:
                error_message = f"Document {doc_id} '{original_title}': Could not fetch original image."
                logger.error(error_message)
                if job_id:
                    _update_document_job_error(job_id, doc_id, error_message)
                return
            
            # Generate title from image
            try:
                new_title = ai_service.generate_title_from_image(original_image, original_title)
            except Exception as e:
                # Capture the full error chain from generate_title_from_image
                error_message = f"Document {doc_id} '{original_title}': Vision model failed to generate title.\n{str(e)}"
                logger.error(error_message)
                if job_id:
                    _update_document_job_error(job_id, doc_id, error_message)
                return
            
            if new_title is None:
                error_message = f"Document {doc_id} '{original_title}': Vision model failed to generate title."
                logger.error(error_message)
                if job_id:
                    _update_document_job_error(job_id, doc_id, error_message)
            elif new_title and new_title != original_title:
                if settings.DRY_RUN:
                    logger.info(f"[DRY RUN] Would update document {doc_id} from '{original_title}' to '{new_title}' (vision)")
                else:
                    paperless_client.update_document(doc_id, new_title)
                    # Archive the rename
                    archive_title_rename(doc_id, original_title, new_title)
                    # Index with vision-generated title
                    ai_service.add_document_to_index(str(doc_id), content, new_title)
            elif new_title == original_title:
                logger.info(f"Document {doc_id} '{original_title}': Vision model thinks title is good enough.")
            else:
                logger.warning(f"Document {doc_id} '{original_title}': Vision model returned empty title.")
            return
        
        # For non-image documents, use text-based generation
        if not content:
            logger.warning(f"Document {doc_id} '{original_title}' has no content. Skipping.")
            return

        # 2. Generate New Title
        try:
            new_title = ai_service.generate_title(content, original_title)
        except Exception as e:
            # Capture the full error chain from generate_title
            error_message = f"Document {doc_id} '{original_title}': Generation failed.\n{str(e)}"
            logger.error(error_message)
            if job_id:
                _update_document_job_error(job_id, doc_id, error_message)
            return
        
        # 3. Update Paperless
        if new_title is None:
            error_message = f"Document {doc_id} '{original_title}': Generation failed."
            logger.error(error_message)
            if job_id:
                _update_document_job_error(job_id, doc_id, error_message)
        elif new_title and new_title != original_title:
            if settings.DRY_RUN:
                logger.info(f"[DRY RUN] Would update document {doc_id} from '{original_title}' to '{new_title}'")
            else:
                paperless_client.update_document(doc_id, new_title)
                # Archive the rename
                archive_title_rename(doc_id, original_title, new_title)
                # 4. Index the document with the NEW title for future RAG
                ai_service.add_document_to_index(str(doc_id), content, new_title)
        elif new_title == original_title:
            logger.info(f"Document {doc_id} '{original_title}': LLM thinks title is good enough.")
        else:
            # Empty or whitespace-only response
            logger.warning(f"Document {doc_id} '{original_title}': LLM returned empty title.")
    except Exception as e:
        error_message = f"Document {doc_id}: {str(e)}"
        logger.error(error_message, exc_info=True)
        if job_id:
            _update_document_job_error(job_id, doc_id, error_message)

def _update_document_job_error(job_id: str, doc_id: int, error_message: str):
    """Update a document processing job with an error for a specific document."""
    # Archive the error
    if job_id.startswith("webhook-"):
        job_type = "webhook"
    elif job_id.startswith("process-"):
        job_type = "process"
    elif job_id.startswith("scan") or job_id == "scan":
        job_type = "scan"
    else:
        job_type = "index"
    archive_error(job_type=job_type, error_message=error_message, job_id=job_id, document_id=doc_id)
    
    with progress_lock:
        if job_id in jobs:
            if "errors" not in jobs[job_id]:
                jobs[job_id]["errors"] = []
            jobs[job_id]["errors"].append({
                "document_id": doc_id,
                "error": error_message
            })
            jobs[job_id]["processed"] = jobs[job_id].get("processed", 0) + 1
            _signal_progress_update(job_id)

def _signal_progress_update(job_id: str):
    """Signal that progress has been updated for a job (thread-safe)."""
    global _main_event_loop
    
    if job_id in progress_events:
        thread_event, async_event = progress_events[job_id]
        # Set the thread event (thread-safe)
        thread_event.set()
        # Signal the async event from the main event loop
        if _main_event_loop is not None and _main_event_loop.is_running():
            _main_event_loop.call_soon_threadsafe(async_event.set)
    
    # Also signal the global "all jobs" event for long polling without job_id
    # This allows clients waiting for any job update to be notified
    global_event_key = "__all_jobs__"
    if global_event_key in progress_events:
        thread_event, async_event = progress_events[global_event_key]
        thread_event.set()
        if _main_event_loop is not None and _main_event_loop.is_running():
            _main_event_loop.call_soon_threadsafe(async_event.set)

def _signal_all_jobs_update():
    """Signal that any job has been created or updated (for long polling without job_id)."""
    _signal_progress_update("__all_jobs__")

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
                    jobs[job_id]["last_reported"] = time.time()
        
        for doc in matching_docs:
            logger.info(f"Queuing document {doc['id']}: '{doc.get('title', 'N/A')}'")
            process_document(doc["id"], job_id)
            # Update processed count with throttling
            if job_id:
                current_time = time.time()
                with progress_lock:
                    if job_id in jobs:
                        jobs[job_id]["processed"] += 1
                        # Only signal if at least 1 second has passed since last report
                        if current_time - jobs[job_id].get("last_reported", 0) >= 1.0:
                            jobs[job_id]["last_reported"] = current_time
                            _signal_progress_update(job_id)
        
        # Mark job as completed
        if job_id:
            with progress_lock:
                if job_id in jobs:
                    jobs[job_id]["status"] = "completed"
                    jobs[job_id]["completed_at"] = datetime.now().isoformat()
                    # Archive the scan job
                    archive_scan_job(
                        total_documents=len(all_docs),
                        bad_title_documents=len(matching_docs),
                        timestamp=jobs[job_id]["completed_at"],
                        status="completed"
                    )
                    # Final signal
                    _signal_progress_update(job_id)
                    
    except Exception as e:
        logger.error(f"Error in scheduled_search_job: {e}")
        if job_id:
            error_message = str(e)
            # Archive the error
            archive_error(job_type="scan", error_message=error_message, job_id=job_id)
            with progress_lock:
                if job_id in jobs:
                    jobs[job_id]["status"] = "failed"
                    jobs[job_id]["error"] = error_message
                    jobs[job_id]["completed_at"] = datetime.now().isoformat()
                    # Archive the failed scan job
                    archive_scan_job(
                        total_documents=len(all_docs) if 'all_docs' in locals() else 0,
                        bad_title_documents=len(matching_docs) if 'matching_docs' in locals() else 0,
                        timestamp=jobs[job_id]["completed_at"],
                        status="failed",
                        error=error_message
                    )
                    _signal_progress_update(job_id)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up Paperless AI Renamer...")
    
    # Store reference to the main event loop for thread-safe callbacks
    global _main_event_loop
    _main_event_loop = asyncio.get_event_loop()
    
    # Initialize archive database
    init_database()
    
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
    _main_event_loop = None

app = FastAPI(lifespan=lifespan)

# Mount API routes under /api prefix
from fastapi.routing import APIRouter
api_router = APIRouter()

@api_router.post("/scan")
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
            "newer_than": newer_than,
            "last_reported": time.time()
        }
        # Create events for long-polling (thread-safe + async)
        thread_event = ThreadEvent()
        async_event = asyncio.Event()
        progress_events[job_id] = (thread_event, async_event)
    
    background_tasks.add_task(scheduled_search_job, newer_than, job_id)
    
    # Signal global event for long polling without job_id (after job is created)
    _signal_all_jobs_update()
    return {"status": "scan_started", "job_id": job_id, "newer_than": newer_than}

@api_router.post("/index")
async def trigger_index(background_tasks: BackgroundTasks, older_than: str = None):
    """
    Manually trigger bulk indexing of existing documents.
    Optionally filter by date (YYYY-MM-DD) using 'older_than'.
    Returns a job_id to track progress. Only one index job can run at a time.
    """
    job_id = "index"
    
    # Check if index job is already running
    with progress_lock:
        existing_job = jobs.get(job_id)
        if existing_job and existing_job.get("status") == "running":
            raise HTTPException(
                status_code=409,
                detail="Index job is already running. Please wait for it to complete or check /progress endpoint."
            )
        
        # Create or update job entry
        jobs[job_id] = {
            "status": "running",
            "total": 0,
            "processed": 0,
            "created_at": datetime.now().isoformat(),
            "older_than": older_than,
            "last_reported": time.time()
        }
        # Create events for long-polling (thread-safe + async)
        thread_event = ThreadEvent()
        async_event = asyncio.Event()
        progress_events[job_id] = (thread_event, async_event)
    
    background_tasks.add_task(run_bulk_index, older_than, job_id)
    
    # Signal global event for long polling without job_id (after job is created)
    _signal_all_jobs_update()
    return {"status": "indexing_started", "job_id": job_id, "older_than": older_than}

@api_router.get("/find-outliers")
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

def process_documents_batch(document_ids: list, job_id: str):
    """Process a batch of documents and track progress/errors."""
    try:
        with progress_lock:
            if job_id in jobs:
                jobs[job_id]["total"] = len(document_ids)
                jobs[job_id]["processed"] = 0
                jobs[job_id]["errors"] = []
                jobs[job_id]["last_reported"] = time.time()
        
        for doc_id in document_ids:
            process_document(doc_id, job_id)
            # Update processed count with throttling
            current_time = time.time()
            with progress_lock:
                if job_id in jobs:
                    # Only signal if at least 1 second has passed since last report
                    if current_time - jobs[job_id].get("last_reported", 0) >= 1.0:
                        jobs[job_id]["last_reported"] = current_time
                        _signal_progress_update(job_id)
        
        # Mark job as completed
        with progress_lock:
            if job_id in jobs:
                jobs[job_id]["status"] = "completed"
                jobs[job_id]["completed_at"] = datetime.now().isoformat()
                _signal_progress_update(job_id)
                _signal_all_jobs_update()
    except Exception as e:
        logger.error(f"Error in process_documents_batch: {e}")
        error_message = str(e)
        # Archive the error
        archive_error(job_type="process", error_message=error_message, job_id=job_id)
        with progress_lock:
            if job_id in jobs:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["error"] = error_message
                jobs[job_id]["completed_at"] = datetime.now().isoformat()
                _signal_progress_update(job_id)
                _signal_all_jobs_update()

@api_router.post("/process-documents")
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
        
        # Create a job to track this batch of documents
        job_id = f"process-{uuid.uuid4()}"
        
        with progress_lock:
            jobs[job_id] = {
                "status": "running",
                "total": len(document_ids),
                "processed": 0,
                "created_at": datetime.now().isoformat(),
                "errors": [],
                "last_reported": time.time()
            }
            # Create events for long-polling
            thread_event = ThreadEvent()
            async_event = asyncio.Event()
            progress_events[job_id] = (thread_event, async_event)
        
        # Process documents in background
        background_tasks.add_task(process_documents_batch, document_ids, job_id)
        
        # Signal global event for long polling
        _signal_all_jobs_update()
        
        return {
            "status": "processing_started",
            "document_count": len(document_ids),
            "document_ids": document_ids,
            "job_id": job_id
        }
    except Exception as e:
        logger.error(f"Error processing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

import re

def run_bulk_index(older_than: str = None, job_id: str = None):
    """Fetch all documents and index them if they have good titles."""
    logger.info(f"Starting bulk index... (older_than={older_than}, job_id={job_id})")
    
    try:
        # 1. Fetch all documents
        all_docs = paperless_client.get_all_documents(older_than=older_than)
        logger.info(f"Fetched {len(all_docs)} documents from Paperless.")
        
        # Initialize progress tracking for this job
        if job_id:
            with progress_lock:
                if job_id in jobs:
                    jobs[job_id]["total"] = len(all_docs)
                    jobs[job_id]["processed"] = 0
                    jobs[job_id]["last_reported"] = time.time()
        
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
            
            # Update processed count with throttling (even if we skip this document)
            if job_id:
                current_time = time.time()
                with progress_lock:
                    if job_id in jobs:
                        jobs[job_id]["processed"] += 1
                        # Only signal if at least 1 second has passed since last report
                        if current_time - jobs[job_id].get("last_reported", 0) >= 1.0:
                            jobs[job_id]["last_reported"] = current_time
                            _signal_progress_update(job_id)
            
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
        
        # Mark job as completed and store results
        if job_id:
            with progress_lock:
                if job_id in jobs:
                    jobs[job_id]["status"] = "completed"
                    jobs[job_id]["indexed"] = count
                    jobs[job_id]["skipped_scan"] = skipped_scan
                    jobs[job_id]["cleaned"] = cleaned
                    jobs[job_id]["completed_at"] = datetime.now().isoformat()
                    # Archive the index job
                    archive_index_job(
                        documents_indexed=count,
                        timestamp=jobs[job_id]["completed_at"],
                        status="completed"
                    )
                    # Final signal
                    _signal_progress_update(job_id)
                    
    except Exception as e:
        logger.error(f"Error in run_bulk_index: {e}")
        if job_id:
            error_message = str(e)
            with progress_lock:
                if job_id in jobs:
                    jobs[job_id]["status"] = "failed"
                    jobs[job_id]["error"] = error_message
                    jobs[job_id]["completed_at"] = datetime.now().isoformat()
                    # Archive the failed index job
                    archive_index_job(
                        documents_indexed=count if 'count' in locals() else 0,
                        timestamp=jobs[job_id]["completed_at"],
                        status="failed",
                        error=error_message
                    )
                    _signal_progress_update(job_id)

def process_document_with_progress(doc_id: int, job_id: str):
    """Process a single document with progress tracking."""
    try:
        with progress_lock:
            if job_id in jobs:
                jobs[job_id]["total"] = 1
                jobs[job_id]["processed"] = 0
                jobs[job_id]["errors"] = []
                jobs[job_id]["last_reported"] = time.time()
        
        # Process the document
        process_document(doc_id, job_id)
        
        # Update processed count if not already updated by error handler
        current_time = time.time()
        with progress_lock:
            if job_id in jobs:
                # Only update if not already processed (error handler may have already incremented it)
                if jobs[job_id]["processed"] == 0:
                    jobs[job_id]["processed"] = 1
                    jobs[job_id]["last_reported"] = current_time
                    _signal_progress_update(job_id)
        
        # Mark job as completed
        with progress_lock:
            if job_id in jobs:
                jobs[job_id]["status"] = "completed"
                jobs[job_id]["completed_at"] = datetime.now().isoformat()
                _signal_progress_update(job_id)
                _signal_all_jobs_update()
    except Exception as e:
        logger.error(f"Error in process_document_with_progress: {e}")
        error_message = str(e)
        # Archive the error (job_type will be determined from job_id prefix by archive_error if needed)
        archive_error(job_type="process", error_message=error_message, job_id=job_id, document_id=doc_id)
        with progress_lock:
            if job_id in jobs:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["error"] = error_message
                jobs[job_id]["completed_at"] = datetime.now().isoformat()
                # Ensure processed is set if not already set by process_document error handler
                if jobs[job_id]["processed"] == 0:
                    jobs[job_id]["processed"] = 1
                _signal_progress_update(job_id)
                _signal_all_jobs_update()

@api_router.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle incoming webhooks from Paperless."""
    try:
        payload = await request.json()
        logger.info(f"Received webhook: {payload}")
        
        # Paperless webhook payload structure:
        # Paperless may send either:
        # 1. Direct document_id: { "document_id": 123, ... }
        # 2. Document URL: { "url": "https://paperless.tty7.de/documents/1602/", ... }
        #    or the payload itself might be a URL string
        
        doc_id = None
        
        # First, try to get document_id directly (for backward compatibility)
        if isinstance(payload, dict):
            doc_id = payload.get("document_id")
        
        # If not found, try to extract from URL
        if not doc_id:
            url = None
            if isinstance(payload, str):
                # Payload is a URL string directly
                url = payload
            elif isinstance(payload, dict):
                # Try common URL field names
                url = payload.get("url") or payload.get("document_url") or payload.get("link")
            
            if url:
                # Extract document ID from URL pattern: https://paperless.tty7.de/documents/1602/
                match = re.search(r'/documents/(\d+)/?', url)
                if match:
                    doc_id = int(match.group(1))
                    logger.info(f"Extracted document_id {doc_id} from URL: {url}")
                else:
                    logger.warning(f"Could not extract document_id from URL: {url}")
        
        if doc_id:
            # Archive the webhook trigger
            archive_webhook_trigger(doc_id)
            
            # Create a job to track this webhook-triggered document processing
            # Use 'process-' prefix so frontend recognizes it as a Process job
            job_id = f"process-{uuid.uuid4()}"
            
            with progress_lock:
                jobs[job_id] = {
                    "status": "running",
                    "total": 1,
                    "processed": 0,
                    "created_at": datetime.now().isoformat(),
                    "document_id": doc_id,
                    "errors": [],
                    "last_reported": time.time()
                }
                # Create events for long-polling
                thread_event = ThreadEvent()
                async_event = asyncio.Event()
                progress_events[job_id] = (thread_event, async_event)
            
            # Process document in background with progress tracking
            background_tasks.add_task(process_document_with_progress, doc_id, job_id)
            
            # Signal global event for long polling
            _signal_all_jobs_update()
            
            return {"status": "processing_started", "document_id": doc_id, "job_id": job_id}
        else:
            # It might be a different event type or payload
            logger.warning(f"Webhook payload missing document_id or valid URL. Payload: {payload}")
            return {"status": "ignored", "reason": "missing_document_id"}
            
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/health")
def health_check():
    return {"status": "ok"}

@api_router.get("/progress")
async def get_progress(
    job_id: Optional[str] = None,
    wait: bool = False,
    timeout: int = 60
):
    """
    Get progress of scan and index jobs.
    If job_id is provided, returns details for that specific job (use 'index' for index job).
    If no job_id is provided, returns all jobs including the index job (if exists).
    
    Args:
        job_id: Optional job ID to query
        wait: If True, wait for progress updates (long-polling). Default: False
        timeout: Maximum time to wait in seconds when wait=True. Default: 60
    """
    if not wait:
        # Regular polling mode - immediate response
        with progress_lock:
            if job_id:
                job = jobs.get(job_id)
                if not job:
                    raise HTTPException(status_code=404, detail="Job not found")
                return job
            else:
                # Return all jobs, including index job if it exists
                return {"jobs": jobs}
    else:
        # Long-polling mode - wait for updates
        if job_id:
            # Long poll specific job
            # Get initial state
            with progress_lock:
                job = jobs.get(job_id)
                if not job:
                    raise HTTPException(status_code=404, detail="Job not found")
                
                # If job is already completed or failed, return immediately
                if job.get("status") in ("completed", "failed"):
                    return job
                
                # Get the event for this job, create if it doesn't exist
                if job_id not in progress_events:
                    thread_event = ThreadEvent()
                    async_event = asyncio.Event()
                    progress_events[job_id] = (thread_event, async_event)
                
                thread_event, async_event = progress_events[job_id]
                initial_processed = job.get("processed", 0)
            
            # Wait for progress update or timeout
            try:
                await asyncio.wait_for(async_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                # Timeout reached, return current state
                pass
            
            # Clear the events for next wait cycle
            async_event.clear()
            thread_event.clear()
            
            # Return current state
            with progress_lock:
                job = jobs.get(job_id)
                if not job:
                    raise HTTPException(status_code=404, detail="Job not found")
                return job
        else:
            # Long poll all jobs - wait for any job to start or update
            # Create a global event that gets signaled when any job updates
            global_event_key = "__all_jobs__"
            
            with progress_lock:
                # Check if there are any running jobs
                has_running = any(j.get("status") == "running" for j in jobs.values())
                
                # If no running jobs, wait for a new job to start
                # We'll create a global event that gets signaled when any job is created/updated
                if global_event_key not in progress_events:
                    thread_event = ThreadEvent()
                    async_event = asyncio.Event()
                    progress_events[global_event_key] = (thread_event, async_event)
                
                thread_event, async_event = progress_events[global_event_key]
                initial_jobs_count = len(jobs)
            
            # Wait for any job update or timeout
            try:
                await asyncio.wait_for(async_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                # Timeout reached, return current state
                pass
            
            # Clear the event for next wait cycle
            async_event.clear()
            thread_event.clear()
            
            # Return all jobs
            with progress_lock:
                return {"jobs": jobs}

@api_router.get("/archive")
async def get_archive(
    type: str,
    page: int = 1,
    limit: int = 50,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Query the job archive with pagination.
    
    Args:
        type: Archive type - one of 'index', 'scan', 'rename', 'webhook'
        page: Page number (1-indexed). Default: 1
        limit: Number of results per page. Default: 50
        start_date: Optional start date filter (ISO format)
        end_date: Optional end date filter (ISO format)
    """
    try:
        result = query_archive(
            archive_type=type,
            page=page,
            limit=limit,
            start_date=start_date,
            end_date=end_date
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying archive: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/archive")
async def delete_archive(type: str):
    """
    Clear an archive type. Currently only supports clearing the error archive.
    
    Args:
        type: Archive type - must be 'error' to clear the error archive
    """
    if type != 'error':
        raise HTTPException(
            status_code=400,
            detail=f"Only 'error' archive type can be cleared. Received: {type}"
        )
    
    try:
        deleted_count = clear_error_archive()
        return {"status": "success", "deleted_count": deleted_count}
    except Exception as e:
        logger.error(f"Error clearing error archive: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Mount API router with /api prefix
app.include_router(api_router, prefix="/api")

# Serve static files from frontend build
# Note: This must be registered AFTER all API routes
frontend_dist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(frontend_dist_path):
    # Mount static assets (JS, CSS, etc.)
    assets_path = os.path.join(frontend_dist_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
    
    # Serve other static files (favicon, etc.)
    static_path = os.path.join(frontend_dist_path)
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    
    # Serve index.html for SPA routing (catch-all, must be last)
    # FastAPI will match API routes first, so this only catches unmatched routes
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Skip known API/documentation paths
        if full_path in ["docs", "redoc", "openapi.json"]:
            raise HTTPException(status_code=404, detail="Not found")
        
        # Check if it's a static file request
        if "." in full_path.split("/")[-1] and not full_path.startswith("assets/"):
            file_path = os.path.join(frontend_dist_path, full_path)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                return FileResponse(file_path)
        
        # Serve index.html for SPA routing
        index_path = os.path.join(frontend_dist_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="Frontend not found")
else:
    logger.warning(f"Frontend build not found at {frontend_dist_path}. Static file serving disabled.")
