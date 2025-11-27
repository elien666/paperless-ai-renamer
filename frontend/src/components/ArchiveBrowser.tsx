import { useState, useEffect, useRef, useCallback } from 'react';
import { apiService } from '../services/api';
import type { ProgressResponse } from '../services/api';
import { useProgress } from '../contexts/ProgressContext';
import { formatDistanceToNow } from 'date-fns';
import { IoIosHeartEmpty } from 'react-icons/io';
import { FaFileAlt } from 'react-icons/fa';
import { GiBroom } from 'react-icons/gi';

type ArchiveType = 'rename' | 'index' | 'scan' | 'error';

export default function ArchiveBrowser() {
  const [activeTab, setActiveTab] = useState<'rename' | 'jobs' | 'issues'>('rename');
  const [renameItems, setRenameItems] = useState<any[]>([]);
  const [indexItems, setIndexItems] = useState<any[]>([]);
  const [scanItems, setScanItems] = useState<any[]>([]);
  const [errorItems, setErrorItems] = useState<any[]>([]);
  const [selectedError, setSelectedError] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [initialFetching, setInitialFetching] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState<Record<string, boolean>>({
    rename: true,
    index: true,
    scan: true,
    error: true,
  });
  const [currentPage, setCurrentPage] = useState<Record<string, number>>({
    rename: 1,
    index: 1,
    scan: 1,
    error: 1,
  });
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const observerTargetRef = useRef<HTMLDivElement>(null);
  const fetchingRef = useRef<Record<string, boolean>>({
    rename: false,
    index: false,
    scan: false,
    error: false,
  });
  const { subscribe } = useProgress();
  const [toastMessage, setToastMessage] = useState<{ type: 'error'; text: string } | null>(null);
  const [isClearing, setIsClearing] = useState(false);
  const [showClearModal, setShowClearModal] = useState(false);

  const fetchArchive = useCallback(async (type: ArchiveType, page: number, append: boolean = false, isInitial: boolean = false) => {
    // Prevent concurrent requests for the same type
    if (fetchingRef.current[type]) return;
    
    fetchingRef.current[type] = true;
    // Only show loading spinner for infinite scroll, not initial load
    if (!isInitial) {
      setLoading(true);
    } else {
      // Track initial fetches
      setInitialFetching(prev => new Set(prev).add(type));
    }
    setError(null);
    try {
      const data = await apiService.getArchive(type, page, 50);
      
      if (type === 'rename') {
        setRenameItems(append ? (prev) => [...prev, ...data.items] : () => [...data.items]);
        setHasMore(prev => ({ ...prev, rename: data.has_more }));
      } else if (type === 'index') {
        setIndexItems(append ? (prev) => [...prev, ...data.items] : () => [...data.items]);
        setHasMore(prev => ({ ...prev, index: data.has_more }));
      } else if (type === 'scan') {
        setScanItems(append ? (prev) => [...prev, ...data.items] : () => [...data.items]);
        setHasMore(prev => ({ ...prev, scan: data.has_more }));
      } else if (type === 'error') {
        setErrorItems(append ? (prev) => [...prev, ...data.items] : () => [...data.items]);
        setHasMore(prev => ({ ...prev, error: data.has_more }));
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to fetch archive');
    } finally {
      fetchingRef.current[type] = false;
      if (!isInitial) {
        setLoading(false);
      } else {
        // Remove from initial fetching set
        setInitialFetching(prev => {
          const next = new Set(prev);
          next.delete(type);
          return next;
        });
      }
    }
  }, []);

  // Load initial data when tab changes - fetch immediately without blocking UI
  useEffect(() => {
    // Reset fetching state when tab changes
    fetchingRef.current = { rename: false, index: false, scan: false, error: false };
    setInitialFetching(new Set());
    
    if (activeTab === 'rename') {
      setRenameItems([]);
      setCurrentPage(prev => ({ ...prev, rename: 1 }));
      setHasMore(prev => ({ ...prev, rename: true }));
      // Fetch immediately without showing loading spinner
      fetchArchive('rename', 1, false, true);
    } else if (activeTab === 'jobs') {
      setIndexItems([]);
      setScanItems([]);
      setCurrentPage(prev => ({ ...prev, index: 1, scan: 1 }));
      setHasMore(prev => ({ ...prev, index: true, scan: true }));
      // Fetch immediately without showing loading spinner
      fetchArchive('index', 1, false, true);
      fetchArchive('scan', 1, false, true);
    } else if (activeTab === 'issues') {
      setErrorItems([]);
      setCurrentPage(prev => ({ ...prev, error: 1 }));
      setHasMore(prev => ({ ...prev, error: true }));
      // Fetch immediately without showing loading spinner
      fetchArchive('error', 1, false, true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // Subscribe to progress updates and refresh archive when jobs complete
  useEffect(() => {
    // Subscribe to shared progress updates
    const unsubscribe = subscribe((currentProgress: Record<string, ProgressResponse>, previousProgress: Record<string, ProgressResponse>) => {
      // Check for jobs that just finished
      Object.entries(currentProgress).forEach(([jobId, job]) => {
        const previousJob = previousProgress[jobId];
        
        // If job status changed from 'running' to 'failed', show toast
        if (previousJob?.status === 'running' && job.status === 'failed') {
          const jobType = jobId === 'index' ? 'Index' : jobId.startsWith('process-') ? 'Process' : 'Scan';
          const errorMessage = job.error || 'Unknown error';
          setToastMessage({
            type: 'error',
            text: `${jobType} job failed: ${errorMessage}`
          });
          // Clear toast after 5 seconds
          setTimeout(() => setToastMessage(null), 5000);
        }
        
        // If job status changed from 'running' to 'completed' or 'failed'
        // OR if a job is now completed and wasn't completed before (handles jobs that complete quickly)
        const jobJustCompleted = previousJob?.status === 'running' && (job.status === 'completed' || job.status === 'failed');
        const jobNowCompleted = (job.status === 'completed' || job.status === 'failed') && previousJob?.status !== job.status;
        
        if (jobJustCompleted || jobNowCompleted) {
          // Refresh relevant archive data - use setTimeout to ensure state updates are processed
          setTimeout(() => {
            if (jobId === 'index') {
              // Refresh index archive
              fetchArchive('index', 1, false, true);
            } else if (jobId.startsWith('scan') || jobId === 'scan') {
              // Refresh scan archive
              fetchArchive('scan', 1, false, true);
            }
            
            // Always refresh rename archive when any job completes (jobs might create rename entries)
            // This is especially important for process jobs (including webhook-triggered) which create rename entries
            fetchArchive('rename', 1, false, true);
            
            // Always refresh error archive when any job completes or fails (new errors may have been created)
            fetchArchive('error', 1, false, true);
          }, 0);
        }
      });
    });

    return unsubscribe;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subscribe]);

  // Handle ESC key to close modals
  useEffect(() => {
    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (selectedError) {
          setSelectedError(null);
        }
        if (showClearModal) {
          setShowClearModal(false);
        }
      }
    };

    if (selectedError || showClearModal) {
      document.addEventListener('keydown', handleEsc);
      return () => {
        document.removeEventListener('keydown', handleEsc);
      };
    }
  }, [selectedError, showClearModal]);

  // Infinite scroll observer
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !loading) {
          if (activeTab === 'rename') {
            const nextPage = currentPage.rename + 1;
            if (hasMore.rename && !fetchingRef.current.rename) {
              setCurrentPage(prev => ({ ...prev, rename: nextPage }));
              fetchArchive('rename', nextPage, true);
            }
          } else if (activeTab === 'jobs') {
            if (hasMore.index && !fetchingRef.current.index) {
              const nextIndexPage = currentPage.index + 1;
              setCurrentPage(prev => ({ ...prev, index: nextIndexPage }));
              fetchArchive('index', nextIndexPage, true);
            }
            if (hasMore.scan && !fetchingRef.current.scan) {
              const nextScanPage = currentPage.scan + 1;
              setCurrentPage(prev => ({ ...prev, scan: nextScanPage }));
              fetchArchive('scan', nextScanPage, true);
            }
          } else if (activeTab === 'issues') {
            const nextPage = currentPage.error + 1;
            if (hasMore.error && !fetchingRef.current.error) {
              setCurrentPage(prev => ({ ...prev, error: nextPage }));
              fetchArchive('error', nextPage, true);
            }
          }
        }
      },
      { threshold: 0.1 }
    );

    const currentTarget = observerTargetRef.current;
    if (currentTarget) {
      observer.observe(currentTarget);
    }

    return () => {
      if (currentTarget) {
        observer.unobserve(currentTarget);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, activeTab, currentPage, hasMore]);

  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString);
      return formatDistanceToNow(date, { addSuffix: true });
    } catch {
      return dateString;
    }
  };

  const getPaperlessUrl = (documentId: number) => {
    // Get Paperless URL from environment variable or use default
    const paperlessUrl = import.meta.env.VITE_PAPERLESS_URL || 'https://paperless.tty7.de';
    return `${paperlessUrl}/documents/${documentId}/details`;
  };

  const handleRenameItemClick = (documentId: number) => {
    const url = getPaperlessUrl(documentId);
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const handleClearIssues = () => {
    if (errorItems.length === 0) return;
    setShowClearModal(true);
  };

  const confirmClearIssues = async () => {
    setShowClearModal(false);
    setIsClearing(true);
    setError(null);
    
    try {
      await apiService.clearErrorArchive();
      // Clear the error items and reset pagination
      setErrorItems([]);
      setCurrentPage(prev => ({ ...prev, error: 1 }));
      setHasMore(prev => ({ ...prev, error: true }));
      // Optionally refresh to ensure UI is in sync
      fetchArchive('error', 1, false, true);
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || err.message || 'Failed to clear issues log';
      setError(errorMessage);
      setToastMessage({
        type: 'error',
        text: errorMessage
      });
      setTimeout(() => setToastMessage(null), 5000);
    } finally {
      setIsClearing(false);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Tabs */}
      <div className="mb-4 flex-none">
        <div className="flex items-center justify-between gap-4">
          <div className="tabs tabs-border flex-1">
            <button
              className={`tab ${activeTab === 'rename' ? 'tab-active' : ''}`}
              onClick={() => setActiveTab('rename')}
            >
              Renaming
            </button>
            <button
              className={`tab ${activeTab === 'jobs' ? 'tab-active' : ''}`}
              onClick={() => setActiveTab('jobs')}
            >
              Jobs
            </button>
            <button
              className={`tab ${activeTab === 'issues' ? 'tab-active' : ''}`}
              onClick={() => setActiveTab('issues')}
            >
              Issues
            </button>
          </div>
          {activeTab === 'issues' && errorItems.length > 0 && (
            <button
              type="button"
              className="btn btn-sm btn-neutral"
              onClick={handleClearIssues}
              disabled={isClearing}
            >
              {isClearing ? (
                <>
                  <span className="loading loading-spinner loading-xs"></span>
                  Clearing...
                </>
              ) : (
                <>
                  <GiBroom className="w-4 h-4" />
                  Clear All
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="alert alert-error mb-4 flex-none">
          <span>Error: {error}</span>
        </div>
      )}

      {/* Scrollable content area */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto min-h-0 bg-base-100 rounded-box shadow-sm flex flex-col"
      >
        {/* Renaming Tab */}
        {activeTab === 'rename' && (
          <>
            {renameItems.length === 0 && !initialFetching.has('rename') ? (
              <div className="flex flex-col items-center justify-center h-full min-h-[400px] p-8">
                <div className="text-center space-y-4">
                  <IoIosHeartEmpty className="w-16 h-16 mx-auto text-base-content/30 pointer-events-none" />
                  <div className="space-y-2">
                    <h3 className="text-lg font-semibold text-base-content">No rename history</h3>
                    <p className="text-sm text-base-content/70 max-w-md">
                      Document titles that have been renamed will appear here. Start processing documents to see rename history.
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <ul className="menu menu-lg flex-1 w-full">
                {renameItems.map((item: any) => (
                  <li key={item.id} className="w-full">
                    <div 
                      className="flex w-full items-start gap-4 p-4 hover:bg-base-200 cursor-pointer"
                      onClick={() => handleRenameItemClick(item.document_id)}
                    >
                      {/* First column: Renaming badge (fixed width) */}
                      <div className="shrink-0 w-24">
                        <span className="badge badge-sm badge-soft badge-success">
                          Renaming
                        </span>
                      </div>
                      {/* Second column: Rename info, document button, and timestamp */}
                      <div className="flex-1 flex flex-col gap-1 min-w-0">
                        <div className="text-base font-semibold">
                          <span className="text-base-content bg-success/10 px-2 py-1 rounded inline-block" title={item.new_title}>
                            {item.new_title}
                          </span>
                        </div>
                        <div className="text-sm">
                          <span className="text-base-content bg-error/10 px-2 py-1 rounded inline-block line-through" title={item.old_title}>
                            {item.old_title}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <button
                            type="button"
                            className="btn btn-xs btn-ghost border border-base-content/20"
                            onClick={(e) => {
                              e.stopPropagation();
                              const url = getPaperlessUrl(item.document_id);
                              window.open(url, '_blank', 'noopener,noreferrer');
                            }}
                          >
                            <FaFileAlt className="w-3 h-3" />
                            Document #{item.document_id}
                          </button>
                          <span className="text-xs text-base-content/50">
                            {formatDate(item.timestamp)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        {/* Jobs Tab */}
        {activeTab === 'jobs' && (
          <>
            {(() => {
              // Combine and sort all jobs by timestamp (newest first)
              const allJobs = [
                ...indexItems.map((item: any) => ({ ...item, type: 'index' })),
                ...scanItems.map((item: any) => ({ ...item, type: 'scan' }))
              ].sort((a, b) => {
                const dateA = new Date(a.timestamp).getTime();
                const dateB = new Date(b.timestamp).getTime();
                return dateB - dateA; // Newest first
              });

              // Only show "no jobs" if we're not currently fetching initial data
              const isInitialFetching = initialFetching.has('index') || initialFetching.has('scan');
              if (allJobs.length === 0 && !isInitialFetching) {
                return (
                  <div className="flex flex-col items-center justify-center h-full min-h-[400px] p-8">
                    <div className="text-center space-y-4">
                      <IoIosHeartEmpty className="w-16 h-16 mx-auto text-base-content/30 pointer-events-none" />
                      <div className="space-y-2">
                        <h3 className="text-lg font-semibold text-base-content">No jobs found</h3>
                        <p className="text-sm text-base-content/70 max-w-md">
                          Index and scan jobs will appear here once they are executed. Use the document processor to start indexing or scanning documents.
                        </p>
                      </div>
                    </div>
                  </div>
                );
              }

              return (
                <>
                  <ul className="menu menu-lg flex-1 w-full">
                    {allJobs.map((item: any) => {
                      const hasError = item.error || item.status === 'failed';
                      
                      return (
                        <li key={`${item.type}-${item.id}`} className="w-full">
                          <div className="flex w-full items-start gap-4 p-4 hover:bg-base-200 cursor-default">
                            {/* First column: Type (fixed width) */}
                            <div className="shrink-0 w-24">
                              <span className={`badge badge-sm badge-soft ${hasError ? 'badge-error' : item.type === 'index' ? 'badge-success' : 'badge-info'}`}>
                                {item.type === 'index' ? 'Index' : 'Scan'}
                              </span>
                            </div>
                            {/* Second column: Results and timestamp */}
                            <div className="flex-1 flex flex-col gap-1 min-w-0">
                              <div className={`text-base ${hasError ? 'text-error' : ''}`}>
                                {hasError ? (
                                  <span>Failed: {item.error || 'Unknown error'}</span>
                                ) : item.type === 'index' ? (
                                  <span>Indexed {item.documents_indexed} {item.documents_indexed === 1 ? 'document' : 'documents'}</span>
                                ) : (
                                  <span>
                                    Found {item.total_documents} {item.total_documents === 1 ? 'document' : 'documents'}, {item.bad_title_documents || 0} {item.bad_title_documents === 1 ? 'bad title identified' : 'bad titles identified'}
                                  </span>
                                )}
                              </div>
                              {item.errors && item.errors.length > 0 && (
                                <div className="text-sm text-error/80 mt-1">
                                  {item.errors.length} {item.errors.length === 1 ? 'document error' : 'document errors'}
                                </div>
                              )}
                              <span className="text-xs text-base-content/50">{formatDate(item.timestamp)}</span>
                            </div>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                  
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
            })()}
          </>
        )}

        {/* Issues Tab */}
        {activeTab === 'issues' && (
          <>
            {errorItems.length === 0 && !initialFetching.has('error') ? (
              <div className="flex flex-col items-center justify-center h-full min-h-[400px] p-8">
                <div className="text-center space-y-4">
                  <IoIosHeartEmpty className="w-16 h-16 mx-auto text-base-content/30 pointer-events-none" />
                  <div className="space-y-2">
                    <h3 className="text-lg font-semibold text-base-content">No errors found</h3>
                    <p className="text-sm text-base-content/70 max-w-md">
                      Errors that occur during document processing, indexing, or scanning will appear here.
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <ul className="menu menu-lg flex-1 w-full">
                {errorItems.map((item: any) => (
                  <li key={item.id} className="w-full">
                    <div 
                      className="flex w-full items-start gap-4 p-4 hover:bg-base-200 cursor-pointer"
                      onClick={() => setSelectedError(item)}
                    >
                      {/* First column: Job Type (fixed width) */}
                      <div className="shrink-0 w-24">
                        <span className="badge badge-sm badge-neutral">
                          {item.job_type === 'process' ? 'Generation' : item.job_type || 'Error'}
                        </span>
                      </div>
                      {/* Second column: Error info and timestamp */}
                      <div className="flex-1 flex flex-col gap-1 min-w-0">
                        <div className="text-base text-error">
                          {item.error_message ? (
                            <span className="line-clamp-2" title={item.error_message}>
                              {item.error_message}
                            </span>
                          ) : (
                            <span>Unknown error</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 flex-wrap">
                          {item.document_id && (
                            <button
                              type="button"
                              className="btn btn-xs btn-ghost border border-base-content/20"
                              onClick={(e) => {
                                e.stopPropagation();
                                const url = getPaperlessUrl(item.document_id);
                                window.open(url, '_blank', 'noopener,noreferrer');
                              }}
                            >
                              <FaFileAlt className="w-3 h-3" />
                              Document #{item.document_id}
                            </button>
                          )}
                          <span className="text-xs text-base-content/50">
                            {formatDate(item.timestamp)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        {/* Loading indicator at bottom for infinite scroll */}
        <div ref={observerTargetRef} className="flex justify-center py-4">
          {loading && (
            <span className="loading loading-spinner loading-md"></span>
          )}
        </div>
      </div>

      {/* Clear Issues Confirmation Modal */}
      {showClearModal && (
        <dialog open className="modal modal-open">
          <div className="modal-box">
            <form method="dialog">
              <button
                type="button"
                className="btn btn-circle btn-ghost absolute right-2 top-2"
                onClick={() => setShowClearModal(false)}
              >
                <span className="text-xl">✕</span>
              </button>
            </form>
            <h3 className="font-bold text-lg mb-4">Clear Issues Log</h3>
            <p className="py-4">
              Are you sure you want to clear all {errorItems.length} error{errorItems.length !== 1 ? 's' : ''} from the issues log? This action cannot be undone.
            </p>
            <div className="modal-action">
              <button
                type="button"
                className="btn btn-neutral"
                onClick={confirmClearIssues}
                disabled={isClearing}
              >
                {isClearing ? (
                  <>
                    <span className="loading loading-spinner loading-xs"></span>
                    Clearing...
                  </>
                ) : (
                  <>
                    <GiBroom className="w-4 h-4" />
                    Clear All
                  </>
                )}
              </button>
            </div>
          </div>
          <form method="dialog" className="modal-backdrop" onClick={() => setShowClearModal(false)}>
            <button>close</button>
          </form>
        </dialog>
      )}

      {/* Error Detail Modal */}
      {selectedError && (
        <dialog open className="modal modal-open">
          <div className="modal-box max-w-2xl">
            <form method="dialog">
              <button
                type="button"
                className="btn btn-circle btn-ghost absolute right-2 top-2"
                onClick={() => setSelectedError(null)}
              >
                <span className="text-xl">✕</span>
              </button>
            </form>
            <h3 className="font-bold text-lg mb-4">
              {selectedError.job_type === 'process' ? 'Generation' : selectedError.job_type || 'Error'}
            </h3>
            <div className="space-y-4">
              {/* Timestamp at top */}
              <div>
                <p className="text-xs text-base-content/50">{new Date(selectedError.timestamp).toLocaleString()}</p>
              </div>
              
              {/* Error Message */}
              <div>
                <div className="bg-error/10 border border-error/20 rounded-lg p-4">
                  <span className="whitespace-pre-wrap wrap-break-word text-base-content">{selectedError.error_message || 'No error message available'}</span>
                </div>
              </div>
            </div>
            
            {/* Footer with Document button and Job ID */}
            {(selectedError.document_id || selectedError.job_id) && (
              <div className="modal-action mt-6 pt-4 border-t border-base-300">
                <div className="flex items-center gap-4 w-full">
                  {selectedError.document_id && (
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost border border-base-content/20"
                      onClick={() => {
                        const url = getPaperlessUrl(selectedError.document_id);
                        window.open(url, '_blank', 'noopener,noreferrer');
                      }}
                    >
                      <FaFileAlt className="w-4 h-4" />
                      Document #{selectedError.document_id}
                    </button>
                  )}
                  {selectedError.job_id && (
                    <span className="text-xs text-base-content/50 ml-auto">{selectedError.job_id}</span>
                  )}
                </div>
              </div>
            )}
          </div>
          <form method="dialog" className="modal-backdrop" onClick={() => setSelectedError(null)}>
            <button>close</button>
          </form>
        </dialog>
      )}
    </div>
  );
}
