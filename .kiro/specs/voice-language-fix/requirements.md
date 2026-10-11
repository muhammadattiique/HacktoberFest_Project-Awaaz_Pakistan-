# Requirements Document

## Introduction

The voice complaint feature of Awaaz Pakistan lets citizens report price gouging, food
safety, and municipal issues by speaking in their own language. Today the feature does
not reliably work "according to the speaker's language": the backend uses the Whisper
`base` model, which transcribes Urdu, Punjabi, and Pashto poorly, and the spoken-response
("Replay Voice") path maps only Urdu to a native voice while routing every other language
(Roman Urdu, Punjabi, Pashto) to an English voice. The result is wrong or empty transcripts
and acknowledgements that do not match the citizen's language.

This spec covers making the end-to-end voice path language-aware and accurate for all five
supported languages while keeping the system fully local (offline), and ensuring genuine
failures surface actionable errors instead of fabricated results.

Supported languages (confirmed scope): Urdu (Urdu script), Roman Urdu, Punjabi, Pashto, English.
Accuracy posture (confirmed): upgrade to the best feasible local Whisper multilingual model;
slower / higher memory is acceptable as long as the system stays offline.

## Requirements

### Requirement 1: Accurate multilingual transcription

**User Story:** As a citizen speaking Urdu, Punjabi, or Pashto, I want my voice note
transcribed accurately, so that my complaint reflects what I actually said.

#### Acceptance Criteria

1. WHEN a citizen submits a voice note in any supported language THEN the system SHALL
   transcribe the speech using a multilingual Whisper model capable of handling Urdu,
   Punjabi, and Pashto, not the English-biased `base` model.
2. WHEN the configured Whisper model is selected THEN the system SHALL allow the model
   size to be set via configuration (environment variable) without code changes.
3. WHEN transcription completes THEN the system SHALL retain the detected language and the
   transcript text so downstream extraction and acknowledgement use the citizen's language.
4. IF the selected model is unavailable or fails to load THEN the system SHALL log an
   actionable error and SHALL NOT silently fall back to returning a fabricated complaint.

### Requirement 2: Language-correct acknowledgement and playback

**User Story:** As a citizen, I want the spoken and written acknowledgement to be in the
same language I used, so that I understand the response.

#### Acceptance Criteria

1. WHEN the system generates the native acknowledgement THEN it SHALL be in the same
   language and script as the detected language of the complaint.
2. WHEN the citizen plays back the acknowledgement ("Replay Voice") THEN the system SHALL
   select a speech-synthesis language code appropriate to the detected language, covering
   Urdu, Roman Urdu, Punjabi, Pashto, and English rather than defaulting non-Urdu to English.
3. IF no exact voice is available for a detected language THEN the system SHALL fall back to
   the closest reasonable voice (e.g. Urdu voice for Roman Urdu/Punjabi) rather than English.

### Requirement 3: Honest handling of failed or empty speech

**User Story:** As a citizen whose recording failed or was silent, I want a clear message,
so that I know to retry or type my complaint instead of seeing a false result.

#### Acceptance Criteria

1. WHEN transcription genuinely fails (model error, conversion error) THEN the system SHALL
   return an actionable error and SHALL NOT fabricate a complaint result.
2. WHEN the audio is silent or contains no recognisable speech THEN the system SHALL return
   a clear "no speech detected" message distinct from a service-unavailable error.
3. WHEN the backend returns an error THEN the frontend SHALL display a specific, friendly
   message and SHALL offer the text-complaint fallback.

### Requirement 4: Reliable audio capture and conversion

**User Story:** As a citizen on any supported browser, I want my recorded audio accepted
and processed, so that transcription has clean input.

#### Acceptance Criteria

1. WHEN the browser records audio THEN the recorded format SHALL be one the backend can
   convert (e.g. WebM/Opus, mp4/m4a, wav).
2. WHEN the backend converts audio THEN it SHALL resolve an FFmpeg binary (system PATH or a
   bundled fallback) and convert to 16 kHz mono WAV for Whisper.
3. IF FFmpeg is unavailable THEN the system SHALL surface a clear configuration error rather
   than failing with an opaque message.

### Requirement 5: Offline operation and no regressions

**User Story:** As an operator, I want the fix to remain fully local and not break existing
behaviour, so that the demo and existing flows keep working.

#### Acceptance Criteria

1. WHEN the voice feature runs THEN it SHALL operate without any external cloud transcription
   dependency.
2. WHEN the model is upgraded THEN existing text-complaint behaviour and the rate/overcharge
   logic SHALL remain unchanged.
3. WHEN the changes are complete THEN existing backend tests and the frontend build SHALL pass.
