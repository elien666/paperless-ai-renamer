import { useEffect, useState, useRef } from 'react';
import { apiService } from '../services/api';
import type { ProgressResponse } from '../services/api';
import { GiMusicalNotes } from 'react-icons/gi';
import { ImSpinner2 } from 'react-icons/im';

const MIN_DISPLAY_TIME = 1500; // 1.5 seconds

export default function ActivityBar() {
  const [progress, setProgress] = useState<Record<string, ProgressResponse>>({});
  const [displayedProgress, setDisplayedProgress] = useState<Record<string, ProgressResponse>>({});
  const [loading, setLoading] = useState(true);
  const lastUpdateTimeRef = useRef<number>(0);
  const updateTimerRef = useRef<number | null>(null);

  useEffect(() => {
    let isMounted = true;

    // First, get current state immediately (no waiting)
    const fetchInitialState = async () => {
      try {
        const data = await apiService.getProgress(undefined, false);
        if (isMounted) {
          if (data.jobs) {
            setProgress(data.jobs);
          } else {
            setProgress({ [data.status || 'unknown']: data });
          }
          setLoading(false);
          // Now start long polling for updates
          fetchAllJobsWithLongPolling();
        }
      } catch (err: any) {
        if (isMounted) {
          setLoading(false);
          // Retry after delay
          setTimeout(() => {
            if (isMounted) {
              fetchInitialState();
            }
          }, 2000);
        }
      }
    };

    const fetchAllJobsWithLongPolling = async () => {
      try {
        const data = await apiService.getProgress(undefined, true, 30);
        
        if (isMounted) {
          if (data.jobs) {
            setProgress(data.jobs);
          } else {
            setProgress({ [data.status || 'unknown']: data });
          }
          // Continue long polling
          fetchAllJobsWithLongPolling();
        }
      } catch (err: any) {
        if (isMounted) {
          if (err.code === 'ECONNABORTED' || err.message?.includes('timeout') || err.response?.status === 408) {
            // Timeout is expected - get current state and continue
            try {
              const data = await apiService.getProgress(undefined, false);
              if (isMounted) {
                if (data.jobs) {
                  setProgress(data.jobs);
                } else {
                  setProgress({ [data.status || 'unknown']: data });
                }
                fetchAllJobsWithLongPolling();
              }
            } catch (refreshErr: any) {
              if (isMounted) {
                setTimeout(() => {
                  fetchAllJobsWithLongPolling();
                }, 2000);
              }
            }
          } else {
            // Other errors - retry after delay
            setTimeout(() => {
              if (isMounted) {
                fetchAllJobsWithLongPolling();
              }
            }, 5000);
          }
        }
      }
    };

    fetchInitialState();

    return () => {
      isMounted = false;
      if (updateTimerRef.current !== null) {
        clearTimeout(updateTimerRef.current);
      }
    };
  }, []);

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
    return 'Scan';
  };

  const jobs = Object.entries(displayedProgress);
  const activeJobs = jobs.filter(([_, job]) => job.status === 'running');

  if (loading) {
    return (
      <div className="flex items-center gap-2">
        <span className="loading loading-spinner loading-sm"></span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {activeJobs.length === 0 ? (
        <div className="flex items-center gap-2 text-base-content/70">
          <span className="text-sm">Idle</span>
          <GiMusicalNotes className="w-5 h-5" />
        </div>
      ) : (
        activeJobs.map(([jobId, job]) => {
          const jobType = getJobType(jobId);
          
          return (
            <div key={jobId} className="flex items-center gap-2 px-2 py-1 bg-base-200 rounded-full border border-base-300">
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
            </div>
          );
        })
      )}
    </div>
  );
}

