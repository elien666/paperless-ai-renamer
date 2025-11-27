import { useEffect, useState } from 'react';
import { apiService } from '../services/api';
import type { ProgressResponse } from '../services/api';

export default function ProgressView() {
  const [progress, setProgress] = useState<Record<string, ProgressResponse>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    const fetchAllJobsWithLongPolling = async () => {
      try {
        // Single long polling request for ALL jobs
        // Backend will wait for any job to start or update, then return all jobs
        const data = await apiService.getProgress(undefined, true, 30);
        
        if (isMounted) {
          if (data.jobs) {
            setProgress(data.jobs);
          } else {
            // Single job response (shouldn't happen when querying all, but handle it)
            setProgress({ [data.status || 'unknown']: data });
          }
          setError(null);
          setLoading(false);
          
          // Immediately start a new long poll for the next update
          fetchAllJobsWithLongPolling();
        }
      } catch (err: any) {
        if (isMounted) {
          // Handle timeout (expected) or other errors
          if (err.code === 'ECONNABORTED' || err.message?.includes('timeout') || err.response?.status === 408) {
            // Timeout is expected - get current state and continue long polling
            try {
              const data = await apiService.getProgress();
              if (isMounted) {
                if (data.jobs) {
                  setProgress(data.jobs);
                } else {
                  setProgress({ [data.status || 'unknown']: data });
                }
                // Continue long polling
                fetchAllJobsWithLongPolling();
              }
            } catch (refreshErr: any) {
              // If refresh also fails, retry after delay
              if (isMounted) {
                setTimeout(() => {
                  fetchAllJobsWithLongPolling();
                }, 2000);
              }
            }
          } else {
            setError(err.response?.data?.detail || err.message || 'Failed to fetch progress');
            setLoading(false);
            // Retry after error
            setTimeout(() => {
              if (isMounted) {
                fetchAllJobsWithLongPolling();
              }
            }, 5000);
          }
        }
      }
    };

    fetchAllJobsWithLongPolling();

    return () => {
      isMounted = false;
    };
  }, []);

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A';
    try {
      return new Date(dateString).toLocaleString();
    } catch {
      return dateString;
    }
  };

  const getStatusColor = (status?: string) => {
    switch (status) {
      case 'completed':
        return 'success';
      case 'failed':
        return 'error';
      case 'running':
        return 'info';
      default:
        return 'neutral';
    }
  };

  const calculatePercentage = (processed?: number, total?: number) => {
    if (!total || total === 0) return 0;
    return Math.round((processed || 0) / total * 100);
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="alert alert-error">
        <span>Error: {error}</span>
      </div>
    );
  }

  const jobs = Object.entries(progress);
  
  if (jobs.length === 0) {
    return (
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <h2 className="card-title">Progress</h2>
          <p>No active or completed jobs found.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Current Progress</h2>
      {jobs.map(([jobId, job]) => (
        <div key={jobId} className="card bg-base-100 shadow-xl">
          <div className="card-body">
            <div className="flex justify-between items-start mb-4">
              <h3 className="card-title">
                Job: {jobId === 'index' ? 'Index' : jobId.substring(0, 8)}
              </h3>
              <div className={`badge badge-${getStatusColor(job.status)}`}>
                {job.status || 'unknown'}
              </div>
            </div>

            {job.status === 'running' && job.total !== undefined && (
              <div className="mb-4">
                <div className="flex justify-between mb-2">
                  <span>Progress</span>
                  <span>
                    {job.processed || 0} / {job.total} ({calculatePercentage(job.processed, job.total)}%)
                  </span>
                </div>
                <progress
                  className="progress progress-primary w-full"
                  value={job.processed || 0}
                  max={job.total}
                ></progress>
              </div>
            )}

            {job.status === 'completed' && (
              <div className="space-y-2">
                {job.indexed !== undefined && (
                  <div className="stat">
                    <div className="stat-title">Documents Indexed</div>
                    <div className="stat-value text-primary">{job.indexed}</div>
                  </div>
                )}
                {job.skipped_scan !== undefined && (
                  <div className="stat">
                    <div className="stat-title">Skipped (Scan)</div>
                    <div className="stat-value text-secondary">{job.skipped_scan}</div>
                  </div>
                )}
                {job.cleaned !== undefined && (
                  <div className="stat">
                    <div className="stat-title">Titles Cleaned</div>
                    <div className="stat-value text-accent">{job.cleaned}</div>
                  </div>
                )}
                {job.processed !== undefined && job.total !== undefined && (
                  <div className="stat">
                    <div className="stat-title">Processed</div>
                    <div className="stat-value">{job.processed} / {job.total}</div>
                  </div>
                )}
              </div>
            )}

            {job.status === 'failed' && job.error && (
              <div className="alert alert-error">
                <span>Error: {job.error}</span>
              </div>
            )}

            <div className="divider"></div>

            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="font-semibold">Created</div>
                <div>{formatDate(job.created_at)}</div>
              </div>
              {job.completed_at && (
                <div>
                  <div className="font-semibold">Completed</div>
                  <div>{formatDate(job.completed_at)}</div>
                </div>
              )}
              {job.newer_than && (
                <div>
                  <div className="font-semibold">Newer Than</div>
                  <div>{job.newer_than}</div>
                </div>
              )}
              {job.older_than && (
                <div>
                  <div className="font-semibold">Older Than</div>
                  <div>{job.older_than}</div>
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

