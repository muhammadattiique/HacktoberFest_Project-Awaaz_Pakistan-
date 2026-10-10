import axios from 'axios';
import { MOCK_ADMIN_COMPLAINTS, MOCK_RATES, MOCK_ANALYTICS } from './demoData';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 35000,
});

// Admin API Key storage
let adminApiKey = sessionStorage.getItem('awaaz_admin_key') || '';

export const setAdminApiKey = (key) => {
  adminApiKey = key;
  if (key) {
    sessionStorage.setItem('awaaz_admin_key', key);
  } else {
    sessionStorage.removeItem('awaaz_admin_key');
  }
};

export const getAdminApiKey = () => {
  return adminApiKey || sessionStorage.getItem('awaaz_admin_key') || '';
};

// Request interceptor to attach X-API-Key
apiClient.interceptors.request.use((config) => {
  const key = getAdminApiKey();
  if (key) {
    config.headers['X-API-Key'] = key;
  }
  return config;
});

// Health check to determine if backend is online
export const checkBackendHealth = async () => {
  try {
    const res = await apiClient.get('/', { timeout: 3000 });
    return { online: true, data: res.data };
  } catch (err) {
    return { online: false, error: err.message };
  }
};

/**
 * Submit voice complaint
 */
export const submitVoiceComplaint = async ({
  audioBlob,
  locationArea,
  shopName,
  lat,
  lng,
  signal,
}) => {
  const formData = new FormData();
  const filename = audioBlob.type.includes('mp4') || audioBlob.type.includes('m4a')
    ? 'recording.m4a'
    : audioBlob.type.includes('wav')
    ? 'recording.wav'
    : 'recording.webm';

  formData.append('audio', audioBlob, filename);
  if (locationArea) formData.append('location_area', locationArea);
  if (shopName) formData.append('shop_name', shopName);
  if (lat !== undefined && lat !== null) formData.append('lat', lat.toString());
  if (lng !== undefined && lng !== null) formData.append('lng', lng.toString());

  // Try primary endpoint first: /api/complaints/voice, fallback to /api/process-complaint
  let res;
  try {
    res = await apiClient.post('/api/complaints/voice', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      signal,
    });
  } catch (primaryErr) {
    if (primaryErr?.response?.status === 404) {
      res = await apiClient.post('/api/process-complaint', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        signal,
      });
    } else {
      throw primaryErr;
    }
  }

  return { success: true, data: res.data, isDemo: false };
};

/**
 * Submit text complaint
 */
export const submitTextComplaint = async ({
  text,
  locationArea,
  shopName,
  lat,
  lng,
  signal,
}) => {
  const payload = {
    transcript_text: text,
    location_area: locationArea || null,
    shop_name: shopName || null,
    lat: lat ?? null,
    lng: lng ?? null,
  };

  const res = await apiClient.post('/api/complaints/text', payload, { signal });
  return { success: true, data: res.data, isDemo: false };
};

/**
 * Get complaints list (for recent complaints ticker and list)
 */
export const getComplaints = async (params = {}) => {
  try {
    const res = await apiClient.get('/api/complaints', { params });
    return { success: true, data: res.data, isDemo: false };
  } catch (err) {
    console.warn('Error fetching complaints from API, falling back to mock:', err);
    let filtered = [...MOCK_ADMIN_COMPLAINTS];
    if (params.category) filtered = filtered.filter(c => c.category === params.category);
    if (params.urgency) filtered = filtered.filter(c => c.urgency === params.urgency);
    if (params.status) filtered = filtered.filter(c => c.status === params.status);
    if (params.search) {
      const q = params.search.toLowerCase();
      filtered = filtered.filter(c =>
        c.transcript_raw.toLowerCase().includes(q) ||
        (c.item_name && c.item_name.toLowerCase().includes(q)) ||
        (c.shop_name && c.shop_name.toLowerCase().includes(q))
      );
    }
    return {
      success: true,
      data: {
        total: filtered.length,
        items: filtered,
        page: 1,
        limit: 50,
      },
      isDemo: true,
    };
  }
};

/**
 * Get single complaint by ID
 */
export const getComplaintById = async (id) => {
  try {
    const res = await apiClient.get(`/api/complaints/${id}`);
    return { success: true, data: res.data, isDemo: false };
  } catch (err) {
    const found = MOCK_ADMIN_COMPLAINTS.find(c => c.id === id);
    if (found) {
      return { success: true, data: found, isDemo: true };
    }
    throw err;
  }
};

/**
 * Update complaint status & notes (for Admin)
 * @param {string} id
 * @param {object} payload
 * @param {string} [payload.status]      Pending | Investigating | Resolved | Rejected
 * @param {string} [payload.adminNotes]  Free-text magistrate notes
 * @param {string} [payload.assignedAuthority] Enforcement body the case is routed to
 */
export const updateComplaintStatus = async (id, { status, adminNotes, assignedAuthority }) => {
  const body = { status };
  if (adminNotes !== undefined) body.admin_notes = adminNotes;
  if (assignedAuthority !== undefined) body.assigned_authority = assignedAuthority;

  try {
    const res = await apiClient.patch(`/api/complaints/${id}`, body);
    return { success: true, data: res.data, isDemo: false };
  } catch (err) {
    if (!err.response || err.code === 'ERR_NETWORK') {
      // Offline fallback: update local mock array
      const idx = MOCK_ADMIN_COMPLAINTS.findIndex(c => c.id === id);
      if (idx !== -1) {
        MOCK_ADMIN_COMPLAINTS[idx].status = status;
        if (adminNotes !== undefined) MOCK_ADMIN_COMPLAINTS[idx].admin_notes = adminNotes;
        if (assignedAuthority !== undefined) {
          MOCK_ADMIN_COMPLAINTS[idx].routing_agency = assignedAuthority;
        }
        return { success: true, data: MOCK_ADMIN_COMPLAINTS[idx], isDemo: true };
      }
    }
    throw err;
  }
};

/**
 * Fetch the aggregated enforcement dossier for a single vendor.
 * Requires the administrative API key.
 */
export const getShopProfile = async (shopName) => {
  const res = await apiClient.get(
    `/api/admin/shops/${encodeURIComponent(shopName)}`
  );
  return { success: true, data: res.data, isDemo: false };
};

/**
 * Trigger the server-side CSV export and download it in the browser.
 * Falls back to the client-side generator when the backend is offline.
 */
export const downloadComplaintsCsv = async ({ category = '', status = '' } = {}) => {
  const params = {};
  if (category) params.category = category;
  if (status) params.status = status;

  try {
    const res = await apiClient.get('/api/admin/export', {
      params,
      responseType: 'blob',
      timeout: 60000,
    });

    const disposition = res.headers['content-disposition'] || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : 'awaaz_complaints.csv';

    const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);

    const count = Number(res.headers['x-record-count'] || 0);
    return { success: true, count, serverSide: true };
  } catch (err) {
    console.warn('Server-side CSV export unavailable, using client-side export:', err);
    return { success: false, serverSide: false, error: err };
  }
};

/**
 * Get Official Notified Rates
 */
export const getRates = async (params = {}) => {
  try {
    const res = await apiClient.get('/api/rates', { params });
    return { success: true, data: res.data, isDemo: false };
  } catch (err) {
    console.warn('Rates API unavailable, using offline notified list:', err);
    let items = [...MOCK_RATES];
    if (params.category) {
      items = items.filter(r => r.category.toLowerCase() === params.category.toLowerCase());
    }
    if (params.search) {
      const q = params.search.toLowerCase();
      items = items.filter(r =>
        r.name_en.toLowerCase().includes(q) ||
        r.name_ur.includes(q)
      );
    }
    return {
      success: true,
      data: {
        meta: { region: "Islamabad & Rawalpindi", date: "Daily Notified" },
        items,
        total_items: items.length,
      },
      isDemo: true,
    };
  }
};

/**
 * Get Impact Stats & Analytics
 */
export const getAnalyticsOverview = async () => {
  try {
    // Try /api/analytics/overview first, then /api/stats
    let res;
    try {
      res = await apiClient.get('/api/analytics/overview');
    } catch {
      res = await apiClient.get('/api/stats');
    }
    return { success: true, data: res.data, isDemo: false };
  } catch {
    return { success: true, data: MOCK_ANALYTICS, isDemo: true };
  }
};

/**
 * Get Hotspot Areas
 */
export const getHotspots = async () => {
  try {
    const res = await apiClient.get('/api/analytics/hotspots');
    return { success: true, data: res.data, isDemo: false };
  } catch {
    return { success: true, data: MOCK_ANALYTICS.hotspots, isDemo: true };
  }
};

/**
 * Get Repeat Offenders
 */
export const getRepeatOffenders = async () => {
  try {
    const res = await apiClient.get('/api/analytics/repeat-offenders');
    return { success: true, data: res.data, isDemo: false };
  } catch {
    return { success: true, data: MOCK_ANALYTICS.repeat_offenders, isDemo: true };
  }
};

