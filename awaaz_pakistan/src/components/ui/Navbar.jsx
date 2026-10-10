import React, { useState, useEffect } from 'react';
import { useLanguage } from '../../i18n/LanguageContext';
import { Mic, Menu, X, ArrowUpRight } from 'lucide-react';

export const Navbar = () => {
  const { language, setLanguage, t } = useLanguage();
  const [isScrolled, setIsScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const scrollTo = (id) => {
    setMobileMenuOpen(false);
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const navLinks = [
    { label: t.nav.report, id: 'report' },
    { label: t.nav.howItWorks, id: 'how-it-works' },
    { label: t.nav.liveDashboard, id: 'dashboard' },
    { label: t.nav.officialRates, id: 'official-rates' },
    { label: t.nav.faq, id: 'faq' },
  ];

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        isScrolled
          ? 'bg-[#080808]/80 backdrop-blur-xl border-b border-white/[0.08] py-3.5 shadow-[0_10px_30px_rgba(0,0,0,0.8)]'
          : 'bg-transparent py-5'
      }`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between">
          {/* Brand Logo */}
          <a
            href="#"
            className="flex items-center gap-3 group focus:outline-none"
            aria-label="Awaaz Pakistan Home"
          >
            <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-[#814bee] to-[#4f1ad6] shadow-[0_0_20px_rgba(129,75,238,0.5)] group-hover:shadow-[0_0_28px_rgba(129,75,238,0.7)] transition-all">
              <Mic className="w-5 h-5 text-white" />
              <div className="absolute inset-0 rounded-xl border border-white/20" />
            </div>
            <div className="flex flex-col">
              <div className="flex items-center gap-1.5">
                <span className="font-extrabold text-lg tracking-tight text-white group-hover:text-white/90">
                  {t.nav.brand}
                </span>
                <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-violet-500/20 text-violet-300 border border-violet-500/30">
                  AI
                </span>
              </div>
              <span className="text-[11px] text-white/50 tracking-wide font-normal -mt-0.5">
                {t.nav.tagline}
              </span>
            </div>
          </a>

          {/* Desktop Anchor Navigation */}
          <nav className="hidden md:flex items-center gap-1 bg-[#131515]/70 backdrop-blur-md px-4 py-1.5 rounded-full border border-white/[0.08] shadow-inner">
            {navLinks.map((link) => (
              <button
                key={link.id}
                onClick={() => scrollTo(link.id)}
                className="px-3.5 py-1.5 text-xs font-medium text-white/70 hover:text-white transition-colors rounded-full hover:bg-white/[0.06] cursor-pointer focus:outline-none focus:ring-1 focus:ring-violet-400"
              >
                {link.label}
              </button>
            ))}
          </nav>

          {/* Actions: Language Switcher + Primary Button */}
          <div className="hidden md:flex items-center gap-3">
            {/* Language Switcher */}
            <div className="flex items-center bg-[#131515]/70 backdrop-blur-md p-1 rounded-full border border-white/[0.08]">
              <button
                onClick={() => setLanguage('en')}
                className={`px-2.5 py-1 text-xs rounded-full font-medium transition-all cursor-pointer ${
                  language === 'en'
                    ? 'bg-violet-600 text-white shadow-[0_0_12px_rgba(129,75,238,0.5)]'
                    : 'text-white/60 hover:text-white'
                }`}
              >
                EN
              </button>
              <button
                onClick={() => setLanguage('ur')}
                className={`px-2.5 py-1 text-xs rounded-full font-medium transition-all cursor-pointer ${
                  language === 'ur'
                    ? 'bg-violet-600 text-white shadow-[0_0_12px_rgba(129,75,238,0.5)]'
                    : 'text-white/60 hover:text-white'
                }`}
              >
                اردو
              </button>
            </div>

            {/* Report Now Primary CTA */}
            <button
              onClick={() => scrollTo('report')}
              className="relative group inline-flex items-center gap-2 px-5 py-2 text-xs font-semibold rounded-full bg-gradient-to-r from-[#814bee] to-[#4f1ad6] text-white shadow-[0_0_25px_rgba(129,75,238,0.4)] hover:shadow-[0_0_35px_rgba(129,75,238,0.7)] hover:scale-[1.02] active:scale-[0.98] transition-all cursor-pointer"
            >
              <Mic className="w-3.5 h-3.5" />
              <span>{t.nav.reportNow}</span>
              <ArrowUpRight className="w-3.5 h-3.5 opacity-70 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
            </button>
          </div>

          {/* Mobile Menu Button */}
          <div className="flex md:hidden items-center gap-2">
            <button
              onClick={() => setLanguage(language === 'en' ? 'ur' : 'en')}
              className="px-2.5 py-1 text-xs rounded-full font-medium bg-white/10 text-white border border-white/10"
            >
              {language === 'en' ? 'اردو' : 'EN'}
            </button>
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 rounded-xl bg-white/[0.05] border border-white/10 text-white/80 hover:text-white"
              aria-label="Toggle Navigation Menu"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="md:hidden bg-[#0c0c0c]/95 backdrop-blur-2xl border-b border-white/10 px-5 py-6 mt-3 animate-in fade-in slide-in-from-top-4 duration-200">
          <nav className="flex flex-col gap-3">
            {navLinks.map((link) => (
              <button
                key={link.id}
                onClick={() => scrollTo(link.id)}
                className="text-left py-2.5 px-3 rounded-lg text-sm font-medium text-white/80 hover:text-white hover:bg-white/5 transition-colors cursor-pointer"
              >
                {link.label}
              </button>
            ))}
            <div className="pt-4 border-t border-white/10">
              <button
                onClick={() => scrollTo('report')}
                className="w-full flex items-center justify-center gap-2 py-3 rounded-full bg-gradient-to-r from-[#814bee] to-[#4f1ad6] text-white font-semibold text-sm shadow-[0_0_20px_rgba(129,75,238,0.5)] cursor-pointer"
              >
                <Mic className="w-4 h-4" />
                <span>{t.nav.reportNow}</span>
              </button>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
};

