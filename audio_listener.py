# audio_listener.py
# Captures microphone audio and detects/verifies piano chord notes.

import time
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 44100
NOTE_NAMES  = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
A4_FREQ     = 440.0
A4_MIDI     = 69

# Pre-build the MIDI→FFT-bin map once at import time (shared by all functions).
_WIN        = 8192
_HOP        = 2048
_DUMMY_FREQS = np.fft.rfftfreq(_WIN, 1.0 / SAMPLE_RATE)
_MIDI_BINS  = {
    midi: int(np.argmin(np.abs(_DUMMY_FREQS - A4_FREQ * (2.0 ** ((midi - A4_MIDI) / 12.0)))))
    for midi in range(21, 109)          # A0 → C8
}


# ── Core DSP ─────────────────────────────────────────────────────────────────

def _compute_chroma(audio, sample_rate=SAMPLE_RATE):
    """
    Short-time averaged chromagram.

    Splits the audio into overlapping windows, computes an FFT-based
    chromagram (12 pitch-class energy bins) for each, and returns the
    average.  Averaging across time makes both simultaneous and sequential
    (broken) chord playing work: every note contributes energy in the
    windows where it is present, and the average accumulates all of them.
    """
    chroma_sum = np.zeros(12)
    n_windows  = 0

    for start in range(0, max(1, len(audio) - _WIN + 1), _HOP):
        chunk = audio[start : start + _WIN]
        if len(chunk) < _WIN:
            chunk = np.pad(chunk, (0, _WIN - len(chunk)))
        fft_mag = np.abs(np.fft.rfft(chunk * np.hanning(_WIN)))

        chroma = np.zeros(12)
        for midi, b in _MIDI_BINS.items():
            if b < len(fft_mag):
                chroma[midi % 12] += fft_mag[b]

        chroma_sum += chroma
        n_windows  += 1

    return chroma_sum / n_windows if n_windows > 0 else chroma_sum


# ── Public API ────────────────────────────────────────────────────────────────

def verify_chord(audio, expected_pitch_classes, sample_rate=SAMPLE_RATE):
    """
    Score-informed chord verification.

    Because the trainer always knows the target chord, we don't need to
    answer the hard open-ended question "what notes are playing?" — we only
    need to answer "are THESE specific notes playing?"  That reframing gives
    much higher accuracy:

      - Skip the first 200 ms (hammer-attack transient — noisy, non-harmonic).
      - Compute the averaged chromagram over the sustain portion.
      - Use ASYMMETRIC thresholds:
          * 0.30 for expected notes  → generous (don't miss a note the user played)
          * 0.50 for unexpected notes → strict  (don't flag harmonic ghosts as extras)

    Returns
    -------
    (is_match, confidence, detected_names, missing_names, extra_names)
      is_match   : True when zero missing and zero extra notes
      confidence : float 0–1 (how well the chord was played)
      detected_names : note names the app heard
      missing_names  : expected notes that were too quiet
      extra_names    : unexpected notes above the strict threshold
    """
    # Drop attack transient
    skip = int(0.20 * sample_rate)
    if len(audio) > skip + _WIN:
        audio = audio[skip:]

    if len(audio) < 2048:
        missing = {NOTE_NAMES[pc] for pc in expected_pitch_classes}
        return False, 0.0, set(), missing, set()

    chroma = _compute_chroma(audio, sample_rate)
    peak   = chroma.max()
    if peak == 0:
        missing = {NOTE_NAMES[pc] for pc in expected_pitch_classes}
        return False, 0.0, set(), missing, set()

    chroma_n      = chroma / peak
    expected_set  = set(expected_pitch_classes)
    unexpected_set = set(range(12)) - expected_set

    missing_pcs = {pc for pc in expected_set   if chroma_n[pc] < 0.30}
    extra_pcs   = {pc for pc in unexpected_set if chroma_n[pc] >= 0.50}

    completeness = 1.0 - len(missing_pcs) / max(1, len(expected_set))
    penalty      = 0.5 * min(len(extra_pcs) / max(1, len(expected_set)), 1.0)
    confidence   = round(max(0.0, completeness * (1.0 - penalty)), 2)

    is_match       = (len(missing_pcs) == 0) and (len(extra_pcs) == 0)
    detected_pcs   = (expected_set - missing_pcs) | extra_pcs

    return (
        is_match,
        confidence,
        {NOTE_NAMES[pc] for pc in detected_pcs},
        {NOTE_NAMES[pc] for pc in missing_pcs},
        {NOTE_NAMES[pc] for pc in extra_pcs},
    )


def detect_notes_from_audio(audio, sample_rate=SAMPLE_RATE, max_notes=4, threshold_ratio=0.28):
    """
    Open-ended note detection (used when no target chord is known).
    Returns a set of note name strings, e.g. {'E', 'G', 'B'}.
    """
    if len(audio) < 2048:
        return set()

    chroma_avg = _compute_chroma(audio, sample_rate)
    peak       = chroma_avg.max()
    if peak == 0:
        return set()

    indices = [i for i in range(12) if chroma_avg[i] >= peak * threshold_ratio]
    if len(indices) > max_notes:
        indices = sorted(indices, key=lambda i: -chroma_avg[i])[:max_notes]

    return {NOTE_NAMES[i] for i in indices}


def listen_for_chord(
    onset_threshold=0.018,
    silence_duration=0.8,
    max_record_seconds=4.0,
    timeout_seconds=15.0,
    sample_rate=SAMPLE_RATE,
    status_callback=None,
):
    """
    Blocks until a chord is played and released via the microphone.

    1. Waits for audio above onset_threshold (chord pressed).
    2. Records until silence_duration seconds of quiet follows (chord released).
    3. Returns the recorded numpy array for analysis.

    status_callback(str) is called with status messages if provided.
    Returns an empty array on timeout.
    """
    CHUNK          = 2048
    recorded       = []
    recording      = False
    silent_chunks  = 0
    silence_needed = int(silence_duration * sample_rate / CHUNK)
    max_chunks     = int(max_record_seconds * sample_rate / CHUNK)

    def _status(msg):
        if status_callback:
            status_callback(msg)

    _status("Waiting for you to play...")
    t0 = time.time()

    with sd.InputStream(samplerate=sample_rate, channels=1,
                        blocksize=CHUNK, dtype='float32') as stream:
        while True:
            if time.time() - t0 > timeout_seconds:
                _status("Timed out — no sound detected.")
                break

            data, _ = stream.read(CHUNK)
            data     = data.flatten()
            rms      = float(np.sqrt(np.mean(data ** 2)))

            if not recording:
                if rms > onset_threshold:
                    recording     = True
                    recorded      = [data]
                    silent_chunks = 0
                    _status("Detected! Keep holding...")
            else:
                recorded.append(data)
                if rms < onset_threshold * 0.5:
                    silent_chunks += 1
                    if silent_chunks >= silence_needed:
                        _status("Processing...")
                        break
                else:
                    silent_chunks = 0

                if len(recorded) >= max_chunks:
                    _status("Processing...")
                    break

    return np.concatenate(recorded) if recorded else np.array([], dtype='float32')
