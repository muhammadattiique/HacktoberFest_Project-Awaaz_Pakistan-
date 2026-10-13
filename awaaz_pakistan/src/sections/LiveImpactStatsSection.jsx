import React, { useEffect, useState } from 'react';
import { useLanguage } from '../i18n/LanguageContext';
import { Badge } from '../components/ui/Badge';
import { AnimatedCounter } from '../components/ui/AnimatedCounter';
import { CardTilt } from '../components/ui/CardTilt';
import { getAnalyticsOverview, getHotspots } from '../lib/api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { TrendingUp, AlertTriangle, MapPin, CheckCircle } from 'lucide-react';
import { formatVariance } from '../lib/utils';

export const LiveImpactStatsSection = () => {
  const { t } = useLanguage();
  const [stats, setStats] = useState(null);
  const [hotspots, setHotspots] = useState([]);

  useEffect(() => {
    let isMounted = true;
    const fetchStats = async () => {
      try {
        const [overviewRes, hotspotsRes] = await Promise.allSettled([
          getAnalyticsOverview(),
          getHotspots(),
        ]);

        if (isMounted) {
          if (overviewRes.status === 'fulfilled' && overviewRes.value.data) {
            setStats(overviewRes.value.data);
          }
          if (hotspotsRes.status === 'fulfilled' && hotspotsRes.value.data) {
            setHotspots(hotspotsRes.value.data);
          }
        }
      } catch (err) {
        console.warn('Stats fetch error:', err);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 30000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Fallback defaults if loading
  const totalComplaints = stats?.total_complaints ?? 142;
  const violationsCaught = stats?.overpricing_cases ?? 118;
  const avgOvercharge = stats?.average_overcharge_pct ?? 42.6;
  const languagesCount = 6; // English, Urdu, Punjabi, Sindhi, Balochi, Pashto

  // Chart data
  const chartData = stats?.most_gouged_items?.map((item) => ({
    name: item.item_name,
    overcharge: Math.round(item.average_overcharge_pct),
    count: item.complaint_count,
  })) || [
    { name: 'Potato', overcharge: 82, count: 42 },
    { name: 'Tomato', overcharge: 65, count: 36 },
    { name: 'Sugar', overcharge: 52, count: 28 },
    { name: 'Roti', overcharge: 56, count: 24 },
    { name: 'Chicken', overcharge: 25, count: 19 },
  ];

  return (
    <section id="dashboard" className="py-24 sm:py-32 relative overflow-hidden bg-[#030014]">
      {/* Background radial glow */}
      <div className="pointer-events-none absolute top-1/2 left-1/3 -translate-y-1/2 w-[700px] h-[450px] bg-violet-900/10 rounded-full blur-[140px]" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Section Header */}
        <div className="flex flex-col items-center text-center mb-16">
          <Badge variant="violet" pulsing={false} className="mb-4">
            {t.stats.badge}
          </Badge>
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-extrabold tracking-tight text-white mb-4">
            {t.stats.title}
          </h2>
          <p className="max-w-2xl text-base sm:text-lg text-white/60">
            {t.stats.subtitle}
          </p>
        </div>

        {/* 4 Animated Count-up Metric Cards in VoxAI card style */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6 mb-12">
          {/* Total Complaints */}
          <CardTilt className="p-6 rounded-3xl bg-[#0c0c0c]/80 border border-white/[0.08] backdrop-blur-xl shadow-xl">
            <span className="text-xs text-white/50 block mb-2">{t.stats.totalComplaints}</span>
            <div className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-white">
              <AnimatedCounter value={totalComplaints} duration={1.8} />
            </div>
            <div className="mt-3 flex items-center gap-1.5 text-[11px] text-violet-400">
              <span className="w-1.5 h-1.5 rounded-full bg-violet-400" />
              <span>Real-time citizen feed</span>
            </div>
          </CardTilt>

          {/* Violations Identified */}
          <CardTilt className="p-6 rounded-3xl bg-[#0c0c0c]/80 border border-white/[0.08] backdrop-blur-xl shadow-xl">
            <span className="text-xs text-white/50 block mb-2">{t.stats.violationsCaught}</span>
            <div className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-rose-400">
              <AnimatedCounter value={violationsCaught} duration={1.8} />
            </div>
            <div className="mt-3 flex items-center gap-1.5 text-[11px] text-rose-400">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Gouging confirmed</span>
            </div>
          </CardTilt>

          {/* Average Overcharge */}
          <CardTilt className="p-6 rounded-3xl bg-[#0c0c0c]/80 border border-white/[0.08] backdrop-blur-xl shadow-xl">
            <span className="text-xs text-white/50 block mb-2">{t.stats.avgOvercharge}</span>
            <div className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-amber-400">
              <AnimatedCounter value={avgOvercharge} decimals={1} suffix="%" duration={1.8} />
            </div>
            <div className="mt-3 flex items-center gap-1.5 text-[11px] text-amber-300">
              <TrendingUp className="w-3.5 h-3.5" />
              <span>Above official ceiling</span>
            </div>
          </CardTilt>

          {/* Languages Supported */}
          <CardTilt className="p-6 rounded-3xl bg-[#0c0c0c]/80 border border-white/[0.08] backdrop-blur-xl shadow-xl">
            <span className="text-xs text-white/50 block mb-2">{t.stats.languagesSupported}</span>
            <div className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-emerald-400">
              <AnimatedCounter value={languagesCount} duration={1.5} suffix=" Dialects" />
            </div>
            <div className="mt-3 flex items-center gap-1.5 text-[11px] text-emerald-400">
              <CheckCircle className="w-3.5 h-3.5" />
              <span>EN, Urdu, Punjabi, Sindhi, Balochi, Pashto</span>
            </div>
          </CardTilt>
        </div>

        {/* Chart & Hotspots Split Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Recharts Bar Chart: Violations by Item */}
          <div className="lg:col-span-2 p-6 sm:p-8 rounded-3xl bg-[#0c0c0c]/80 border border-white/[0.08] backdrop-blur-xl shadow-2xl">
            <div className="mb-6">
              <h3 className="text-lg font-bold text-white mb-1">
                {t.stats.chartTitle}
              </h3>
              <p className="text-xs text-white/50">
                {t.stats.chartSub}
              </p>
            </div>

            <div className="h-64 sm:h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <XAxis
                    dataKey="name"
                    stroke="rgba(255,255,255,0.4)"
                    fontSize={11}
                    tickLine={false}
                  />
                  <YAxis
                    stroke="rgba(255,255,255,0.4)"
                    fontSize={11}
                    tickFormatter={(val) => `+${val}%`}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#131515',
                      border: '1px solid rgba(255,255,255,0.1)',
                      borderRadius: '12px',
                      fontSize: '12px',
                      color: '#ffffff',
                    }}
                    formatter={(value) => [`+${value}% Overcharge`, 'Variance']}
                  />
                  <Bar dataKey="overcharge" radius={[8, 8, 0, 0]}>
                    {chartData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={index === 0 ? '#E5484D' : index === 1 ? '#f5a623' : '#814bee'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Hotspot Areas List */}
          {hotspots.length > 0 && (
            <div className="p-6 sm:p-8 rounded-3xl bg-[#0c0c0c]/80 border border-white/[0.08] backdrop-blur-xl shadow-2xl flex flex-col justify-between">
              <div>
                <div className="mb-6">
                  <h3 className="text-lg font-bold text-white mb-1">
                    {t.stats.hotspotsTitle}
                  </h3>
                  <p className="text-xs text-white/50">
                    {t.stats.hotspotsSub}
                  </p>
                </div>

                <div className="space-y-3">
                  {hotspots.slice(0, 5).map((hot, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between p-3 rounded-2xl bg-white/[0.02] border border-white/[0.05] hover:border-white/10 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-xs font-bold text-white/40">
                          #{idx + 1}
                        </span>
                        <div>
                          <p className="text-xs font-semibold text-white truncate max-w-[150px]">
                            {hot.area}
                          </p>
                          <p className="text-[10px] text-white/40">
                            {hot.top_violated_item} • {hot.complaint_count} reports
                          </p>
                        </div>
                      </div>

                      <span className="font-mono text-xs font-bold text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded-full border border-rose-500/20">
                        {formatVariance(hot.avg_overcharge_pct)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-6 pt-4 border-t border-white/[0.05] flex items-center justify-between text-[11px] text-white/40">
                <span className="flex items-center gap-1">
                  <MapPin className="w-3.5 h-3.5 text-rose-400" />
                  <span>ICT & Rawalpindi Price Cells</span>
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

