import { useAuthStore } from '@/stores/auth';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

class ApiClient {
  private async requestWithRetry(url: string, init: RequestInit, tries = 2): Promise<Response> {
    try {
      const res = await fetch(url, init);
      if (res.status === 401 && tries > 1) {
        // small delay to allow HydrateAuth to refresh token
        await new Promise(r => setTimeout(r, 150));
        return this.requestWithRetry(url, init, tries - 1);
      }
      return res;
    } catch (e) {
      if ((e as DOMException).name === 'AbortError') throw e;
      if (tries > 1) {
        await new Promise(r => setTimeout(r, 150));
        return this.requestWithRetry(url, init, tries - 1);
      }
      throw e;
    }
  }

  private getHeaders() {
    const token = useAuthStore.getState().token;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    
    return headers;
  }

  private async handleResponse(response: Response) {
    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Network error' }));
      const correlationId = response.headers.get('X-Request-ID');
      
      throw {
        message: error.message || 'Request failed',
        status: response.status,
        correlationId,
      };
    }
    if (response.status === 204) {
      return null;
    }

    return response.json();
  }

  async get(endpoint: string) {
    const response = await this.requestWithRetry(`${API_BASE_URL}${endpoint}`, {
      method: 'GET',
      headers: this.getHeaders(),
    });
    
    return this.handleResponse(response);
  }

  async post<T>(endpoint: string, data: T, init: RequestInit = {}) {
    const response = await this.requestWithRetry(`${API_BASE_URL}${endpoint}`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(data),
      ...init,
    });

    return this.handleResponse(response);
  }

  async put<T>(endpoint: string, data: T) {
    const response = await this.requestWithRetry(`${API_BASE_URL}${endpoint}`, {
      method: 'PUT',
      headers: this.getHeaders(),
      body: JSON.stringify(data),
    });

    return this.handleResponse(response);
  }

  async patch<T>(endpoint: string, data: T) {
    const response = await this.requestWithRetry(`${API_BASE_URL}${endpoint}`, {
      method: 'PATCH',
      headers: this.getHeaders(),
      body: JSON.stringify(data),
    });
    
    return this.handleResponse(response);
  }

  async delete(endpoint: string) {
    const response = await this.requestWithRetry(`${API_BASE_URL}${endpoint}`, {
      method: 'DELETE',
      headers: this.getHeaders(),
    });
    
    return this.handleResponse(response);
  }

  async upload(endpoint: string, formData: FormData) {
    const token = useAuthStore.getState().token;
    const headers: Record<string, string> = {};
    
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    
    const response = await this.requestWithRetry(`${API_BASE_URL}${endpoint}`, {
      method: 'POST',
      headers,
      body: formData,
    });
    
    return this.handleResponse(response);
  }
}

export const apiClient = new ApiClient();

// Health check endpoints
export const healthApi = {
  checkHealth: () => apiClient.get('/api/health'),
  checkReady: () => apiClient.get('/api/ready'),
  getMetrics: () => apiClient.get('/api/metrics'),
};

// Admin APIs
export const adminApi = {
  // Collections
  getCollections: () => apiClient.get('/api/admin/collections'),
  createCollection: (data: { name: string; description?: string }) =>
    apiClient.post('/api/admin/collections', data),
  updateCollection: (id: string, data: { name?: string; description?: string }) =>
    apiClient.patch(`/api/admin/collections/${id}`, data),
  deleteCollection: (id: string) => apiClient.delete(`/api/admin/collections/${id}`),

  // Documents
  getDocuments: (collectionId: string) =>
    apiClient.get(`/api/admin/collections/${collectionId}/documents`),
  listAllDocuments: () => apiClient.get(`/api/admin/documents`),
  getCollectionStats: (collectionId: string) =>
    apiClient.get(`/api/admin/collections/${collectionId}/stats`),
  uploadDocument: (collectionId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.upload(`/api/admin/collections/${collectionId}/documents`, formData);
  },
  linkDocument: (
    collectionId: string,
    payload: { document_id?: string; sha256?: string }
  ) => apiClient.post(`/api/admin/collections/${collectionId}/documents/link`, payload),
  updateDocument: (
    documentId: string,
    data: { title?: string; meta?: Record<string, unknown> }
  ) => apiClient.patch(`/api/admin/documents/${documentId}`, data),
  reindexDocument: (collectionId: string, documentId: string) =>
    apiClient.post(
      `/api/admin/collections/${collectionId}/documents/${documentId}/reindex`,
      {}
    ),
  unlinkDocument: (collectionId: string, documentId: string) =>
    apiClient.delete(`/api/admin/collections/${collectionId}/documents/${documentId}`),
  purgeDocument: (documentId: string) =>
    apiClient.delete(`/api/admin/documents/${documentId}/purge`),
  getDocumentStatus: (documentId: string) =>
    apiClient.get(`/api/admin/documents/${documentId}/status`),

  // Users
  getUsers: () => apiClient.get('/api/admin/users'),
  createUser: (data: { email: string; name: string; role: string; password: string; active: boolean }) =>
    apiClient.post('/api/admin/users', data),
  updateUser: (
    id: string,
    data: { email?: string; name?: string; active?: boolean; password?: string }
  ) => apiClient.patch(`/api/admin/users/${id}`, data),
  updateUserRole: (id: string, role: string) =>
    apiClient.patch(`/api/admin/users/${id}/role`, { role }),
  deleteUser: (id: string) => apiClient.delete(`/api/admin/users/${id}`),
  getUserCollections: (id: string) =>
    apiClient.get(`/api/admin/users/${id}/collections`),
  assignCollections: (userId: string, collectionIds: string[]) =>
    apiClient.put(`/api/admin/users/${userId}/collections`, { assigned: collectionIds }),
  getUserPrefs: (id: string) =>
    apiClient.get(`/api/admin/users/${id}/prefs`),
  updateUserPrefs: (
    id: string,
    data: { temperature?: number; top_k?: number; mmr_lambda?: number }
  ) => apiClient.patch(`/api/admin/users/${id}/prefs`, data),
};

// Auth APIs
export const authApi = {
  login: (data: { email: string; password: string }) =>
    apiClient.post('/api/auth/login', data),
  logout: () => apiClient.post('/api/auth/logout', {}),
  me: () => apiClient.get('/api/auth/me'),
  changePassword: (data: { old_password: string; new_password: string }) =>
    apiClient.post('/api/auth/password', data),
};

// Current user endpoints
export const meApi = {
  listCollections: () => apiClient.get('/api/me/collections'),
  listCollectionDocs: (collectionId: string) =>
    apiClient.get(`/api/me/collections/${collectionId}/documents`),
};

// Chat APIs
export const chatApi = {
  listSessions: () => apiClient.get('/api/chat/sessions'),
  createSession: () => apiClient.post('/api/chat/sessions', {}),
  renameSession: (id: string, data: { session_title: string }) =>
    apiClient.patch(`/api/chat/sessions/${id}`, data),
  deleteSession: (id: string) => apiClient.delete(`/api/chat/sessions/${id}`),
  getHistory: (id: string) => apiClient.get(`/api/chat/sessions/${id}/history`),
  ask: (
    data: {
      question: string;
      session_id: string;
      top_k: number;
      temperature: number;
      mmr_lambda: number;
    },
    init?: RequestInit,
  ) => apiClient.post('/api/ask', data, init),
  sendFeedback: (queryId: string, feedback: 'up' | 'down') =>
    apiClient.post(`/api/queries/${queryId}/feedback`, { feedback }),
};