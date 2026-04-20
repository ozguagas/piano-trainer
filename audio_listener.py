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


def detect_notes_from_audio(audio, sample_rate=SAMPLE_RATE, max_notes=4, threshold_ratio=0.28):
    """
    Detect piano notes using a short-time averaged chromagram.

    The audio is split into overlapping windows. A chromagram (12-bin
    pitch-class energy) is computed for each window and then averaged.

    Benefits over a single FFT:
      - Simultaneous notes: each window captures all notes → consistent energy.
      - Sequential/broken notes: different windows capture different notes;
        averaging ensures all of them accumulate enough energy to pass the
        threshold even though no single window contains the full chord.
      - Random noise peaks average out across windows.

    Returns a set of note name strings, e.g. {'E', 'G', 'B'}.
    """
    if len(audio) < 2048:
        return set()

    WIN  = 8192   # ~186 ms window — long enough to capture one clear note
    HOP  = 2048   # 75 % overlap

    chroma_sum = np.zeros(12)
    n_windows  = 0

    # Pre-compute freq→bin mapping once (all windows share the same size)
    dummy_freqs = np.fft.rfftfreq(WIN, 1.0 / sample_rate)
    midi_bins   = {}
    for midi in range(21, 109):          # A0 → C8
        freq = A4_FREQ * (2.0 ** ((midi - A4_MIDI) / 12.0))
        midi_bins[midi] = int(np.argmin(np.abs(dummy_freqs - freq)))

    for start in range(0, max(1, len(audio) - WIN + 1), HOP):
        chunk = audio[start : start + WIN]
        if len(chunk) < WIN:
            chunk = np.pad(chunk, (0, WIN - len(chunk)))
        window  = np.hanning(WIN)
        fft_mag = np.abs(np.fft.rfft(chunk * window))

        chroma = np.zeros(12)
        for midi, b in midi_bins.items():
            if b < len(fft_mag):
                chroma[midi % 12] += fft_mag[b]

        chroma_sum += chroma
        n_windows  += 1

    if n_windows == 0 or chroma_sum.max() == 0:
        return set()

    chroma_avg = chroma_sum / n_windows
    peak       = chroma_avg.max()

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
