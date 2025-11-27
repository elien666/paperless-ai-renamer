import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.DEV ? '/api' : '/api', // Use /api prefix for all requests
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface ProgressResponse {
  status?: string;
  total?: number;
  processed?: number;
  indexed?: number;
  skipped_scan?: number;
  cleaned?: number;
  created_at?: string;
  completed_at?: string;
  newer_than?: string;
  older_than?: string;
  error?: string;
  errors?: Array<{ document_id: number; error: string }>;
  jobs?: Record<string, ProgressResponse>;
}

export interface ArchiveResponse {
  items: any[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

export interface OutlierResponse {
  status: string;
  count: number;
  outliers: Array<{
    document_id: string;
    title: string;
    outlier_score: number;
    avg_distance_to_neighbors: number;
  }>;
}

export const apiService = {
  // Health check
  async getHealth() {
    const response = await api.get('/health');
    return response.data;
  },

  // Progress tracking
  async getProgress(jobId?: string, wait: boolean = false, timeout: number = 60): Promise<ProgressResponse> {
    const params: any = {};
    if (jobId) params.job_id = jobId;
    if (wait) {
      params.wait = 'true';
      params.timeout = timeout.toString();
    }
    const response = await api.get('/progress', { 
      params,
      timeout: wait ? (timeout + 5) * 1000 : undefined, // Add 5s buffer for network overhead
    });
    return response.data;
  },

  // Trigger scan
  async triggerScan(newerThan?: string) {
    const params = newerThan ? { newer_than: newerThan } : {};
    const response = await api.post('/scan', null, { params });
    return response.data;
  },

  // Trigger index
  async triggerIndex(olderThan?: string) {
    const params = olderThan ? { older_than: olderThan } : {};
    const response = await api.post('/index', null, { params });
    return response.data;
  },

  // Process specific document
  async processDocument(documentId: number) {
    const response = await api.post('/process-documents', {
      document_ids: [documentId],
    });
    return response.data;
  },

  // Get archive
  async getArchive(
    type: 'index' | 'scan' | 'rename' | 'webhook' | 'error',
    page: number = 1,
    limit: number = 50,
    startDate?: string,
    endDate?: string
  ): Promise<ArchiveResponse> {
    const params: any = { type, page, limit };
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    const response = await api.get('/archive', { params });
    return response.data;
  },

  // Clear error archive
  async clearErrorArchive(): Promise<{ status: string; deleted_count: number }> {
    const response = await api.delete('/archive', { params: { type: 'error' } });
    return response.data;
  },

  // Find outliers
  async findOutliers(kNeighbors: number = 5, limit: number = 50): Promise<OutlierResponse> {
    const response = await api.get('/find-outliers', {
      params: { k_neighbors: kNeighbors, limit },
    });
    return response.data;
  },
};

