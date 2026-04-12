# audio_listener.py
# Captures microphone audio and detects piano chord notes via FFT analysis.

import time
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 44100
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
A4_FREQ = 440.0
A4_MIDI = 69


def freq_to_note(freq):
    """Convert a frequency in Hz to a chromatic note name (ignoring octave)."""
    if freq <= 0:
        return None
    midi = round(12 * np.log2(freq / A4_FREQ) + A4_MIDI)
    if not (21 <= midi <= 108):   # A0 to C8 — piano range
        return None
    return NOTE_NAMES[midi % 12]


def _compute_hps(magnitude, n_harmonics=5):
    """
    Harmonic Product Spectrum.
    Multiplies the spectrum with downsampled versions of itself so that
    fundamental frequencies are amplified relative to their harmonics.
    """
    hps = magnitude.copy().astype(float)
    for h in range(2, n_harmonics + 1):
        downsampled = magnitude[::h]
        length = min(len(hps), len(downsampled))
        hps[:length] *= downsampled[:length]
        if length < len(hps):
            hps[length:] = 0.0
    return hps


def detect_notes_from_audio(audio, sample_rate=SAMPLE_RATE, max_notes=5, min_ratio=0.06):
    """
    Detect up to max_notes piano notes from a recorded numpy audio array.

    Strategy:
      1. FFT the audio with a Hann window.
      2. Iteratively find the strongest fundamental using HPS.
      3. Suppress that note's harmonics, then repeat.

    Returns a set of note name strings, e.g. {'C', 'E', 'G'}.
    """
    if len(audio) < 2048:
        return set()

    window = np.hanning(len(audio))
    fft_mag = np.abs(np.fft.rfft(audio * window))
    freqs = np.fft.rfftfreq(len(audio), 1.0 / sample_rate)

    # Restrict to piano range
    piano_mask = (freqs >= 27.5) & (freqs <= 4200.0)
    work = fft_mag.copy()
    work[~piano_mask] = 0.0

    global_max = work.max()
    if global_max == 0:
        return set()

    threshold = global_max * min_ratio
    detected = set()

    for _ in range(max_notes):
        if work.max() < threshold:
            break

        hps = _compute_hps(work, n_harmonics=5)
        hps[~piano_mask] = 0.0

        peak_idx = int(np.argmax(hps))
        peak_freq = float(freqs[peak_idx])
        note = freq_to_note(peak_freq)
        if note:
            detected.add(note)

        # Suppress this fundamental and its harmonics so next pass finds a different note
        for h in range(1, 8):
            center = peak_freq * h
            tol = center * 0.04           # ±4 % tolerance around each harmonic
            work[(freqs >= center - tol) & (freqs <= center + tol)] = 0.0

    return detected


def listen_for_chord(
    onset_threshold=0.018,
    silence_duration=0.45,
    max_record_seconds=4.0,
    timeout_seconds=15.0,
    sample_rate=SAMPLE_RATE,
    status_callback=None,
):
    """
    Blocks until a chord is played and released via the microphone.

    Flow:
      1. Wait until audio exceeds onset_threshold (chord pressed).
      2. Record until silence_duration seconds of quiet follow (chord released).
      3. Return the recorded numpy array for analysis.

    status_callback(str) is called with human-readable status messages if supplied.
    Returns an empty array on timeout.
    """
    CHUNK = 2048
    recorded = []
    recording = False
    silent_chunks = 0
    silence_needed = int(silence_duration * sample_rate / CHUNK)
    max_chunks = int(max_record_seconds * sample_rate / CHUNK)

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
            data = data.flatten()
            rms = float(np.sqrt(np.mean(data ** 2)))

            if not recording:
                if rms > onset_threshold:
                    recording = True
                    recorded = [data]
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
