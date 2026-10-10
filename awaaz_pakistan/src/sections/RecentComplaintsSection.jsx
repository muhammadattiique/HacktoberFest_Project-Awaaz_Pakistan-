import React, { useEffect, useState } from 'react';
import { useLanguage } from '../i18n/LanguageContext';
import { Badge } from '../components/ui/Badge';
import { Skeleton } from '../components/ui/Skeleton';
import { getComplaints } from '../lib/api';
import { formatPrice, formatVariance, formatTimeAgo, getSeverityStyle, getStatusStyle } from '../lib/utils';
import { RefreshCw, Clock, CheckCircle } from 'lucide-react';

export const RecentComplaintsSection = () => {
  const { t, language } = useLanguage();
  const [complaints, setComplaints] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchComplaints = async (isBackground = false) => {
    if (!isBackground) setIsLoading(true);
    else setIsRefreshing(true);

    try {
      const res = await getComplaints({ limit: 15 });
      if (res.data?.items) {
        setComplaints(res.data.items);
      }
    } catch (err) {
      console.warn('Recent complaints fetch error:', err);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchComplaints();
    const interval = setInterval(() => fetchComplaints(true), 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <section className="py-24 sm:py-32 relative overflow-hidden bg-[#030014]/80">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Section Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-end justify-between gap-4 mb-12">
          <div>
            <Badge variant="violet" pulsing={false} className="mb-3">
              {t.recent.badge}
            </Badge>
            <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white mb-2">
              {t.recent.title}
            </h2>
            <p className="text-sm text-white/60">
              {t.recent.subtitle}
            </p>
          </div>

          <div className="flex items-center gap-2 text-xs text-white/40">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            <span>{t.recent.liveUpdating}</span>
            <button
              onClick={() => fetchComplaints(true)}
              className="p-1 rounded-lg hover:bg-white/10 text-white/60 hover:text-white transition-colors cursor-pointer ml-1"
              title="Refresh now"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Loading Skeletons */}
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((n) => (
              <Skeleton key={n} className="h-16 w-full rounded-2xl" />
            ))}
          </div>
        ) : complaints.length === 0 ? (
          /* Empty State */
          <div className="flex flex-col items-center justify-center p-16 rounded-3xl bg-[#0c0c0c]/60 border border-white/[0.08] text-center">
            <CheckCircle className="w-12 h-12 text-emerald-400 mb-3" />
            <p className="text-white font-medium text-base mb-1">{t.recent.empty}</p>
          </div>
        ) : (
          /* Complaints Table (Desktop) & Cards (Mobile) */
          <div className="rounded-3xl bg-[#0c0c0c]/80 border border-white/[0.08] backdrop-blur-xl shadow-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-white/[0.08] bg-white/[0.02] text-[11px] font-mono uppercase tracking-wider text-white/40">
                    <th className="py-4 px-6">{t.recent.colId}</th>
                    <th className="py-4 px-6">{t.recent.colTime}</th>
                    <th className="py-4 px-6">{t.recent.colItem}</th>
                    <th className="py-4 px-6">{t.recent.colReported}</th>
                    <th className="py-4 px-6">{t.recent.colOfficial}</th>
                    <th className="py-4 px-6">{t.recent.colVariance}</th>
                    <th className="py-4 px-6">{t.recent.colSeverity}</th>
                    <th className="py-4 px-6">{t.recent.colStatus}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04] text-xs">
                  {complaints.map((c) => {
                    const isViolation = c.percentage_overcharge > 0 || c.is_violation;
                    const sevStyle = getSeverityStyle(c.severity || c.urgency, isViolation);
                    const statusClass = getStatusStyle(c.status);

                    return (
                      <tr
                        key={c.id}
                        className="hover:bg-white/[0.02] transition-colors group cursor-default"
                      >
                        {/* ID */}
                        <td className="py-4 px-6 font-mono text-white/60">
                          {c.id?.slice(0, 8)}...
                        </td>

                        {/* Time */}
                        <td className="py-4 px-6 text-white/50">
                          <span className="flex items-center gap-1.5">
                            <Clock className="w-3 h-3 text-white/30" />
                            <span>{formatTimeAgo(c.created_at, language)}</span>
                          </span>
                        </td>

                        {/* Item & Location */}
                        <td className="py-4 px-6 font-semibold text-white">
                          <div>
                            <span>{c.item_name || 'General Item'}</span>
                            {c.location_area && (
                              <span className="block text-[10px] text-white/40 font-normal truncate max-w-[140px]">
                                {c.location_area}
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Reported Price */}
                        <td className="py-4 px-6 font-mono text-rose-300 font-medium">
                          {formatPrice(c.reported_price, language)}
                        </td>

                        {/* Official Price */}
                        <td className="py-4 px-6 font-mono text-emerald-300 font-medium">
                          {formatPrice(c.official_price, language)}
                        </td>

                        {/* Variance % */}
                        <td className="py-4 px-6 font-mono font-bold">
                          <span
                            className={
                              isViolation ? 'text-rose-400' : 'text-emerald-400'
                            }
                          >
                            {formatVariance(c.percentage_overcharge) || '—'}
                          </span>
                        </td>

                        {/* Severity */}
                        <td className="py-4 px-6">
                          <span
                            className={`px-2.5 py-1 rounded-full text-[10px] font-semibold border ${sevStyle.bg}`}
                          >
                            {c.urgency || c.severity || 'Normal'}
                          </span>
                        </td>

                        {/* Status */}
                        <td className="py-4 px-6">
                          <span
                            className={`px-2.5 py-1 rounded-full text-[10px] font-semibold border ${statusClass}`}
                          >
                            {c.status || 'Pending'}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </section>
  );
};

