import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useLanguage } from '../i18n/LanguageContext';
import {
  getAdminApiKey,
  setAdminApiKey,
  getComplaints,
  updateComplaintStatus,
  downloadComplaintsCsv,
  getHotspots,
  getRepeatOffenders,
} from '../lib/api';
import { MOCK_ADMIN_COMPLAINTS } from '../lib/demoData';
import { AdminMap } from '../components/map/AdminMap';
import { MiniLocationMap } from '../components/map/MiniLocationMap';
import {
  formatPrice,
  formatVariance,
  formatTimeAgo,
  getSeverityStyle,
  getStatusStyle,
  exportToCsv,
} from '../lib/utils';
import {
  ShieldAlert,
  Key,
  Unlock,
  LogOut,
  MapPin,
  List,
  Map as MapIcon,
  Download,
  Search,
  Copy,
  Check,
  Store,
  Save,
  X,
  Flame,
} from 'lucide-react';

export const Admin = () => {
  const { t, language } = useLanguage();

  // Authentication State
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [isAuthorized, setIsAuthorized] = useState(() => Boolean(getAdminApiKey()));
  const [authError, setAuthError] = useState('');

  // Live Incident Feed
  const [complaints, setComplaints] = useState([]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [newComplaintIds, setNewComplaintIds] = useState(new Set());

  // View Mode: 'map' or 'list'
  const [viewMode, setViewMode] = useState('map');

  // Selected Complaint for Detail Drawer
  const [selectedComplaint, setSelectedComplaint] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [copiedField, setCopiedField] = useState(null);

  // Status & Notes editing form
  const [editingStatus, setEditingStatus] = useState('');
  const [editingAuthority, setEditingAuthority] = useState('');
  const [editingNotes, setEditingNotes] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Filters
  const [filterSeverity, setFilterSeverity] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterAuthority, setFilterAuthority] = useState('');
  const [searchShop, setSearchShop] = useState('');

  // Side Panel tabs / Hotspots
  const [hotspots, setHotspots] = useState([]);
  const [repeatOffenders, setRepeatOffenders] = useState([]);

  const prevComplaintsCountRef = useRef(0);

  // Handle Key Submission
  const handleAuthorize = (e) => {
    e?.preventDefault();
    const cleanKey = apiKeyInput.trim();
    if (!cleanKey) {
      setAuthError('Please enter an administrative API Key.');
      return;
    }

    setAdminApiKey(cleanKey);
    setIsAuthorized(true);
    setAuthError('');
  };

  const handleLogout = () => {
    setAdminApiKey('');
    setIsAuthorized(false);
    setSelectedComplaint(null);
    setDrawerOpen(false);
  };

  // Fetch Complaints & Analytics
  const loadAdminData = async (isBackground = false) => {
    if (!isAuthorized) return;
    if (isBackground) setIsRefreshing(true);

    try {
      const [compRes, hotRes, offRes] = await Promise.allSettled([
        getComplaints({ limit: 100 }),
        getHotspots(),
        getRepeatOffenders(),
      ]);

      if (compRes.status === 'fulfilled') {
        const fetched = compRes.value.data?.items || MOCK_ADMIN_COMPLAINTS;
        setIsDemoMode(Boolean(compRes.value.isDemo));

        // Detect new incoming complaints for highlight pulse
        if (prevComplaintsCountRef.current > 0 && fetched.length > prevComplaintsCountRef.current) {
          const newSet = new Set();
          fetched.slice(0, fetched.length - prevComplaintsCountRef.current).forEach((c) => {
            newSet.add(c.id);
          });
          setNewComplaintIds(newSet);
          setTimeout(() => setNewComplaintIds(new Set()), 6000);
        }
        prevComplaintsCountRef.current = fetched.length;

        setComplaints(fetched);
      }

      if (hotRes.status === 'fulfilled' && hotRes.value.data) {
        setHotspots(hotRes.value.data);
      }
      if (offRes.status === 'fulfilled' && offRes.value.data) {
        setRepeatOffenders(offRes.value.data);
      }
    } catch (err) {
      console.warn('Admin load error:', err);
      if (err.response?.status === 401 || err.response?.status === 403) {
        setAuthError(t.admin.keyInvalid);
        setIsAuthorized(false);
      }
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    if (isAuthorized) {
      loadAdminData();
      const pollInterval = setInterval(() => loadAdminData(true), 10000);
      return () => clearInterval(pollInterval);
    }
  }, [isAuthorized]);

  const handleSelectComplaint = (complaint) => {
    setSelectedComplaint(complaint);
    setEditingStatus(complaint.status || 'Pending');
    setEditingAuthority(complaint.routing_agency || 'PERA - Price Enforcement');
    setEditingNotes(complaint.admin_notes || '');
    setSaveSuccess(false);
    setDrawerOpen(true);
  };

  const handleSaveResolution = async () => {
    if (!selectedComplaint) return;
    setIsSaving(true);
    setSaveSuccess(false);

    // Capture the previous values so an API failure can be rolled back.
    const oldStatus = selectedComplaint.status;
    const oldNotes = selectedComplaint.admin_notes;
    const oldAuthority = selectedComplaint.routing_agency;

    const updatedComplaint = {
      ...selectedComplaint,
      status: editingStatus,
      admin_notes: editingNotes,
      routing_agency: editingAuthority,
    };
    setSelectedComplaint(updatedComplaint);
    setComplaints((prev) =>
      prev.map((c) => (c.id === selectedComplaint.id ? updatedComplaint : c))
    );

    try {
      await updateComplaintStatus(selectedComplaint.id, {
        status: editingStatus,
        adminNotes: editingNotes,
        assignedAuthority: editingAuthority,
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    } catch (err) {
      console.error('Resolution update failed, rolling back:', err);
      const rolledBack = {
        ...selectedComplaint,
        status: oldStatus,
        admin_notes: oldNotes,
        routing_agency: oldAuthority,
      };
      setSelectedComplaint(rolledBack);
      setComplaints((prev) =>
        prev.map((c) => (c.id === selectedComplaint.id ? rolledBack : c))
      );
      // Surface the server's message when available (e.g. 401/403 key problems).
      const serverMsg = err?.response?.data?.detail;
      alert(
        serverMsg
          ? `Failed to update resolution: ${serverMsg}`
          : 'Failed to update resolution on server. Please check your API key and connection.'
      );
    } finally {
      setIsSaving(false);
    }
  };

  /**
   * Export grievances to CSV.
   * Prefers the authenticated server-side export (full dataset, Excel-safe BOM)
   * and falls back to generating the file in the browser from the currently
   * loaded rows when the backend is unreachable or running in demo mode.
   */
  const handleExportCsv = async () => {
    if (!filteredComplaints.length) return;

    if (!isDemoMode) {
      try {
        // Only `status` maps to a server-side filter; the remaining filters are
        // applied client-side, so the full authorized dataset is exported and
        // the user can narrow it further in Excel if needed.
        const result = await downloadComplaintsCsv({ status: filterStatus });
        if (result.success) return;
      } catch (err) {
        console.warn('Server CSV export failed, using client-side export:', err);
      }
    }

    exportToCsv('awaaz_incident_export', filteredComplaints);
  };

  const handleCopy = (text, field) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const filteredComplaints = useMemo(() => {
    return complaints.filter((c) => {
      if (filterSeverity && (c.severity || c.urgency)?.toLowerCase() !== filterSeverity.toLowerCase()) {
        return false;
      }
      if (filterStatus && c.status?.toLowerCase() !== filterStatus.toLowerCase()) {
        return false;
      }
      if (filterAuthority && !c.routing_agency?.toLowerCase().includes(filterAuthority.toLowerCase())) {
        return false;
      }
      if (searchShop) {
        const q = searchShop.toLowerCase();
        const inShop = c.shop_name?.toLowerCase().includes(q);
        const inArea = c.location_area?.toLowerCase().includes(q);
        const inTranscript = c.transcript_raw?.toLowerCase().includes(q);
        if (!inShop && !inArea && !inTranscript) return false;
      }
      return true;
    });
  }, [complaints, filterSeverity, filterStatus, filterAuthority, searchShop]);

  const unlocatedComplaints = useMemo(() => {
    return complaints.filter((c) => !c.lat || !c.lng);
  }, [complaints]);

  const shopHistory = useMemo(() => {
    if (!selectedComplaint?.shop_name) return [];
    return complaints.filter(
      (c) =>
        c.shop_name?.toLowerCase() === selectedComplaint.shop_name.toLowerCase() &&
        c.id !== selectedComplaint.id
    );
  }, [selectedComplaint, complaints]);

  if (!isAuthorized) {
    return (
      <div className="min-h-screen bg-[#030014] text-white flex items-center justify-center p-4">
        <div className="pointer-events-none absolute w-[500px] h-[350px] bg-rose-900/15 rounded-full blur-[140px]" />

        <div className="relative z-10 w-full max-w-md p-8 rounded-3xl bg-[#0c0c0c]/90 border border-white/10 backdrop-blur-2xl shadow-[0_20px_50px_rgba(0,0,0,0.9)] text-center">
          <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-400 mx-auto mb-6 shadow-[0_0_25px_rgba(229,72,77,0.3)]">
            <ShieldAlert className="w-7 h-7" />
          </div>

          <h2 className="text-2xl font-extrabold text-white mb-2">
            {t.admin.gateTitle}
          </h2>
          <p className="text-xs text-white/60 mb-6 leading-relaxed">
            {t.admin.gateSub}
          </p>

          <form onSubmit={handleAuthorize} className="space-y-4">
            <div className="relative">
              <Key className="absolute left-3.5 top-3 w-4 h-4 text-white/40" />
              <input
                type="password"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder={t.admin.keyPlaceholder}
                className="w-full bg-[#131515] border border-white/10 rounded-xl pl-10 pr-4 py-3 text-xs text-white placeholder-white/40 focus:outline-none focus:border-rose-500 font-mono"
              />
            </div>

            {authError && (
              <p className="text-xs text-rose-400 font-medium text-left">
                {authError}
              </p>
            )}

            <button
              type="submit"
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-gradient-to-r from-rose-600 to-rose-700 hover:from-rose-500 hover:to-rose-600 text-white font-semibold text-xs shadow-[0_0_20px_rgba(229,72,77,0.4)] transition-all cursor-pointer"
            >
              <Unlock className="w-3.5 h-3.5" />
              <span>{t.admin.unlockButton}</span>
            </button>
          </form>

          <div className="mt-6 pt-4 border-t border-white/[0.08] text-[11px] text-white/40">
            Default Demo Key: <code className="text-rose-300 font-mono">awaaz-admin-2024</code>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#030014] text-white flex flex-col overflow-hidden">
      <header className="border-b border-white/[0.08] bg-[#080808]/90 backdrop-blur-xl px-4 sm:px-6 py-3 flex items-center justify-between gap-4 z-40">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400">
            <ShieldAlert className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-extrabold text-sm sm:text-base text-white tracking-tight">
                Awaaz District Command
              </h1>
              <span className="px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/30 text-[10px] font-mono font-bold uppercase">
                Magistrate Live
              </span>
            </div>
            {isDemoMode && (
              <span className="text-[10px] text-amber-400 block -mt-0.5">
                • {t.admin.demoNotice}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          <div className="flex items-center p-1 rounded-xl bg-white/[0.04] border border-white/10">
            <button
              onClick={() => setViewMode('map')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                viewMode === 'map'
                  ? 'bg-rose-600 text-white shadow-[0_0_12px_rgba(229,72,77,0.5)]'
                  : 'text-white/60 hover:text-white'
              }`}
            >
              <MapIcon className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{t.admin.mapView}</span>
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                viewMode === 'list'
                  ? 'bg-rose-600 text-white shadow-[0_0_12px_rgba(229,72,77,0.5)]'
                  : 'text-white/60 hover:text-white'
              }`}
            >
              <List className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{t.admin.listView}</span>
            </button>
          </div>

          <button
            onClick={handleExportCsv}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/[0.05] hover:bg-white/[0.1] border border-white/10 text-white text-xs font-medium transition-colors cursor-pointer"
            title="Export filtered grievances to CSV"
          >
            <Download className="w-3.5 h-3.5 text-violet-400" />
            <span className="hidden md:inline">{t.admin.exportCsv}</span>
          </button>

          <button
            onClick={handleLogout}
            className="p-2 rounded-xl bg-white/[0.05] hover:bg-rose-500/20 text-white/60 hover:text-rose-400 border border-white/10 transition-colors cursor-pointer"
            title="Lock Portal"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </header>

      <div className="border-b border-white/[0.06] bg-[#0c0c0c]/80 backdrop-blur-md px-4 sm:px-6 py-2.5 flex flex-wrap items-center justify-between gap-3 text-xs z-30">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative w-48 sm:w-56">
            <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-white/40" />
            <input
              type="text"
              value={searchShop}
              onChange={(e) => setSearchShop(e.target.value)}
              placeholder={t.admin.searchShop}
              className="w-full bg-[#131515] border border-white/10 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-white/40 focus:outline-none focus:border-rose-500"
            />
          </div>

          <select
            value={filterSeverity}
            onChange={(e) => setFilterSeverity(e.target.value)}
            className="bg-[#131515] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-rose-500"
          >
            <option value="">{t.admin.filterSeverity}: {t.admin.all}</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="normal">Normal</option>
          </select>

          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="bg-[#131515] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-rose-500"
          >
            <option value="">{t.admin.filterStatus}: {t.admin.all}</option>
            <option value="Pending">Pending</option>
            <option value="Investigating">Investigating</option>
            <option value="Resolved">Resolved</option>
            <option value="Rejected">Rejected</option>
          </select>

          <select
            value={filterAuthority}
            onChange={(e) => setFilterAuthority(e.target.value)}
            className="bg-[#131515] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-rose-500"
          >
            <option value="">{t.admin.filterAuthority}: {t.admin.all}</option>
            <option value="PERA">PERA (Price Enforcement)</option>
            <option value="PFA">PFA (Food Safety)</option>
            <option value="District">ICT / DC Office</option>
          </select>
        </div>

        <div className="flex items-center gap-2 text-white/50 text-xs">
          <span>Showing <strong className="text-white">{filteredComplaints.length}</strong> incidents</span>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden relative">
        <div className="flex-1 relative flex flex-col p-4 overflow-hidden">
          {viewMode === 'map' ? (
            <AdminMap
              complaints={filteredComplaints}
              selectedComplaint={selectedComplaint}
              onSelectComplaint={handleSelectComplaint}
              onRefresh={() => loadAdminData(true)}
              isRefreshing={isRefreshing}
              newComplaintIds={newComplaintIds}
            />
          ) : (
            <div className="flex-1 overflow-y-auto rounded-3xl border border-white/10 bg-[#0c0c0c]/80 p-4 sm:p-6 backdrop-blur-xl">
              <div className="space-y-3">
                {filteredComplaints.map((c) => {
                  const isViolation = c.percentage_overcharge > 0 || c.is_violation;
                  const sevStyle = getSeverityStyle(c.severity || c.urgency, isViolation);
                  const statusClass = getStatusStyle(c.status);

                  return (
                    <div
                      key={c.id}
                      onClick={() => handleSelectComplaint(c)}
                      className="p-4 rounded-2xl bg-white/[0.02] hover:bg-white/[0.05] border border-white/[0.08] transition-all cursor-pointer flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
                    >
                      <div className="flex items-start gap-3">
                        <span className="w-3 h-3 rounded-full bg-[#e5484d] mt-1 shrink-0 shadow-[0_0_8px_#e5484d]" />
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-bold text-white text-sm">
                              {c.item_name || 'Price Grievance'}
                            </span>
                            <span className="font-mono text-rose-300 font-semibold text-xs">
                              {formatPrice(c.reported_price, language)} vs {formatPrice(c.official_price, language)}
                            </span>
                            <span className="font-mono text-[10px] font-bold text-rose-400 bg-rose-500/20 px-1.5 py-0.5 rounded">
                              {formatVariance(c.percentage_overcharge)}
                            </span>
                          </div>
                          <p className="text-xs text-white/70">
                            {c.shop_name ? `${c.shop_name} • ` : ''}{c.location_area || 'Rawalpindi / Islamabad'}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-semibold border ${sevStyle.bg}`}>
                          {c.urgency || c.severity || 'Normal'}
                        </span>
                        <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-semibold border ${statusClass}`}>
                          {c.status || 'Pending'}
                        </span>
                        <span className="text-[11px] text-white/40 font-mono">
                          {formatTimeAgo(c.created_at, language)}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <aside className="w-80 lg:w-96 border-l border-white/[0.08] bg-[#080808]/90 backdrop-blur-xl p-4 overflow-y-auto hidden md:flex flex-col gap-6">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Flame className="w-4 h-4 text-rose-400" />
              <h3 className="font-bold text-xs uppercase tracking-wider text-white">
                {t.admin.hotspotsHeading}
              </h3>
            </div>
            <div className="space-y-2">
              {hotspots.slice(0, 4).map((h, i) => (
                <div
                  key={i}
                  className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-white/15 transition-all text-xs"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-white truncate max-w-[170px]">
                      {h.area}
                    </span>
                    <span className="font-mono font-bold text-rose-400 text-[11px]">
                      {formatVariance(h.avg_overcharge_pct)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-white/40">
                    <span>{h.top_violated_item}</span>
                    <span>{h.complaint_count} incidents</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2 mb-3">
              <Store className="w-4 h-4 text-amber-400" />
              <h3 className="font-bold text-xs uppercase tracking-wider text-white">
                {t.admin.repeatOffendersHeading}
              </h3>
            </div>
            <div className="space-y-2">
              {repeatOffenders.slice(0, 3).map((r, i) => (
                <div
                  key={i}
                  onClick={() => setSearchShop(r.shop_name)}
                  className="p-3 rounded-xl bg-amber-500/5 border border-amber-500/20 hover:border-amber-500/40 transition-all text-xs cursor-pointer group"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-amber-200 truncate group-hover:text-amber-100">
                      {r.shop_name}
                    </span>
                    <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 font-mono text-[10px] font-bold">
                      {r.violations_count} strikes
                    </span>
                  </div>
                  <p className="text-[10px] text-white/50 truncate mb-1">
                    {r.area}
                  </p>
                  <div className="flex items-center justify-between text-[10px] text-white/40">
                    <span>Max {formatVariance(r.max_overcharge_pct)}</span>
                    <span className="text-amber-400">{r.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {unlocatedComplaints.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <MapPin className="w-4 h-4 text-white/40" />
                <h3 className="font-bold text-xs uppercase tracking-wider text-white">
                  No-Location Queue ({unlocatedComplaints.length})
                </h3>
              </div>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {unlocatedComplaints.slice(0, 5).map((u) => (
                  <div
                    key={u.id}
                    onClick={() => handleSelectComplaint(u)}
                    className="p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:bg-white/[0.05] transition-all text-xs cursor-pointer"
                  >
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="font-semibold text-white/90 truncate">
                        {u.item_name || 'Price Report'}
                      </span>
                      <span className="text-[10px] text-white/40 font-mono">
                        {formatTimeAgo(u.created_at, language)}
                      </span>
                    </div>
                    <p className="text-[11px] text-white/50 line-clamp-1">
                      "{u.transcript_raw}"
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </aside>

        {drawerOpen && selectedComplaint && (
          <div className="absolute inset-y-0 right-0 w-full sm:w-[480px] lg:w-[540px] bg-[#0c0c0c] border-l border-white/15 shadow-[0_0_60px_rgba(0,0,0,0.9)] z-50 flex flex-col overflow-hidden animate-in slide-in-from-right duration-300">
            <div className="p-5 border-b border-white/10 flex items-center justify-between gap-3 bg-[#131515]">
              <div className="flex items-center gap-2.5">
                <span className="w-3.5 h-3.5 rounded-full bg-[#E5484D] shadow-[0_0_10px_#e5484d]" />
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="font-bold text-sm text-white">
                      Incident Record
                    </h2>
                    <span className="font-mono text-xs text-white/60 bg-white/5 px-2 py-0.5 rounded border border-white/10">
                      {selectedComplaint.id?.slice(0, 10)}...
                    </span>
                    <button
                      onClick={() => handleCopy(selectedComplaint.id, 'id')}
                      className="p-1 text-white/50 hover:text-white"
                      title="Copy ID"
                    >
                      {copiedField === 'id' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                  <span className="text-[11px] text-white/40">
                    Reported {formatTimeAgo(selectedComplaint.created_at, language)} ({new Date(selectedComplaint.created_at).toLocaleTimeString()})
                  </span>
                </div>
              </div>

              <button
                onClick={() => setDrawerOpen(false)}
                className="p-1.5 rounded-full hover:bg-white/10 text-white/60 hover:text-white transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-6 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`px-2.5 py-1 rounded-full text-xs font-semibold border ${getStatusStyle(selectedComplaint.status)}`}>
                  {selectedComplaint.status}
                </span>
                <span className={`px-2.5 py-1 rounded-full text-xs font-semibold border ${getSeverityStyle(selectedComplaint.severity, true).bg}`}>
                  {selectedComplaint.urgency || selectedComplaint.severity} Priority
                </span>
                <span className="px-2.5 py-1 rounded-full bg-white/5 text-white/70 border border-white/10">
                  Lang: {selectedComplaint.detected_language}
                </span>
                {selectedComplaint.needs_review && (
                  <span className="px-2.5 py-1 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30">
                    Flagged for Review
                  </span>
                )}
              </div>

              <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/[0.08] space-y-3">
                <h4 className="font-bold text-xs uppercase tracking-wider text-rose-400">
                  Price Variance Analysis
                </h4>
                <div className="grid grid-cols-2 gap-3 pt-1">
                  <div>
                    <span className="text-white/40 block text-[10px]">Commodity</span>
                    <span className="font-bold text-white text-sm">{selectedComplaint.item_name || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="text-white/40 block text-[10px]">Variance</span>
                    <span className="font-bold font-mono text-rose-400 text-sm">
                      {formatVariance(selectedComplaint.percentage_overcharge)}
                    </span>
                  </div>
                  <div>
                    <span className="text-white/40 block text-[10px]">Reported Rate</span>
                    <span className="font-bold font-mono text-rose-300">
                      {formatPrice(selectedComplaint.reported_price, language)} / {selectedComplaint.unit || 'kg'}
                    </span>
                  </div>
                  <div>
                    <span className="text-white/40 block text-[10px]">Official Ceiling</span>
                    <span className="font-bold font-mono text-emerald-300">
                      {formatPrice(selectedComplaint.official_price, language)} / {selectedComplaint.unit || 'kg'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-xs uppercase tracking-wider text-white/80">
                    Location & Vendor Evidence
                  </h4>
                  {selectedComplaint.lat && selectedComplaint.lng && (
                    <button
                      onClick={() =>
                        handleCopy(`${selectedComplaint.lat},${selectedComplaint.lng}`, 'coords')
                      }
                      className="flex items-center gap-1 text-[11px] text-white/50 hover:text-white"
                    >
                      {copiedField === 'coords' ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                      <span>{selectedComplaint.lat.toFixed(4)}, {selectedComplaint.lng.toFixed(4)}</span>
                    </button>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.05]">
                    <span className="text-white/40 block">Shop / Vendor</span>
                    <span className="font-semibold text-white">{selectedComplaint.shop_name || 'Unspecified'}</span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.05]">
                    <span className="text-white/40 block">Market Area</span>
                    <span className="font-semibold text-white">{selectedComplaint.location_area || 'Rawalpindi / ICT'}</span>
                  </div>
                </div>

                {selectedComplaint.lat && selectedComplaint.lng ? (
                  <MiniLocationMap
                    lat={selectedComplaint.lat}
                    lng={selectedComplaint.lng}
                    areaName={selectedComplaint.location_area}
                    shopName={selectedComplaint.shop_name}
                    height="h-36"
                  />
                ) : (
                  <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.05] text-white/40 text-center">
                    No GPS coordinates attached to this grievance.
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <h4 className="font-bold text-xs uppercase tracking-wider text-white/80">
                  Citizen Spoken Transcript
                </h4>
                <div className="p-3.5 rounded-2xl bg-white/[0.02] border border-white/[0.06] italic text-white/90 leading-relaxed">
                  "{selectedComplaint.transcript_raw}"
                </div>
              </div>

              {shopHistory.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="font-bold text-xs uppercase tracking-wider text-amber-300">
                      Shop History ({shopHistory.length} other violations)
                    </h4>
                    <span className="text-[10px] text-amber-400 font-bold px-1.5 py-0.5 rounded bg-amber-500/20">
                      Repeat Offender
                    </span>
                  </div>
                  <div className="space-y-1.5">
                    {shopHistory.map((sh) => (
                      <div
                        key={sh.id}
                        onClick={() => setSelectedComplaint(sh)}
                        className="p-2 rounded-xl bg-amber-500/5 hover:bg-amber-500/10 border border-amber-500/20 text-[11px] flex items-center justify-between cursor-pointer"
                      >
                        <span className="text-white font-medium">{sh.item_name}</span>
                        <span className="font-mono text-rose-300">{formatVariance(sh.percentage_overcharge)}</span>
                        <span className="text-white/40 font-mono">{formatTimeAgo(sh.created_at, language)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="p-4 rounded-2xl bg-[#131515] border border-white/10 space-y-4">
                <h4 className="font-bold text-xs uppercase tracking-wider text-white">
                  Magistrate Resolution Controls
                </h4>

                <div>
                  <label className="text-[11px] text-white/60 block mb-1">Update Status</label>
                  <select
                    value={editingStatus}
                    onChange={(e) => setEditingStatus(e.target.value)}
                    className="w-full bg-[#0c0c0c] border border-white/10 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-rose-500"
                  >
                    <option value="Pending">Pending</option>
                    <option value="Investigating">Investigating</option>
                    <option value="Resolved">Resolved</option>
                    <option value="Rejected">Rejected</option>
                  </select>
                </div>

                <div>
                  <label className="text-[11px] text-white/60 block mb-1">Assign Authority</label>
                  <select
                    value={editingAuthority}
                    onChange={(e) => setEditingAuthority(e.target.value)}
                    className="w-full bg-[#0c0c0c] border border-white/10 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-rose-500"
                  >
                    {/* Values mirror the backend `routing_agency` strings exactly,
                        otherwise the persisted assignment would not round-trip. */}
                    <option value="Punjab Enforcement &amp; Regulatory Authority (PERA) / ICT Administration">
                      PERA - Price Enforcement
                    </option>
                    <option value="Punjab Food Authority (PFA)">
                      PFA - Punjab Food Authority
                    </option>
                    <option value="Capital Development Authority (CDA / MCI) / WASA Rawalpindi">
                      Municipal Corporation
                    </option>
                  </select>
                </div>

                <div>
                  <label className="text-[11px] text-white/60 block mb-1">{t.admin.internalNotes}</label>
                  <textarea
                    rows={3}
                    value={editingNotes}
                    onChange={(e) => setEditingNotes(e.target.value)}
                    placeholder={t.admin.notesPlaceholder}
                    className="w-full bg-[#0c0c0c] border border-white/10 rounded-xl p-3 text-xs text-white placeholder-white/40 focus:outline-none focus:border-rose-500"
                  />
                </div>

                <button
                  type="button"
                  onClick={handleSaveResolution}
                  disabled={isSaving}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs shadow-[0_0_20px_rgba(229,72,77,0.4)] transition-all cursor-pointer disabled:opacity-50"
                >
                  {saveSuccess ? (
                    <>
                      <Check className="w-3.5 h-3.5" />
                      <span>{t.admin.saved}</span>
                    </>
                  ) : (
                    <>
                      <Save className="w-3.5 h-3.5" />
                      <span>{isSaving ? t.admin.saving : t.admin.saveChanges}</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
