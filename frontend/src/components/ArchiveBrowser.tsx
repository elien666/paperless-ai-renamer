import { useState, useEffect, useRef, useCallback } from 'react';
import { apiService } from '../services/api';
import type { ProgressResponse } from '../services/api';
import { formatDistanceToNow } from 'date-fns';
import { IoIosHeartEmpty } from 'react-icons/io';
import DocumentProcessor from './DocumentProcessor';

type ArchiveType = 'rename' | 'index' | 'scan';

export default function ArchiveBrowser() {
  const [activeTab, setActiveTab] = useState<'rename' | 'jobs'>('rename');
  const [renameItems, setRenameItems] = useState<any[]>([]);
  const [indexItems, setIndexItems] = useState<any[]>([]);
  const [scanItems, setScanItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [initialFetching, setInitialFetching] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState<Record<string, boolean>>({
    rename: true,
    index: true,
    scan: true,
  });
  const [currentPage, setCurrentPage] = useState<Record<string, number>>({
    rename: 1,
    index: 1,
    scan: 1,
  });
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const observerTargetRef = useRef<HTMLDivElement>(null);
  const fetchingRef = useRef<Record<string, boolean>>({
    rename: false,
    index: false,
    scan: false,
  });
  const previousProgressRef = useRef<Record<string, ProgressResponse>>({});

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
        setRenameItems(prev => append ? [...prev, ...data.items] : data.items);
        setHasMore(prev => ({ ...prev, rename: data.has_more }));
      } else if (type === 'index') {
        setIndexItems(prev => append ? [...prev, ...data.items] : data.items);
        setHasMore(prev => ({ ...prev, index: data.has_more }));
      } else if (type === 'scan') {
        setScanItems(prev => append ? [...prev, ...data.items] : data.items);
        setHasMore(prev => ({ ...prev, scan: data.has_more }));
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
    fetchingRef.current = { rename: false, index: false, scan: false };
    setInitialFetching(new Set());
    
    if (activeTab === 'rename') {
      setRenameItems([]);
      setCurrentPage(prev => ({ ...prev, rename: 1 }));
      setHasMore(prev => ({ ...prev, rename: true }));
      // Fetch immediately without showing loading spinner
      fetchArchive('rename', 1, false, true);
    } else {
      setIndexItems([]);
      setScanItems([]);
      setCurrentPage(prev => ({ ...prev, index: 1, scan: 1 }));
      setHasMore(prev => ({ ...prev, index: true, scan: true }));
      // Fetch immediately without showing loading spinner
      fetchArchive('index', 1, false, true);
      fetchArchive('scan', 1, false, true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // Poll for progress updates and refresh archive when jobs complete
  useEffect(() => {
    let isMounted = true;

    const pollProgress = async () => {
      try {
        const data = await apiService.getProgress(undefined, false);
        if (!isMounted) return;

        const currentProgress = data.jobs || { [data.status || 'unknown']: data };
        
        // Check for jobs that just finished
        Object.entries(currentProgress).forEach(([jobId, job]) => {
          const previousJob = previousProgressRef.current[jobId];
          
          // If job status changed from 'running' to 'completed' or 'failed'
          if (previousJob?.status === 'running' && (job.status === 'completed' || job.status === 'failed')) {
            // Refresh relevant archive data
            if (jobId === 'index') {
              // Refresh index archive
              fetchArchive('index', 1, false, true);
            } else if (jobId.startsWith('scan') || jobId === 'scan') {
              // Refresh scan archive
              fetchArchive('scan', 1, false, true);
            }
            
            // Always refresh rename archive when any job completes (jobs might create rename entries)
            fetchArchive('rename', 1, false, true);
          }
        });

        previousProgressRef.current = currentProgress;
      } catch {
        // Silently handle errors, will retry on next poll
      }
    };

    // Initial poll
    pollProgress();

    // Poll every 5 seconds
    const intervalId = setInterval(() => {
      if (isMounted) {
        pollProgress();
      }
    }, 5000);

    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
          } else {
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

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Tabs */}
      <div className="mb-4 flex items-center justify-between flex-none">
        <div className="tabs tabs-border">
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
        </div>
        <DocumentProcessor />
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
                      {/* First column: Document ID (fixed width) */}
                      <div className="shrink-0 w-24">
                        <span className="badge badge-sm badge-soft badge-success">
                          #{item.document_id}
                        </span>
                      </div>
                      {/* Second column: Rename info and timestamp */}
                      <div className="flex-1 flex flex-col gap-1 min-w-0">
                        <div className="text-base font-semibold">
                          <span className="text-base-content bg-success/10 px-2 py-1 rounded inline-block" title={item.new_title}>
                            {item.new_title}
                          </span>
                        </div>
                        <div className="text-sm">
                          <span className="text-base-content bg-error/10 px-2 py-1 rounded inline-block" title={item.old_title}>
                            {item.old_title}
                          </span>
                        </div>
                        <span className="text-xs text-base-content/50">{formatDate(item.timestamp)}</span>
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
                <ul className="menu menu-lg flex-1 w-full">
                  {allJobs.map((item: any) => (
                    <li key={`${item.type}-${item.id}`} className="w-full">
                      <div className="flex w-full items-start gap-4 p-4 hover:bg-base-200 cursor-default">
                        {/* First column: Type (fixed width) */}
                        <div className="shrink-0 w-24">
                          <span className={`badge badge-sm badge-soft ${item.type === 'index' ? 'badge-success' : 'badge-info'}`}>
                            {item.type === 'index' ? 'Index' : 'Scan'}
                          </span>
                        </div>
                        {/* Second column: Results and timestamp */}
                        <div className="flex-1 flex flex-col gap-1 min-w-0">
                          <div className="text-base">
                            {item.type === 'index' ? (
                              <span>Indexed {item.documents_indexed} {item.documents_indexed === 1 ? 'document' : 'documents'}</span>
                            ) : (
                              <span>
                                Found {item.total_documents} {item.total_documents === 1 ? 'document' : 'documents'}, {item.bad_title_documents || 0} {item.bad_title_documents === 1 ? 'bad title identified' : 'bad titles identified'}
                              </span>
                            )}
                          </div>
                          <span className="text-xs text-base-content/50">{formatDate(item.timestamp)}</span>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              );
            })()}
          </>
        )}

        {/* Loading indicator at bottom for infinite scroll */}
        <div ref={observerTargetRef} className="flex justify-center py-4">
          {loading && (
            <span className="loading loading-spinner loading-md"></span>
          )}
        </div>
      </div>
    </div>
  );
}
