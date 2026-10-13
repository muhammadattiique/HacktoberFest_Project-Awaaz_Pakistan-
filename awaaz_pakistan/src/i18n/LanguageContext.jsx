import React, { createContext, useContext, useState, useEffect, useMemo } from 'react';
import { translations, LANGUAGES, RTL_LANGS } from './translations';

const LanguageContext = createContext();

// Set of valid language codes derived from the single source of truth.
const KNOWN_LANGS = new Set(LANGUAGES.map((l) => l.code));

// Recursively merge a (possibly partial) language block over the complete
// English base so every dot-path a component reads (e.g. t.nav.report) always
// resolves. en is the superset; any key missing from `override` falls back to
// the English value, so a partial/incomplete block can never throw at render.
const deepMergeFallback = (base, override) => {
  const result = Array.isArray(base) ? [...base] : { ...base };
  for (const key of Object.keys(override || {})) {
    const baseVal = base?.[key];
    const overrideVal = override[key];
    if (
      overrideVal &&
      typeof overrideVal === 'object' &&
      !Array.isArray(overrideVal) &&
      baseVal &&
      typeof baseVal === 'object' &&
      !Array.isArray(baseVal)
    ) {
      result[key] = deepMergeFallback(baseVal, overrideVal);
    } else {
      result[key] = overrideVal;
    }
  }
  return result;
};

export const LanguageProvider = ({ children }) => {
  const [language, setLanguageState] = useState(() => {
    // Validate the persisted language against the known set; default to 'en'
    // so a stale/invalid awaaz_lang value never selects a missing block.
    const stored = localStorage.getItem('awaaz_lang');
    return stored && KNOWN_LANGS.has(stored) ? stored : 'en';
  });

  const setLanguage = (lang) => {
    const next = KNOWN_LANGS.has(lang) ? lang : 'en';
    setLanguageState(next);
    localStorage.setItem('awaaz_lang', next);
  };

  const isRtl = RTL_LANGS.has(language);

  useEffect(() => {
    document.documentElement.setAttribute('dir', isRtl ? 'rtl' : 'ltr');
    document.documentElement.setAttribute('lang', language);
    if (isRtl) {
      document.body.classList.add('font-urdu');
    } else {
      document.body.classList.remove('font-urdu');
    }
  }, [language, isRtl]);

  // English is the complete base; the active block is deep-merged over it so
  // partial language blocks render English for any missing key with no crash.
  const t = useMemo(
    () => deepMergeFallback(translations.en, translations[language] || {}),
    [language]
  );

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t, isRtl }}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = () => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
};
