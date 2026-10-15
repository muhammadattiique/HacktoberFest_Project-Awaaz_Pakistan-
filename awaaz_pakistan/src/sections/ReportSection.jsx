import React, { useState, useRef, useEffect } from 'react';
import { useLanguage } from '../i18n/LanguageContext';
import { useAudioRecorder } from '../hooks/useAudioRecorder';
import { useGeolocation } from '../hooks/useGeolocation';
import { useLipSync } from '../hooks/useLipSync';
import { submitVoiceComplaint, submitTextComplaint, normalizeComplaintResult } from '../lib/api';
import { LocationPicker } from '../components/map/LocationPicker';
import { MiniLocationMap } from '../components/map/MiniLocationMap';
import { CardTilt } from '../components/ui/CardTilt';
import { Badge } from '../components/ui/Badge';
import { formatPrice, formatVariance } from '../lib/utils';
import {
  Mic,
  Square,
  RotateCcw,
  Upload,
  Type,
  Send,
  Loader2,
  Copy,
  Check,
  AlertTriangle,
  HelpCircle,
  MapPin,
  Store,
  Volume2,
} from 'lucide-react';

// Single violation verdict card. Renders one complaint from a submission,
// preserving the rose/emerald theming, Badge variants, Noto Nastaliq RTL,
// per-card Copy-ID and Replay-Voice. The shared transcript and map are rendered
// once by the parent, not inside this card.
// Detected-language labels whose native_response is written in a Perso-Arabic
// (RTL) script and should use the Nastaliq/Naskh font + right alignment. Covers
// Urdu plus the newly supported Sindhi/Balochi/Punjabi/Pashto script responses.
// TODO: split Naskh for sd/ps/bal — Noto Nastaliq Urdu is a stopgap for all.
const RTL_RESPONSE_LANGS = new Set([
  'Urdu',
  'Sindhi',
  'Balochi',
  'Baluchi',
  'Punjabi',
  'Pashto',
  'Pushto',
]);

const VerdictCard = ({ complaint, copiedId, onCopyId, t, language, speakText }) => {
  const isViolation = complaint.percentage_overcharge > 0;
  const isRtlResponse = RTL_RESPONSE_LANGS.has(complaint.detected_language);

  return (
    <CardTilt
      className={`p-6 sm:p-8 rounded-3xl border backdrop-blur-2xl shadow-2xl transition-all ${
        isViolation
          ? 'bg-[#140809]/90 border-rose-500/30 shadow-[0_0_40px_rgba(229,72,77,0.25)]'
          : 'bg-[#09140d]/90 border-emerald-500/30 shadow-[0_0_40px_rgba(48,164,108,0.2)]'
      }`}
    >
      {/* Header: Badge & Complaint ID */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-6 border-b border-white/[0.08]">
        <div className="flex items-center gap-3">
          {isViolation ? (
            <Badge variant="red" pulsing={true}>
              {t.verdict.violationBadge}
            </Badge>
          ) : complaint.item_name ? (
            <Badge variant="green" pulsing={false}>
              {t.verdict.normalBadge}
            </Badge>
          ) : (
            <Badge variant="neutral" pulsing={false}>
              {t.verdict.unknownBadge}
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-white/40">{t.verdict.complaintId}:</span>
          <span className="font-mono text-xs text-white/80 bg-white/5 px-2.5 py-1 rounded-lg border border-white/10">
            {complaint.id || 'N/A'}
          </span>
          <button
            onClick={() => onCopyId(complaint.id)}
            className="p-1 rounded-lg hover:bg-white/10 text-white/60 hover:text-white transition-colors cursor-pointer"
            title="Copy Complaint ID"
          >
            {copiedId === complaint.id ? (
              <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Price Delta Metric Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 py-6 border-b border-white/[0.08]">
        <div>
          <span className="text-[11px] text-white/50 block mb-1">{t.verdict.item}</span>
          <span className="text-base sm:text-lg font-bold text-white">
            {complaint.item_name || 'General Grievance'}
          </span>
        </div>

        <div>
          <span className="text-[11px] text-white/50 block mb-1">{t.verdict.reportedPrice}</span>
          <span className="text-base sm:text-lg font-bold font-mono text-rose-300">
            {formatPrice(complaint.reported_price, language)}
          </span>
        </div>

        <div>
          <span className="text-[11px] text-white/50 block mb-1">{t.verdict.officialPrice}</span>
          <span className="text-base sm:text-lg font-bold font-mono text-emerald-300">
            {formatPrice(complaint.official_price, language)}
          </span>
        </div>

        <div>
          <span className="text-[11px] text-white/50 block mb-1">{t.verdict.variance}</span>
          <span
            className={`text-base sm:text-lg font-bold font-mono ${
              complaint.percentage_overcharge > 0
                ? 'text-rose-400'
                : 'text-emerald-400'
            }`}
          >
            {formatVariance(complaint.percentage_overcharge) || '0.0%'}
          </span>
        </div>
      </div>

      {/* Citizen Advisory Voice Output with Noto Nastaliq Urdu RTL */}
      {complaint.native_response && (
        <div className="my-6 p-4 rounded-2xl bg-black/40 border border-white/10">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-semibold text-violet-400 uppercase tracking-wider">
              {t.verdict.nativeResponse}
            </span>
            <button
              type="button"
              onClick={() =>
                speakText(
                  complaint.native_response,
                  isRtlResponse ? 'ur-PK' : 'en-US'
                )
              }
              className="flex items-center gap-1 text-[11px] text-white/60 hover:text-white cursor-pointer"
            >
              <Volume2 className="w-3.5 h-3.5 text-violet-400" />
              <span>Replay Voice</span>
            </button>
          </div>
          <p
            className={`text-sm sm:text-base text-white/90 leading-relaxed ${
              isRtlResponse
                ? 'font-urdu text-right text-base sm:text-lg'
                : 'text-left'
            }`}
          >
            {complaint.native_response}
          </p>
        </div>
      )}

      {/* Routing Agency Details */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs text-white/70">
        <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.05] flex flex-col justify-between">
          <div>
            <span className="text-white/40 block mb-1">{t.verdict.routedTo}</span>
            <p className="font-semibold text-white">
              {complaint.routing_agency || 'PERA - Price Enforcement'}
            </p>
          </div>
          {complaint.helpline_reference && (
            <div className="mt-2 text-[11px] text-white/50">
              Helpline: <span className="font-mono text-white/80">{complaint.helpline_reference}</span>
            </div>
          )}
        </div>
      </div>

      {/* Review required notice if confidence low or fallback used */}
      {complaint.needs_review && (
        <div className="mt-4 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs flex items-center gap-2">
          <HelpCircle className="w-4 h-4 shrink-0" />
          <span>{t.verdict.autoDetectedNotice}</span>
        </div>
      )}
    </CardTilt>
  );
};

export const ReportSection = ({
  avatarController, // { setListening, setThinking, setSpeaking, setVerdict, setError, setIdle }
  onComplaintSubmitted,
}) => {
  const { t, language } = useLanguage();

  // Active Tab: 'voice' | 'upload' | 'text'
  const [activeTab, setActiveTab] = useState('voice');

  // Input states
  const [textInput, setTextInput] = useState('');
  const [uploadedFile, setUploadedFile] = useState(null);
  const [areaName, setAreaName] = useState('');
  const [shopName, setShopName] = useState('');

  // Processing & abort controller
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [verdictData, setVerdictData] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  // Audio Recorder hook
  const {
    isRecording,
    duration,
    audioBlob,
    audioUrl,
    permissionError,
    volumeLevel,
    startRecording,
    stopRecording,
    resetRecording,
  } = useAudioRecorder();

  // Geolocation hook
  const {
    consent,
    setConsent,
    status: geoStatus,
    coordinates,
    errorMessage: geoError,
    requestPosition,
    updateManualCoordinates,
    clearLocation,
  } = useGeolocation();

  // Lip Sync hook - only speakText is consumed here; the avatar reads mouth
  // aperture from its own controller rather than from this section.
  const { speakText } = useLipSync();

  const abortControllerRef = useRef(null);
  const fileInputRef = useRef(null);

  // Connect audio volume to avatar when recording
  useEffect(() => {
    if (isRecording) {
      avatarController?.setListening();
    } else if (!isSubmitting && !verdictData) {
      avatarController?.setIdle();
    }
  }, [isRecording, isSubmitting, verdictData]);

  // Handle Recording Start/Stop
  const handleToggleRecord = () => {
    if (isRecording) {
      stopRecording();
    } else {
      setSubmitError(null);
      setVerdictData(null);
      startRecording();
    }
  };

  // Handle File Upload
  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadedFile(file);
      setSubmitError(null);
    }
  };

  // Submission handler with AbortController and step-by-step avatar reactions
  const handleSubmit = async () => {
    setSubmitError(null);
    setVerdictData(null);
    setIsSubmitting(true);
    abortControllerRef.current = new AbortController();

    // Avatar state sequence
    avatarController?.setThinking(t.report.stepListening);
    const stepTimer1 = setTimeout(() => {
      avatarController?.setThinking(t.report.stepTranscribing);
    }, 900);
    const stepTimer2 = setTimeout(() => {
      avatarController?.setThinking(t.report.stepAnalyzing);
    }, 1800);
    const stepTimer3 = setTimeout(() => {
      avatarController?.setThinking(t.report.stepVerifying);
    }, 2700);

    try {
      let result;

      // Only send coordinates if citizen explicitly checked consent
      const latToSend = consent && coordinates ? coordinates.lat : undefined;
      const lngToSend = consent && coordinates ? coordinates.lng : undefined;

      if (activeTab === 'voice' || activeTab === 'upload') {
        const fileToUpload = activeTab === 'voice' ? audioBlob : uploadedFile;
        if (!fileToUpload) {
          throw new Error('Please record or select an audio file first.');
        }

        result = await submitVoiceComplaint({
          audioBlob: fileToUpload,
          locationArea: areaName,
          shopName,
          lat: latToSend,
          lng: lngToSend,
          signal: abortControllerRef.current.signal,
        });
      } else {
        if (!textInput.trim()) {
          throw new Error('Please enter your complaint text.');
        }

        result = await submitTextComplaint({
          text: textInput,
          locationArea: areaName,
          shopName,
          lat: latToSend,
          lng: lngToSend,
          signal: abortControllerRef.current.signal,
        });
      }

      clearTimeout(stepTimer1);
      clearTimeout(stepTimer2);
      clearTimeout(stepTimer3);

      const data = result.data;
      const normalized = normalizeComplaintResult(data);
      setVerdictData(normalized);
      if (onComplaintSubmitted) onComplaintSubmitted(data);

      // Determine violation & severity for Avatar reaction (multi-item)
      const isViolation = normalized.complaints.some(
        (c) => (c.percentage_overcharge ?? 0) > 0
      );
      const chips = [];
      for (const c of normalized.complaints) {
        if (chips.length >= 6) break;
        if (c.item_name) chips.push({ text: c.item_name, variant: 'neutral' });
        if (c.percentage_overcharge && chips.length < 6) {
          chips.push({
            text: formatVariance(c.percentage_overcharge),
            variant: (c.percentage_overcharge ?? 0) > 0 ? 'alert' : 'success',
          });
        }
      }

      avatarController?.setVerdict(isViolation, chips.slice(0, 6));

      // Speak the primary native response ONCE through SpeechSynthesis / LipSync
      if (normalized.primary?.native_response) {
        const langCode = RTL_RESPONSE_LANGS.has(
          normalized.primary.detected_language
        )
          ? 'ur-PK'
          : 'en-US';
        speakText(normalized.primary.native_response, langCode);
      }

    } catch (err) {
      clearTimeout(stepTimer1);
      clearTimeout(stepTimer2);
      clearTimeout(stepTimer3);

      if (err.name === 'CanceledError' || err.name === 'AbortError') {
        avatarController?.setIdle();
        setSubmitError('Complaint processing was cancelled.');
      } else {
        console.error('Submission failed:', err);
        avatarController?.setError('Analysis failed');

        // Parse friendly error messages
        const status = err.response?.status;
        const responseMessage = err.response?.data?.detail || err.response?.data?.message;
        let friendly = err.message || t.report.networkError;

        const isTimeout =
          err.code === 'ECONNABORTED' ||
          /timeout/i.test(err.message || '');

        if (isTimeout) {
          friendly =
            'Processing is taking longer than usual (voice transcription runs locally). Please wait a moment and try again, or submit your complaint as text.';
        } else if (!err.response && err.request) {
          friendly = 'Unable to connect to the complaint service. Check your connection and try again.';
        } else if (status === 400) {
          friendly = responseMessage || t.report.emptyAudio;
        } else if (status === 413) {
          friendly = 'Audio file is too large (maximum allowed size is 25MB).';
        } else if (status === 415) {
          friendly = 'Unsupported audio format. Please use WAV, MP3, M4A, or WEBM.';
        } else if (status === 422) {
          friendly = responseMessage || 'Validation error: Please check that your input is valid.';
        } else if (status === 503) {
          friendly = responseMessage || 'Complaint processing is temporarily unavailable. Please try again or submit your complaint as text.';
        } else if (status === 500) {
          friendly = responseMessage || 'The server could not process your complaint. Please try again.';
        }
        setSubmitError(friendly);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setIsSubmitting(false);
    avatarController?.setIdle();
  };

  const handleCopyId = (id) => {
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <section id="report" className="py-24 sm:py-32 relative overflow-hidden bg-[#030014]">
      {/* Ambient background glows */}
      <div className="pointer-events-none absolute top-1/4 left-1/2 -translate-x-1/2 w-[900px] h-[500px] bg-gradient-to-b from-violet-900/15 via-rose-900/10 to-transparent rounded-full blur-[160px]" />

      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Section Header */}
        <div className="flex flex-col items-center text-center mb-12">
          <Badge variant="red" pulsing={true} className="mb-4">
            {t.report.badge}
          </Badge>
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-extrabold tracking-tight text-white mb-4">
            {t.report.title}
          </h2>
          <p className="max-w-2xl text-base sm:text-lg text-white/65">
            {t.report.subtitle}
          </p>
        </div>

        {/* Input Format Tabs */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <div className="flex items-center p-1.5 rounded-full bg-[#131515]/90 border border-white/[0.08] backdrop-blur-xl shadow-xl">
            <button
              onClick={() => setActiveTab('voice')}
              className={`flex items-center gap-2 px-5 py-2 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                activeTab === 'voice'
                  ? 'bg-gradient-to-r from-[#814bee] to-[#4f1ad6] text-white shadow-[0_0_15px_rgba(129,75,238,0.4)]'
                  : 'text-white/60 hover:text-white'
              }`}
            >
              <Mic className="w-3.5 h-3.5" />
              <span>{t.report.tabVoice}</span>
            </button>
            <button
              onClick={() => setActiveTab('upload')}
              className={`flex items-center gap-2 px-5 py-2 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                activeTab === 'upload'
                  ? 'bg-gradient-to-r from-[#814bee] to-[#4f1ad6] text-white shadow-[0_0_15px_rgba(129,75,238,0.4)]'
                  : 'text-white/60 hover:text-white'
              }`}
            >
              <Upload className="w-3.5 h-3.5" />
              <span>{t.report.tabUpload}</span>
            </button>
            <button
              onClick={() => setActiveTab('text')}
              className={`flex items-center gap-2 px-5 py-2 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                activeTab === 'text'
                  ? 'bg-gradient-to-r from-[#814bee] to-[#4f1ad6] text-white shadow-[0_0_15px_rgba(129,75,238,0.4)]'
                  : 'text-white/60 hover:text-white'
              }`}
            >
              <Type className="w-3.5 h-3.5" />
              <span>{t.report.tabText}</span>
            </button>
          </div>
        </div>

        {/* Main Reporting Workspace Card */}
        <div className="rounded-3xl bg-[#0c0c0c]/85 border border-white/[0.09] p-6 sm:p-10 backdrop-blur-2xl shadow-[0_25px_50px_-12px_rgba(0,0,0,0.9)] relative overflow-hidden">
          {/* TAB 1: VOICE RECORDING INTERFACE */}
          {activeTab === 'voice' && (
            <div className="flex flex-col items-center text-center py-6">
              {/* Massive Interactive Mic Button */}
              <div className="relative flex items-center justify-center my-6">
                {/* Dynamic sound ripple rings when recording */}
                {isRecording && (
                  <>
                    <div
                      className="absolute rounded-full border border-rose-500/50 animate-ping"
                      style={{
                        width: `${140 + volumeLevel * 80}px`,
                        height: `${140 + volumeLevel * 80}px`,
                      }}
                    />
                    <div
                      className="absolute rounded-full bg-rose-500/10 blur-xl"
                      style={{
                        width: `${160 + volumeLevel * 100}px`,
                        height: `${160 + volumeLevel * 100}px`,
                      }}
                    />
                  </>
                )}

                <button
                  type="button"
                  onClick={handleToggleRecord}
                  disabled={isSubmitting}
                  className={`relative flex items-center justify-center w-28 h-28 sm:w-32 sm:h-32 rounded-full transition-all duration-300 shadow-2xl cursor-pointer ${
                    isRecording
                      ? 'bg-rose-600 text-white shadow-[0_0_40px_rgba(229,72,77,0.8)] scale-105'
                      : 'bg-gradient-to-br from-[#814bee] to-[#4f1ad6] text-white shadow-[0_0_35px_rgba(129,75,238,0.5)] hover:shadow-[0_0_50px_rgba(129,75,238,0.7)] hover:scale-105'
                  }`}
                  aria-label={isRecording ? 'Stop Recording' : 'Start Recording Voice Complaint'}
                >
                  {isRecording ? (
                    <Square className="w-10 h-10 fill-current" />
                  ) : (
                    <Mic className="w-12 h-12" />
                  )}
                </button>
              </div>

              {/* Status prompt & Timer */}
              <div className="space-y-1 mb-4">
                <p className="text-base font-semibold text-white">
                  {isRecording ? t.report.recordingNow : audioBlob ? 'Voice Note Ready' : t.report.recordPrompt}
                </p>
                {isRecording && (
                  <p className="font-mono text-xl font-bold text-rose-400">
                    {Math.floor(duration / 60)}:{(duration % 60).toString().padStart(2, '0')}
                  </p>
                )}
                {!isRecording && audioBlob && (
                  <p className="text-xs text-white/50">
                    Recorded {duration}s of audio
                  </p>
                )}
              </div>

              {/* Audio Playback & Re-record controls */}
              {audioBlob && !isRecording && (
                <div className="flex items-center gap-4 mt-2 mb-6">
                  {audioUrl && (
                    <audio
                      src={audioUrl}
                      controls
                      className="h-10 rounded-full bg-white/[0.05] border border-white/10"
                    />
                  )}
                  <button
                    type="button"
                    onClick={resetRecording}
                    className="flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-white/[0.05] hover:bg-white/[0.1] border border-white/10 text-white/70 hover:text-white text-xs transition-colors cursor-pointer"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>{t.report.reRecord}</span>
                  </button>
                </div>
              )}

              {/* Balochi voice-recognition experimental notice. Balochi
                  transcription is not reliable; recommend the text tab. This
                  reuses the existing low-confidence backend path for any
                  submitted audio and adds no new transcription logic. */}
              {language === 'bal' && (
                <div className="max-w-md mx-auto p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs text-left mb-4">
                  <div className="flex items-start gap-2.5">
                    <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                    <p>{t.report.balochiVoiceNotice}</p>
                  </div>
                </div>
              )}

              {/* Mic Permission Warning */}
              {permissionError && (
                <div className="max-w-md mx-auto p-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs text-left mb-4">
                  <div className="flex items-start gap-2.5">
                    <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                    <p>{t.report.micDenied}</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: UPLOAD AUDIO */}
          {activeTab === 'upload' && (
            <div className="py-8">
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileChange}
                accept="audio/*,.mp3,.wav,.m4a,.webm,.ogg,.aac"
                className="hidden"
              />
              <div
                onClick={() => fileInputRef.current?.click()}
                className="flex flex-col items-center justify-center p-10 border-2 border-dashed border-white/15 hover:border-violet-500/50 rounded-3xl bg-white/[0.02] hover:bg-white/[0.04] transition-all cursor-pointer text-center"
              >
                <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-violet-500/10 border border-violet-500/30 text-violet-400 mb-4">
                  <Upload className="w-7 h-7" />
                </div>
                <p className="text-sm font-semibold text-white mb-1">
                  {uploadedFile ? uploadedFile.name : t.report.uploadPrompt}
                </p>
                <p className="text-xs text-white/40">
                  WAV, MP3, M4A, WEBM up to 25MB
                </p>
              </div>
            </div>
          )}

          {/* TAB 3: TYPE COMPLAINT */}
          {activeTab === 'text' && (
            <div className="py-4">
              <textarea
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                placeholder={t.report.textPlaceholder}
                rows={4}
                className="w-full bg-[#131515] border border-white/10 rounded-2xl p-4 text-sm text-white placeholder-white/40 focus:outline-none focus:border-violet-500 leading-relaxed font-sans"
              />
            </div>
          )}

          {/* OPTIONAL METADATA FIELDS (Market & Shop Name) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-white/[0.08] mb-6">
            <div className="relative">
              <MapPin className="absolute left-3.5 top-3 w-4 h-4 text-white/40" />
              <input
                type="text"
                value={areaName}
                onChange={(e) => setAreaName(e.target.value)}
                placeholder={t.report.areaPlaceholder}
                className="w-full bg-[#131515] border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-xs text-white placeholder-white/40 focus:outline-none focus:border-violet-500"
              />
            </div>

            <div className="relative">
              <Store className="absolute left-3.5 top-3 w-4 h-4 text-white/40" />
              <input
                type="text"
                value={shopName}
                onChange={(e) => setShopName(e.target.value)}
                placeholder={t.report.shopPlaceholder}
                className="w-full bg-[#131515] border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-xs text-white placeholder-white/40 focus:outline-none focus:border-violet-500"
              />
            </div>
          </div>

          {/* LOCATION CAPTURE STEP (OPTIONAL & CONSENT GATED) */}
          <div className="mb-8">
            <LocationPicker
              consent={consent}
              setConsent={setConsent}
              status={geoStatus}
              coordinates={coordinates}
              errorMessage={geoError}
              requestPosition={requestPosition}
              updateManualCoordinates={updateManualCoordinates}
              clearLocation={clearLocation}
              selectedArea={areaName}
              setSelectedArea={setAreaName}
            />
          </div>

          {/* SUBMISSION & CANCEL CONTROLS */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-6 border-t border-white/[0.08]">
            <div className="text-xs text-white/50">
              {consent && coordinates ? (
                <span className="text-rose-400 font-medium">✓ GPS Pin Attached</span>
              ) : (
                <span>No location attached (submission remains 100% valid)</span>
              )}
            </div>

            <div className="flex items-center gap-3 w-full sm:w-auto">
              {isSubmitting ? (
                <>
                  <div className="flex items-center gap-2 px-5 py-2.5 rounded-full bg-violet-600/30 border border-violet-500/50 text-violet-200 text-xs">
                    <Loader2 className="w-4 h-4 animate-spin text-violet-400" />
                    <span>{t.report.processing}</span>
                  </div>
                  <button
                    type="button"
                    onClick={handleCancel}
                    className="px-4 py-2.5 rounded-full bg-white/10 hover:bg-white/15 text-white/80 hover:text-white text-xs font-medium cursor-pointer"
                  >
                    {t.report.cancel}
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={activeTab === 'voice' && !audioBlob}
                  className="w-full sm:w-auto flex items-center justify-center gap-2 px-8 py-3 rounded-full bg-gradient-to-r from-[#814bee] to-[#4f1ad6] hover:from-[#925eff] hover:to-[#5e24f0] text-white font-semibold text-xs shadow-[0_0_25px_rgba(129,75,238,0.5)] hover:shadow-[0_0_35px_rgba(129,75,238,0.7)] transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>
                    {activeTab === 'text' ? t.report.submitTextButton : t.report.submitButton}
                  </span>
                </button>
              )}
            </div>
          </div>

          {/* SUBMIT ERROR DISPLAY */}
          {submitError && (
            <div className="mt-6 p-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start justify-between gap-3 animate-in fade-in">
              <div className="flex items-start gap-2.5">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{submitError}</span>
              </div>
              <button
                onClick={() => setSubmitError(null)}
                className="text-rose-400 hover:text-white text-[11px] underline cursor-pointer"
              >
                Dismiss
              </button>
            </div>
          )}
        </div>

        {/* VERDICT ASSESSMENT (Appears on successful processing) */}
        {verdictData && verdictData.complaints.length > 0 && (
          <div className="mt-12 animate-in fade-in slide-in-from-bottom-6 duration-500 space-y-6">
            {/* 'N violations detected' header shown only for multi-item
                submissions. Count only ACTUAL violations (overcharge > 0), not
                every parsed item, so compliant/under-rate rows are not counted. */}
            {verdictData.complaints.length > 1 && (
              <h3 className="text-lg sm:text-xl font-bold text-rose-300 text-center">
                {t.verdict.violationsCount.replaceAll(
                  '{count}',
                  String(
                    verdictData.complaints.filter(
                      (c) => c.percentage_overcharge > 0
                    ).length
                  )
                )}
              </h3>
            )}

            {/* Shared transcript shown ONCE above the cards */}
            {verdictData.primary?.transcript_raw && (
              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.05] text-xs text-white/70">
                <span className="text-white/40 block mb-1">{t.verdict.transcript}</span>
                <p className="italic text-white/90">"{verdictData.primary.transcript_raw}"</p>
              </div>
            )}

            {/* One verdict card per complaint */}
            {verdictData.complaints.map((c) => (
              <VerdictCard
                key={c.id}
                complaint={c}
                copiedId={copiedId}
                onCopyId={handleCopyId}
                t={t}
                language={language}
                speakText={speakText}
              />
            ))}

            {/* Shared Mini Map shown ONCE after the card list */}
            {verdictData.primary?.lat && verdictData.primary?.lng && (
              <div className="pt-6 border-t border-white/[0.08]">
                <span className="text-xs font-medium text-white/50 block mb-2">
                  {t.verdict.viewOnMap}
                </span>
                <MiniLocationMap
                  lat={verdictData.primary.lat}
                  lng={verdictData.primary.lng}
                  areaName={verdictData.primary.location_area}
                  shopName={verdictData.primary.shop_name}
                />
              </div>
            )}
          </div>
        )}

        {/* No-violation notice: every item was priced at or below the official
            rate, so nothing was registered. */}
        {verdictData &&
          verdictData.complaints.length === 0 &&
          verdictData.message && (
            <div className="mt-12 animate-in fade-in slide-in-from-bottom-6 duration-500">
              <div className="p-6 sm:p-8 rounded-3xl border border-emerald-500/30 bg-[#09140d]/90 shadow-[0_0_40px_rgba(48,164,108,0.2)] text-center">
                <Check className="w-8 h-8 text-emerald-400 mx-auto mb-3" />
                <h3 className="text-lg font-bold text-emerald-300 mb-1.5">
                  {t.verdict.noViolationTitle}
                </h3>
                <p className="text-sm text-white/70 max-w-md mx-auto">
                  {verdictData.message}
                </p>
              </div>
            </div>
          )}
      </div>
    </section>
  );
};

