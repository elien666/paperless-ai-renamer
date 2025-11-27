import { useEffect, useState, useRef } from 'react';
import type { ProgressResponse } from '../services/api';
import { useProgress } from '../contexts/ProgressContext';
import { GiMusicalNotes } from 'react-icons/gi';
import { ImSpinner2 } from 'react-icons/im';
import { FaExclamationCircle } from 'react-icons/fa';

const MIN_DISPLAY_TIME = 1500; // 1.5 seconds

export default function ActivityBar() {
  const { progress, loading, subscribe } = useProgress();
  const [displayedProgress, setDisplayedProgress] = useState<Record<string, ProgressResponse>>({});
  const [toastMessage, setToastMessage] = useState<{ type: 'error'; text: string } | null>(null);
  const lastUpdateTimeRef = useRef<number>(0);
  const updateTimerRef = useRef<number | null>(null);

  useEffect(() => {
    // Subscribe to progress updates to detect job failures and document errors
    const unsubscribe = subscribe((currentProgress: Record<string, ProgressResponse>, previousProgress: Record<string, ProgressResponse>) => {
      // Check for jobs that just failed or have new document errors
      Object.entries(currentProgress).forEach(([jobId, job]) => {
        const previousJob = previousProgress[jobId];
        
        // If job status changed from 'running' to 'failed', show toast
        if (previousJob?.status === 'running' && job.status === 'failed') {
          const jobType = getJobType(jobId);
          const errorMessage = job.error || 'Unknown error';
          setToastMessage({
            type: 'error',
            text: `${jobType} job failed: ${errorMessage}`
          });
          // Clear toast after 5 seconds
          setTimeout(() => setToastMessage(null), 5000);
        }
        
        // If job has new document errors, show toast
        if (job.status === 'running' && job.errors && job.errors.length > 0) {
          const previousErrorCount = previousJob?.errors?.length || 0;
          if (job.errors.length > previousErrorCount) {
            const newErrors = job.errors.slice(previousErrorCount);
            const latestError = newErrors[newErrors.length - 1];
            const jobType = getJobType(jobId);
            setToastMessage({
              type: 'error',
              text: `${jobType} job: Document ${latestError.document_id} failed - ${latestError.error}`
            });
            // Clear toast after 5 seconds
            setTimeout(() => setToastMessage(null), 5000);
          }
        }
      });
    });

    return unsubscribe;
  }, [subscribe]);

  // Debounce progress updates to show state changes for at least 1.5s
  useEffect(() => {
    // If displayedProgress is empty (initial load), update immediately
    if (Object.keys(displayedProgress).length === 0 && Object.keys(progress).length > 0) {
      setDisplayedProgress(progress);
      lastUpdateTimeRef.current = Date.now();
      return;
    }

    const now = Date.now();
    const timeSinceLastUpdate = now - lastUpdateTimeRef.current;

    // Clear any pending update
    if (updateTimerRef.current !== null) {
      clearTimeout(updateTimerRef.current);
    }

    if (timeSinceLastUpdate >= MIN_DISPLAY_TIME) {
      // Enough time has passed, update immediately
      setDisplayedProgress(progress);
      lastUpdateTimeRef.current = now;
    } else {
      // Schedule update after remaining time
      const remainingTime = MIN_DISPLAY_TIME - timeSinceLastUpdate;
      updateTimerRef.current = window.setTimeout(() => {
        setDisplayedProgress(progress);
        lastUpdateTimeRef.current = Date.now();
      }, remainingTime);
    }

    return () => {
      if (updateTimerRef.current !== null) {
        clearTimeout(updateTimerRef.current);
      }
    };
  }, [progress, displayedProgress]);

  const getJobType = (jobId: string) => {
    if (jobId === 'index') return 'Index';
    if (jobId.startsWith('process-')) return 'Process';
    return 'Scan';
  };

  const jobs = Object.entries(displayedProgress);
  const activeJobs = jobs.filter(([_, job]) => job.status === 'running');
  const failedJobs = jobs.filter(([_, job]) => job.status === 'failed');

  if (loading) {
    return (
      <div className="flex items-center gap-2">
        <span className="loading loading-spinner loading-sm"></span>
      </div>
    );
  }

  return (
    <>
      <div className="flex items-center gap-2">
        {activeJobs.length === 0 && failedJobs.length === 0 ? (
          <div className="flex items-center gap-2 text-base-content/70">
            <span className="text-sm">Idle</span>
            <GiMusicalNotes className="w-5 h-5" />
          </div>
        ) : (
          <>
            {activeJobs.map(([jobId, job]) => {
              const jobType = getJobType(jobId);
              const hasDocumentErrors = job.errors && job.errors.length > 0;
              
              return (
                <div key={jobId} className="flex items-center gap-2 px-2 py-1 bg-base-200 rounded-full border border-base-300" title={hasDocumentErrors ? `${job.errors?.length || 0} document error(s)` : undefined}>
                  <span className="font-medium text-xs">{jobType}</span>
                  <ImSpinner2 className="w-5 h-5 animate-spin text-primary" />
                  {job.total !== undefined && (
                    <>
                      <span className="text-xs text-base-content/70">
                        {job.processed || 0}/{job.total}
                      </span>
                      <progress
                        className="progress progress-primary w-12 h-1"
                        value={job.processed || 0}
                        max={job.total}
                      ></progress>
                    </>
                  )}
                  {hasDocumentErrors && job.errors && (
                    <span className="text-xs text-error" title={job.errors.map((e: any) => `Doc ${e.document_id}: ${e.error}`).join('\n')}>
                      {job.errors.length} error{job.errors.length !== 1 ? 's' : ''}
                    </span>
                  )}
                </div>
              );
            })}
            {failedJobs.map(([jobId, job]) => {
              const jobType = getJobType(jobId);
              const errorMessage = job.error || 'Unknown error';
              
              return (
                <div key={jobId} className="flex items-center gap-2 px-2 py-1 bg-error/20 rounded-full border border-error/50" title={errorMessage}>
                  <span className="font-medium text-xs text-error">{jobType}</span>
                  <FaExclamationCircle className="w-4 h-4 text-error" />
                  <span className="text-xs text-error/80">Failed</span>
                </div>
              );
            })}
          </>
        )}
      </div>
      
      {/* Toast Messages */}
      {toastMessage && (
        <div className="toast toast-center toast-top z-50">
          <div className="alert alert-error">
            <span>{toastMessage.text}</span>
          </div>
        </div>
      )}
    </>
  );
}

