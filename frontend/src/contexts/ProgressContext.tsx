import React, { createContext, useContext, useEffect, useState, useRef, useCallback } from 'react';
import { apiService } from '../services/api';
import type { ProgressResponse } from '../services/api';

interface ProgressContextType {
  progress: Record<string, ProgressResponse>;
  loading: boolean;
  subscribe: (callback: (progress: Record<string, ProgressResponse>, previous: Record<string, ProgressResponse>) => void) => () => void;
}

const ProgressContext = createContext<ProgressContextType>({
  progress: {},
  loading: true,
  subscribe: () => () => {}, // Dummy subscribe function for initial context
});

export function ProgressProvider({ children }: { children: React.ReactNode }) {
  const [progress, setProgress] = useState<Record<string, ProgressResponse>>({});
  const [loading, setLoading] = useState(true);
  const previousProgressRef = useRef<Record<string, ProgressResponse>>({});
  const isMountedRef = useRef(true);
  const subscribersRef = useRef<Set<(progress: Record<string, ProgressResponse>, previous: Record<string, ProgressResponse>) => void>>(new Set());

  // Subscribe to progress updates
  const subscribe = useCallback((callback: (progress: Record<string, ProgressResponse>, previous: Record<string, ProgressResponse>) => void) => {
    subscribersRef.current.add(callback);
    return () => {
      subscribersRef.current.delete(callback);
    };
  }, []);

  // Notify all subscribers
  const notifySubscribers = useCallback((current: Record<string, ProgressResponse>, previous: Record<string, ProgressResponse>) => {
    subscribersRef.current.forEach(callback => {
      try {
        callback(current, previous);
      } catch (err) {
        console.error('Error in progress subscriber:', err);
      }
    });
  }, []);

  const fetchAllJobsWithLongPolling = useCallback(async () => {
    try {
      const data = await apiService.getProgress(undefined, true, 30);
      
      if (!isMountedRef.current) return;

      const currentProgress = data.jobs || { [data.status || 'unknown']: data };
      
      // Update state
      setProgress(currentProgress);
      setLoading(false);
      
      // Notify subscribers
      notifySubscribers(currentProgress, previousProgressRef.current);
      
      previousProgressRef.current = currentProgress;
      
      // Continue long polling
      if (isMountedRef.current) {
        fetchAllJobsWithLongPolling();
      }
    } catch (err: any) {
      if (!isMountedRef.current) return;
      
      if (err.code === 'ECONNABORTED' || err.message?.includes('timeout') || err.response?.status === 408) {
        // Timeout is expected - get current state and continue
        try {
          const data = await apiService.getProgress(undefined, false);
          if (isMountedRef.current) {
            const currentProgress = data.jobs || { [data.status || 'unknown']: data };
            
            setProgress(currentProgress);
            setLoading(false);
            
            notifySubscribers(currentProgress, previousProgressRef.current);
            
            previousProgressRef.current = currentProgress;
            fetchAllJobsWithLongPolling();
          }
        } catch (refreshErr: any) {
          if (isMountedRef.current) {
            setTimeout(() => {
              fetchAllJobsWithLongPolling();
            }, 2000);
          }
        }
      } else {
        // Other errors - retry after delay
        if (isMountedRef.current) {
          setTimeout(() => {
            fetchAllJobsWithLongPolling();
          }, 5000);
        }
      }
    }
  }, [notifySubscribers]);

  useEffect(() => {
    isMountedRef.current = true;

    // First, get current state immediately (no waiting)
    const fetchInitialState = async () => {
      try {
        const data = await apiService.getProgress(undefined, false);
        if (isMountedRef.current) {
          const currentProgress: Record<string, ProgressResponse> = data.jobs || { [data.status || 'unknown']: data };
          
          setProgress(currentProgress);
          previousProgressRef.current = currentProgress;
          setLoading(false);
          // Now start long polling for updates
          fetchAllJobsWithLongPolling();
        }
      } catch (err: any) {
        if (isMountedRef.current) {
          setLoading(false);
          // Retry after delay
          setTimeout(() => {
            if (isMountedRef.current) {
              fetchInitialState();
            }
          }, 2000);
        }
      }
    };

    fetchInitialState();

    return () => {
      isMountedRef.current = false;
    };
  }, [fetchAllJobsWithLongPolling]);

  // Expose subscribe function via context value
  const contextValue = React.useMemo(() => ({
    progress,
    loading,
    subscribe,
  }), [progress, loading, subscribe]);

  return (
    <ProgressContext.Provider value={contextValue}>
      {children}
    </ProgressContext.Provider>
  );
}

export function useProgress() {
  const context = useContext(ProgressContext);
  if (!context) {
    throw new Error('useProgress must be used within ProgressProvider');
  }
  return context;
}

