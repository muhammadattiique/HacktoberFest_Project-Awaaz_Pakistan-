/**
 * Map a backend-detected complaint language to the best available
 * SpeechSynthesis language code, with graceful fallbacks.
 *
 * The backend reports languages as: "Urdu", "Roman Urdu", "Punjabi",
 * "Pashto", "English". Browsers rarely ship a Pashto or Punjabi voice, so each
 * language has an ordered preference list and we pick the first code whose
 * voice is actually installed. Only when nothing closer exists do we fall back
 * to English, so a citizen never hears their Urdu/Punjabi reply read in English
 * when a closer native voice is present.
 */

// Ordered preference of BCP-47 codes per detected language.
const LANG_PREFERENCES = {
  urdu: ['ur-PK', 'ur', 'hi-IN', 'en-US'],
  'roman urdu': ['ur-PK', 'ur', 'hi-IN', 'en-US'],
  punjabi: ['pa-IN', 'pa', 'ur-PK', 'hi-IN', 'en-US'],
  pashto: ['ps-AF', 'ps', 'fa-IR', 'ur-PK', 'en-US'],
  english: ['en-US', 'en-GB', 'en'],
};

const DEFAULT_PREFERENCES = ['en-US', 'en'];

/**
 * Returns the list of available speech-synthesis voice language codes
 * (lower-cased), or an empty array if the API is unavailable.
 */
function getAvailableVoiceLangs() {
  if (typeof window === 'undefined' || !window.speechSynthesis) return [];
  try {
    return window.speechSynthesis.getVoices().map((v) => (v.lang || '').toLowerCase());
  } catch {
    return [];
  }
}

/**
 * Pick the best speech-synthesis language code for a detected language.
 *
 * @param {string} detectedLanguage - e.g. "Urdu", "Roman Urdu", "Punjabi".
 * @returns {string} A BCP-47 language code (e.g. "ur-PK").
 */
export function getSpeechLangCode(detectedLanguage) {
  const key = (detectedLanguage || '').trim().toLowerCase();
  const prefs = LANG_PREFERENCES[key] || DEFAULT_PREFERENCES;

  const available = getAvailableVoiceLangs();
  if (available.length > 0) {
    for (const code of prefs) {
      const target = code.toLowerCase();
      // Exact match, or language-family match (e.g. "ur" matches "ur-pk").
      if (available.some((a) => a === target || a.startsWith(target + '-') || target.startsWith(a + '-'))) {
        return code;
      }
    }
  }

  // No voice list yet (voices load async) or no match: return the top preference
  // so playback still attempts the closest native language rather than English.
  return prefs[0];
}

export default getSpeechLangCode;
