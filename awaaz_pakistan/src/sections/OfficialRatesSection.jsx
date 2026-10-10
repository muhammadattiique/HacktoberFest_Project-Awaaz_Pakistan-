import React, { useEffect, useState } from 'react';
import { useLanguage } from '../i18n/LanguageContext';
import { Badge } from '../components/ui/Badge';
import { Skeleton } from '../components/ui/Skeleton';
import { CardTilt } from '../components/ui/CardTilt';
import { getRates } from '../lib/api';
import { formatPrice } from '../lib/utils';
import { Search } from 'lucide-react';

export const OfficialRatesSection = () => {
  const { t, language } = useLanguage();
  const [rates, setRates] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  const categories = [
    { key: '', label: t.rates.allCategories },
    { key: 'vegetable', label: t.rates.vegetable },
    { key: 'grocery', label: t.rates.grocery },
    { key: 'meat', label: t.rates.meat },
    { key: 'dairy', label: t.rates.dairy },
    { key: 'pulses', label: t.rates.pulses },
  ];

  const fetchRates = async () => {
    setIsLoading(true);
    try {
      const res = await getRates({
        category: selectedCategory || undefined,
        search: searchQuery.trim() || undefined,
      });
      if (res.data?.items) {
        setRates(res.data.items);
      }
    } catch (err) {
      console.warn('Rates fetch error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchRates();
    }, 200);
    return () => clearTimeout(timer);
  }, [selectedCategory, searchQuery]);

  return (
    <section id="official-rates" className="py-24 sm:py-32 relative overflow-hidden bg-[#030014]">
      {/* Background ambient lighting */}
      <div className="pointer-events-none absolute top-1/3 right-1/4 w-[600px] h-[400px] bg-violet-900/10 rounded-full blur-[140px]" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Section Header */}
        <div className="flex flex-col items-center text-center mb-12">
          <Badge variant="violet" pulsing={false} className="mb-4">
            {t.rates.badge}
          </Badge>
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-extrabold tracking-tight text-white mb-4">
            {t.rates.title}
          </h2>
          <p className="max-w-2xl text-base sm:text-lg text-white/60">
            {t.rates.subtitle}
          </p>
        </div>

        {/* Search & Category Filter Controls */}
        <div className="flex flex-col md:flex-row items-center justify-between gap-4 mb-10">
          {/* Search Bar */}
          <div className="relative w-full md:w-96">
            <Search className="absolute left-4 top-3.5 w-4 h-4 text-white/40" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t.rates.searchPlaceholder}
              className="w-full bg-[#0c0c0c]/90 border border-white/10 rounded-full pl-11 pr-5 py-3 text-xs text-white placeholder-white/40 backdrop-blur-md focus:outline-none focus:border-violet-500 shadow-inner"
            />
          </div>

          {/* Category Tabs */}
          <div className="flex flex-wrap items-center justify-center gap-1.5 p-1 rounded-full bg-[#0c0c0c]/80 border border-white/10 backdrop-blur-md">
            {categories.map((cat) => (
              <button
                key={cat.key}
                onClick={() => setSelectedCategory(cat.key)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer ${
                  selectedCategory === cat.key
                    ? 'bg-violet-600 text-white shadow-[0_0_15px_rgba(129,75,238,0.4)]'
                    : 'text-white/60 hover:text-white'
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>
        </div>

        {/* Rates Grid */}
        {isLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
              <Skeleton key={n} className="h-32 rounded-3xl" />
            ))}
          </div>
        ) : rates.length === 0 ? (
          <div className="p-12 text-center rounded-3xl bg-[#0c0c0c]/50 border border-white/10 text-white/50 text-sm">
            No matching items found in the official rate list.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 sm:gap-6">
            {rates.map((item) => (
              <CardTilt
                key={item.id}
                className="p-5 sm:p-6 rounded-3xl bg-[#0c0c0c]/80 border border-white/[0.08] hover:border-violet-500/40 backdrop-blur-xl shadow-xl transition-all duration-300 group"
              >
                <div className="flex items-start justify-between gap-2 mb-3">
                  <div>
                    <h4 className="font-bold text-white text-base group-hover:text-violet-300 transition-colors">
                      {item.name_en}
                    </h4>
                    {item.name_ur && (
                      <span className="font-urdu text-xs text-white/50 block mt-0.5">
                        {item.name_ur}
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-white/[0.05] text-white/40 border border-white/[0.08]">
                    {item.category}
                  </span>
                </div>

                <div className="mt-4 pt-3 border-t border-white/[0.06] flex items-baseline justify-between">
                  <div className="text-xl sm:text-2xl font-extrabold font-mono text-emerald-400">
                    {formatPrice(item.price, language)}
                  </div>
                  <span className="text-xs text-white/40">
                    {t.rates.perUnit} {item.unit || 'kg'}
                  </span>
                </div>
              </CardTilt>
            ))}
          </div>
        )}
      </div>
    </section>
  );
};

