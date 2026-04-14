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


def detect_notes_from_audio(audio, sample_rate=SAMPLE_RATE, max_notes=4, threshold_ratio=0.38):
    """
    Detect piano notes using a chromagram (pitch-class energy) approach.

    Why this is more reliable than HPS for polyphonic piano:
      - Piano harmonics are integer multiples of the fundamental, so the 2nd
        harmonic of note X is X an octave higher — same pitch class.
      - By summing FFT energy across ALL octaves for each of the 12 pitch
        classes, harmonics reinforce the correct note instead of polluting others.
      - A simple energy threshold then selects the notes actually played.

    Returns a set of note name strings, e.g. {'E', 'G', 'B'}.
    """
    if len(audio) < 2048:
        return set()

    window = np.hanning(len(audio))
    fft_mag = np.abs(np.fft.rfft(audio * window))
    freqs   = np.fft.rfftfreq(len(audio), 1.0 / sample_rate)

    # Accumulate FFT energy into 12 pitch-class buckets (chroma).
    # For every piano note (MIDI 21–108), find its nearest FFT bin and add
    # its magnitude to the corresponding pitch class.
    chroma = np.zeros(12)
    for midi in range(21, 109):                        # A0 → C8
        freq    = A4_FREQ * (2.0 ** ((midi - A4_MIDI) / 12.0))
        bin_idx = int(np.argmin(np.abs(freqs - freq)))
        if bin_idx < len(fft_mag):
            chroma[midi % 12] += fft_mag[bin_idx]

    peak = chroma.max()
    if peak == 0:
        return set()

    # Keep only pitch classes whose energy clears the threshold, up to max_notes
    indices = [i for i in range(12) if chroma[i] >= peak * threshold_ratio]
    if len(indices) > max_notes:
        indices = sorted(indices, key=lambda i: -chroma[i])[:max_notes]

    return {NOTE_NAMES[i] for i in indices}


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
