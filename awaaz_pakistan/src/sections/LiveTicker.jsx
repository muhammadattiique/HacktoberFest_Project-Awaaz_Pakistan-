import React, { useEffect, useState } from 'react';
import { getComplaints } from '../lib/api';
import { useLanguage } from '../i18n/LanguageContext';
import { AlertTriangle } from 'lucide-react';
import { formatPrice, formatVariance } from '../lib/utils';

export const LiveTicker = () => {
  const { t, language } = useLanguage();
  const [tickerItems, setTickerItems] = useState([]);

  useEffect(() => {
    let isMounted = true;
    const fetchTickerData = async () => {
      try {
        const res = await getComplaints({ limit: 12 });
        if (isMounted && res.data?.items) {
          const violations = res.data.items.filter(
            (c) => c.item_name && c.reported_price && c.percentage_overcharge > 0
          );
          setTickerItems(violations.length ? violations : res.data.items.slice(0, 8));
        }
      } catch (err) {
        console.warn('Ticker data fetch error:', err);
      }
    };

    fetchTickerData();
    const interval = setInterval(fetchTickerData, 30000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Fallback demo ticker items if empty
  const items = tickerItems.length > 0 ? tickerItems : [
    { item_name: 'Aloo (Potato)', reported_price: 200, official_price: 100, percentage_overcharge: 100, location_area: 'Raja Bazaar' },
    { item_name: 'Pyaaz (Onion)', reported_price: 160, official_price: 120, percentage_overcharge: 33.3, location_area: 'Saddar' },
    { item_name: 'Cheeni (Sugar)', reported_price: 220, official_price: 145, percentage_overcharge: 51.7, location_area: 'G-9 Markaz' },
    { item_name: 'Tamatar (Tomato)', reported_price: 250, official_price: 150, percentage_overcharge: 66.7, location_area: 'Committee Chowk' },
    { item_name: 'Chicken Meat', reported_price: 650, official_price: 520, percentage_overcharge: 25.0, location_area: 'Commercial Market' },
    { item_name: 'Fresh Milk', reported_price: 230, official_price: 200, percentage_overcharge: 15.0, location_area: 'PWD Islamabad' },
  ];

  return (
    <div className="relative border-y border-white/[0.08] bg-[#080808]/90 py-3.5 overflow-hidden backdrop-blur-md">
      {/* Side gradient fade masks */}
      <div className="pointer-events-none absolute left-0 top-0 bottom-0 w-24 bg-gradient-to-r from-[#030014] to-transparent z-10" />
      <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-24 bg-gradient-to-l from-[#030014] to-transparent z-10" />

      <div className="flex items-center">
        {/* Sticky Label */}
        <div className="flex items-center gap-2 pl-4 pr-6 shrink-0 z-20 bg-[#080808]">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500" />
          </span>
          <span className="font-mono text-xs font-bold tracking-wider uppercase text-rose-400">
            {t.ticker.liveAlerts}
          </span>
        </div>

        {/* Scrolling Marquee Strip */}
        <div className="animate-marquee flex items-center gap-8 whitespace-nowrap">
          {[...items, ...items].map((item, index) => {
            const variance = formatVariance(item.percentage_overcharge);
            return (
              <div
                key={`${item.id || index}-${index}`}
                className="flex items-center gap-3 text-xs text-white/80 group cursor-default"
              >
                <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                <span className="font-semibold text-white">
                  {item.item_name}:
                </span>
                <span className="font-mono text-rose-300">
                  {formatPrice(item.reported_price, language)}
                </span>
                <span className="text-white/40">
                  {t.ticker.vsOfficial}
                </span>
                <span className="font-mono text-emerald-400">
                  {formatPrice(item.official_price, language)}
                </span>
                <span className="px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 font-mono font-bold text-[11px] border border-rose-500/30">
                  {variance}
                </span>
                {item.location_area && (
                  <span className="text-white/40">
                    — {item.location_area}
                  </span>
                )}
                <span className="text-white/20 ml-4">•</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

