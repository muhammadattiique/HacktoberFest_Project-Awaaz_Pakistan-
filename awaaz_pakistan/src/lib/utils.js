import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function formatPrice(num, lang = 'en') {
  if (num === null || num === undefined) return '—';
  const val = Number(num).toLocaleString('en-PK');
  return lang === 'ur' ? `${val} روپے` : `Rs ${val}`;
}

export function formatVariance(pct) {
  if (pct === null || pct === undefined) return null;
  const num = Number(pct);
  // Prefix '+' only for genuine positives. Negatives rely on the native minus
  // sign that toFixed() already produces, so we never emit '+-14.3%'. Zero is
  // rendered plain as '0.0%'.
  const sign = num > 0 ? '+' : '';
  return `${sign}${num.toFixed(1)}%`;
}

export function formatTimeAgo(dateString, lang = 'en') {
  if (!dateString) return '';
  const date = new Date(dateString);
  const now = new Date();
  const diffSec = Math.floor((now - date) / 1000);

  if (diffSec < 60) return lang === 'ur' ? 'ابھی' : 'Just now';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return lang === 'ur' ? `${diffMin} منٹ پہلے` : `${diffMin}m ago`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return lang === 'ur' ? `${diffHours} گھنٹے پہلے` : `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return lang === 'ur' ? `${diffDays} دن پہلے` : `${diffDays}d ago`;
}

export function getSeverityStyle(severity, isViolation) {
  if (!isViolation && severity === 'Normal') {
    return {
      bg: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
      glow: 'shadow-[0_0_15px_rgba(52,211,153,0.25)]',
      label: 'Normal',
    };
  }
  switch (severity?.toLowerCase()) {
    case 'critical':
      return {
        bg: 'bg-rose-500/15 border-rose-500/40 text-rose-400',
        glow: 'shadow-[0_0_20px_rgba(244,63,94,0.4)]',
        label: 'Critical',
      };
    case 'high':
      return {
        bg: 'bg-amber-500/15 border-amber-500/40 text-amber-400',
        glow: 'shadow-[0_0_15px_rgba(245,158,11,0.3)]',
        label: 'High',
      };
    case 'moderate':
    case 'medium':
      return {
        bg: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-300',
        glow: 'shadow-[0_0_12px_rgba(234,179,8,0.2)]',
        label: 'Medium',
      };
    default:
      return {
        bg: 'bg-white/5 border-white/10 text-white/70',
        glow: '',
        label: severity || 'Normal',
      };
  }
}

export function getStatusStyle(status) {
  switch (status?.toLowerCase()) {
    case 'investigating':
      return 'bg-amber-500/10 border-amber-500/30 text-amber-400';
    case 'resolved':
      return 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400';
    case 'rejected':
      return 'bg-red-500/10 border-red-500/30 text-red-400';
    case 'pending':
    default:
      return 'bg-indigo-500/10 border-indigo-500/30 text-indigo-400';
  }
}

/**
 * Export array of complaints to CSV
 */
export function exportToCsv(filename, complaints) {
  if (!complaints || !complaints.length) return;
  const headers = [
    'ID',
    'Created At',
    'Item Name',
    'Reported Price (PKR)',
    'Official Price (PKR)',
    'Overcharge %',
    'Severity',
    'Urgency',
    'Status',
    'Routing Agency',
    'Location Area',
    'Shop Name',
    'Latitude',
    'Longitude',
    'Transcript'
  ];

  const rows = complaints.map(c => [
    `"${c.id}"`,
    `"${c.created_at || ''}"`,
    `"${(c.item_name || '').replace(/"/g, '""')}"`,
    c.reported_price ?? '',
    c.official_price ?? '',
    c.percentage_overcharge ?? '',
    `"${c.severity || c.urgency || ''}"`,
    `"${c.urgency || ''}"`,
    `"${c.status || ''}"`,
    `"${(c.routing_agency || '').replace(/"/g, '""')}"`,
    `"${(c.location_area || '').replace(/"/g, '""')}"`,
    `"${(c.shop_name || '').replace(/"/g, '""')}"`,
    c.lat ?? '',
    c.lng ?? '',
    `"${(c.transcript_raw || '').replace(/"/g, '""')}"`
  ]);

  const csvContent = 'data:text/csv;charset=utf-8,\uFEFF' + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement('a');
  link.setAttribute('href', encodedUri);
  link.setAttribute('download', `${filename}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

