import { useState, useEffect, useRef, useCallback } from 'react';
import { apiService } from '../services/api';
import DocumentProcessor from './DocumentProcessor';

type ArchiveType = 'rename' | 'index' | 'scan';

export default function ArchiveBrowser() {
  const [activeTab, setActiveTab] = useState<'rename' | 'jobs'>('rename');
  const [renameItems, setRenameItems] = useState<any[]>([]);
  const [indexItems, setIndexItems] = useState<any[]>([]);
  const [scanItems, setScanItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
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

  const fetchArchive = useCallback(async (type: ArchiveType, page: number, append: boolean = false) => {
    // Prevent concurrent requests for the same type
    if (fetchingRef.current[type]) return;
    
    fetchingRef.current[type] = true;
    setLoading(true);
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
      setLoading(false);
    }
  }, []);

  // Load initial data when tab changes
  useEffect(() => {
    // Reset fetching state when tab changes
    fetchingRef.current = { rename: false, index: false, scan: false };
    
    if (activeTab === 'rename') {
      setRenameItems([]);
      setCurrentPage(prev => ({ ...prev, rename: 1 }));
      setHasMore(prev => ({ ...prev, rename: true }));
      fetchArchive('rename', 1, false);
    } else {
      setIndexItems([]);
      setScanItems([]);
      setCurrentPage(prev => ({ ...prev, index: 1, scan: 1 }));
      setHasMore(prev => ({ ...prev, index: true, scan: true }));
      fetchArchive('index', 1, false);
      fetchArchive('scan', 1, false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

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
      return new Date(dateString).toLocaleString();
    } catch {
      return dateString;
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Tabs */}
      <div className="mb-4 flex items-center justify-between">
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
        <div className="alert alert-error mb-4">
          <span>Error: {error}</span>
        </div>
      )}

      {/* Scrollable content area */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto"
        style={{ maxHeight: 'calc(100vh - 280px)' }}
      >
        {/* Renaming Tab */}
        {activeTab === 'rename' && (
          <ul className="menu bg-base-100 rounded-box shadow-sm">
            {renameItems.length === 0 && !loading ? (
              <li>
                <div className="alert alert-info">
                  <span>No rename history found.</span>
                </div>
              </li>
            ) : (
              renameItems.map((item: any) => (
                <li key={item.id}>
                  <div className="flex flex-col gap-2 p-4 hover:bg-base-200">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="badge badge-primary">{item.document_id}</span>
                        <span className="text-xs text-base-content/70">{formatDate(item.timestamp)}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm line-through text-base-content/60 truncate flex-1" title={item.old_title}>
                        {item.old_title}
                      </span>
                      <span className="text-base-content/40">→</span>
                      <span className="text-sm font-semibold text-success truncate flex-1" title={item.new_title}>
                        {item.new_title}
                      </span>
                    </div>
                  </div>
                </li>
              ))
            )}
          </ul>
        )}

        {/* Jobs Tab */}
        {activeTab === 'jobs' && (
          <div className="space-y-4">
            {/* Index Jobs */}
            <div className="card bg-base-100 shadow-sm">
              <div className="card-body p-4">
                <h3 className="card-title text-lg mb-2">Index Jobs</h3>
                {indexItems.length === 0 && !loading ? (
                  <p className="text-sm text-base-content/70">No index jobs found.</p>
                ) : (
                  <ul className="menu bg-base-200 rounded-box">
                    {indexItems.map((item: any) => (
                      <li key={item.id}>
                        <div className="flex items-center justify-between p-3 hover:bg-base-300">
                          <span className="text-sm text-base-content/70">{formatDate(item.timestamp)}</span>
                          <span className="badge badge-success">{item.documents_indexed} indexed</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            {/* Scan Jobs */}
            <div className="card bg-base-100 shadow-sm">
              <div className="card-body p-4">
                <h3 className="card-title text-lg mb-2">Scan Jobs</h3>
                {scanItems.length === 0 && !loading ? (
                  <p className="text-sm text-base-content/70">No scan jobs found.</p>
                ) : (
                  <ul className="menu bg-base-200 rounded-box">
                    {scanItems.map((item: any) => (
                      <li key={item.id}>
                        <div className="flex items-center justify-between p-3 hover:bg-base-300">
                          <span className="text-sm text-base-content/70">{formatDate(item.timestamp)}</span>
                          <div className="flex items-center gap-2">
                            <span className="badge badge-info">{item.total_documents} total</span>
                            <span className="badge badge-warning">{item.bad_title_documents} bad titles</span>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
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
