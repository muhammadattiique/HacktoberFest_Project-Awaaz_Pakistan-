import React, { useState } from 'react';
import { useLanguage } from '../i18n/LanguageContext';
import { Badge } from '../components/ui/Badge';
import { ChevronDown } from 'lucide-react';

export const FaqSection = () => {
  const { t } = useLanguage();
  const [openIndex, setOpenIndex] = useState(0);

  const faqs = [
    { q: t.faq.q1, a: t.faq.a1 },
    { q: t.faq.q2, a: t.faq.a2 },
    { q: t.faq.q3, a: t.faq.a3 },
    { q: t.faq.q4, a: t.faq.a4 },
    { q: t.faq.q5, a: t.faq.a5 }, // Location pin privacy FAQ
    { q: t.faq.q6, a: t.faq.a6 },
  ];

  return (
    <section id="faq" className="py-24 sm:py-32 relative overflow-hidden bg-[#030014]/70">
      {/* Background ambient lighting */}
      <div className="pointer-events-none absolute bottom-1/3 left-1/4 w-[600px] h-[400px] bg-violet-900/10 rounded-full blur-[140px]" />

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Section Header */}
        <div className="flex flex-col items-center text-center mb-16">
          <Badge variant="violet" pulsing={false} className="mb-4">
            {t.faq.badge}
          </Badge>
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-extrabold tracking-tight text-white mb-4">
            {t.faq.title}
          </h2>
          <p className="max-w-xl text-base text-white/60">
            {t.faq.subtitle}
          </p>
        </div>

        {/* Accordion List */}
        <div className="space-y-4">
          {faqs.map((faq, idx) => {
            const isOpen = openIndex === idx;
            return (
              <div
                key={idx}
                className="rounded-2xl bg-[#0c0c0c]/80 border border-white/[0.08] backdrop-blur-xl overflow-hidden transition-all duration-300"
              >
                <button
                  type="button"
                  onClick={() => setOpenIndex(isOpen ? null : idx)}
                  className="w-full flex items-center justify-between p-6 text-left cursor-pointer focus:outline-none"
                  aria-expanded={isOpen}
                >
                  <span className="text-base sm:text-lg font-semibold text-white/90 hover:text-white transition-colors">
                    {faq.q}
                  </span>
                  <div
                    className={`flex items-center justify-center w-8 h-8 rounded-full bg-white/[0.04] border border-white/10 shrink-0 ml-4 transition-transform duration-300 ${
                      isOpen ? 'rotate-180 bg-violet-500/20 text-violet-300' : 'text-white/50'
                    }`}
                  >
                    <ChevronDown className="w-4 h-4" />
                  </div>
                </button>

                {isOpen && (
                  <div className="px-6 pb-6 pt-1 text-sm sm:text-base text-white/65 leading-relaxed border-t border-white/[0.04] animate-in fade-in duration-200">
                    <p>{faq.a}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};

