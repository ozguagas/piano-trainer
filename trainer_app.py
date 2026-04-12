# trainer_app.py
# Piano Chord Trainer — microphone-based chord recognition GUI
# Run with:  python trainer_app.py

import os
import random
import threading
import tkinter as tk
from tkinter import font as tkfont

from chord_loader import load_chords
from audio_listener import listen_for_chord, detect_notes_from_audio, SAMPLE_RATE

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CHORD_FILE = os.path.join(BASE_DIR, 'notes', 'pianoNotes.xlsx')

# ── Colours ───────────────────────────────────────────────────────────────────
BG        = '#1a1a2e'
CARD      = '#16213e'
CARD2     = '#0f3460'
ACCENT    = '#e94560'
TEXT      = '#eaeaea'
MUTED     = '#888888'
GREEN     = '#4caf50'
RED       = '#f44336'
YELLOW    = '#ffd700'
BLUE      = '#64b5f6'


# ── Helpers ───────────────────────────────────────────────────────────────────
_FLAT_TO_SHARP = {
    'Eb': 'D#', 'Bb': 'A#', 'Gb': 'F#',
    'Ab': 'G#', 'Db': 'C#', 'E#': 'F',
    'B#': 'C',  'Fb': 'E',  'Cb': 'B',
}


def _normalize(note):
    return _FLAT_TO_SHARP.get(note.strip(), note.strip())


def _parse_chord_notes(raw):
    """Return a set of normalized note names from a string like 'C–Eb(D#)–G'."""
    notes = set()
    for part in str(raw).split('\u2013'):          # en-dash separator
        part = part.strip()
        if '(' in part:
            part = part[:part.index('(')].strip()
        notes.add(_normalize(part))
    return notes


def _format_notes_display(raw):
    """Return a pretty version of the chord notes string for display."""
    parts = []
    for part in str(raw).split('\u2013'):
        parts.append(part.strip())
    return '  \u2013  '.join(parts)


# ── Main App ──────────────────────────────────────────────────────────────────
class PianoTrainerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title('Piano Chord Trainer')
        self.root.configure(bg=BG)
        self.root.geometry('660x800')
        self.root.resizable(False, False)

        # Load chords — only Solid texture for mic-based training
        all_chords = load_chords(CHORD_FILE)
        self.chords = [c for c in all_chords
                       if str(c.get('Texture', '')).strip() == 'Solid']
        random.shuffle(self.chords)

        self.index     = 0
        self.score     = 0
        self.total     = 0
        self._busy     = False   # True while mic thread is running

        self._build_ui()
        self._show_chord()

    # ── UI Construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        TITLE  = tkfont.Font(family='Segoe UI', size=24, weight='bold')
        LABEL  = tkfont.Font(family='Segoe UI', size=12)
        CHORD  = tkfont.Font(family='Segoe UI', size=32, weight='bold')
        NOTES  = tkfont.Font(family='Segoe UI', size=19)
        HINT   = tkfont.Font(family='Segoe UI', size=10, slant='italic')
        RESULT = tkfont.Font(family='Segoe UI', size=16, weight='bold')
        BTN    = tkfont.Font(family='Segoe UI', size=13, weight='bold')
        SMALL  = tkfont.Font(family='Segoe UI', size=11)

        P = dict(padx=24, pady=6)

        # Title
        tk.Label(self.root, text='Piano Chord Trainer',
                 font=TITLE, bg=BG, fg=ACCENT).pack(pady=(20, 2))

        # Score
        self.score_var = tk.StringVar(value='Score:  0 / 0')
        tk.Label(self.root, textvariable=self.score_var,
                 font=LABEL, bg=BG, fg=MUTED).pack(pady=(0, 12))

        # ── Chord card ──
        card = tk.Frame(self.root, bg=CARD, bd=0)
        card.pack(fill='x', **P)

        self.chord_name_var = tk.StringVar()
        tk.Label(card, textvariable=self.chord_name_var,
                 font=CHORD, bg=CARD, fg=TEXT).pack(pady=(20, 4))

        self.notes_var = tk.StringVar()
        tk.Label(card, textvariable=self.notes_var,
                 font=NOTES, bg=CARD, fg=YELLOW).pack()

        self.fingering_var = tk.StringVar()
        tk.Label(card, textvariable=self.fingering_var,
                 font=SMALL, bg=CARD, fg=MUTED).pack(pady=(6, 2))

        self.zone_var = tk.StringVar()
        tk.Label(card, textvariable=self.zone_var,
                 font=HINT, bg=CARD, fg=MUTED).pack(pady=(0, 4))

        self.hand_var = tk.StringVar()
        tk.Label(card, textvariable=self.hand_var,
                 font=HINT, bg=CARD, fg=BLUE).pack(pady=(0, 8))

        # How-to-play instruction from the database
        tk.Label(card, text='How to play:', font=HINT, bg=CARD, fg=MUTED).pack()
        self.instruction_var = tk.StringVar()
        tk.Label(card, textvariable=self.instruction_var,
                 font=LABEL, bg=CARD, fg=ACCENT,
                 wraplength=560, justify='center').pack(pady=(2, 20))

        # ── Listen button ──
        self.listen_btn = tk.Button(
            self.root, text='\u25b6  Listen',
            font=BTN, bg=ACCENT, fg='white',
            activebackground='#c73652', relief='flat',
            padx=34, pady=12, cursor='hand2',
            command=self._start_listening,
        )
        self.listen_btn.pack(pady=18)

        # Status line
        self.status_var = tk.StringVar(
            value='Press Listen, then play the chord on your keyboard.')
        tk.Label(self.root, textvariable=self.status_var,
                 font=LABEL, bg=BG, fg=MUTED,
                 wraplength=580).pack(pady=(0, 12))

        # ── Result card ──
        rcard = tk.Frame(self.root, bg=CARD2, bd=0)
        rcard.pack(fill='x', **P)

        self.result_var = tk.StringVar(value='')
        self.result_lbl = tk.Label(rcard, textvariable=self.result_var,
                                   font=RESULT, bg=CARD2, fg=TEXT,
                                   wraplength=580)
        self.result_lbl.pack(pady=(16, 4))

        self.detected_var = tk.StringVar(value='')
        tk.Label(rcard, textvariable=self.detected_var,
                 font=LABEL, bg=CARD2, fg=MUTED).pack(pady=(0, 16))

        # ── Navigation ──
        nav = tk.Frame(self.root, bg=BG)
        nav.pack(pady=16)

        bs = dict(font=BTN, relief='flat', padx=24, pady=9, cursor='hand2')
        tk.Button(nav, text='Next Chord', bg='#2e7d32', fg='white',
                  activebackground='#1b5e20',
                  command=self._next_chord, **bs).grid(row=0, column=0, padx=12)
        tk.Button(nav, text='Skip', bg='#424242', fg='white',
                  activebackground='#212121',
                  command=self._skip_chord, **bs).grid(row=0, column=1, padx=12)

        # Tip
        tip = ('Tip: sit in a quiet room, hold the chord for 1\u20132 seconds, '
               'then release. Keep your keyboard close to the microphone.')
        tk.Label(self.root, text=tip, font=HINT, bg=BG, fg=MUTED,
                 wraplength=600, justify='center').pack(pady=(8, 4))

    # ── Chord Display ─────────────────────────────────────────────────────────
    def _show_chord(self):
        if self.index >= len(self.chords):
            random.shuffle(self.chords)
            self.index = 0

        c = self.chords[self.index]
        root_note = str(c.get('Root', '')).strip()
        ctype     = str(c.get('ChordType', '')).strip()
        hand      = str(c.get('Hand', '')).strip()
        texture   = str(c.get('Texture', '')).strip()
        notes_raw   = str(c.get('ChordNotes', '')).strip()
        fingering   = str(c.get('Fingering', '')).strip()
        zone        = str(c.get('KeyboardZone', '')).strip()
        instruction = str(c.get('BrokenOrder', '')).strip()

        self.chord_name_var.set(f'{root_note}  {ctype}')
        self.notes_var.set(_format_notes_display(notes_raw))
        self.fingering_var.set(f'Fingering:  {fingering}')
        self.zone_var.set(zone)
        self.hand_var.set(f'{hand}  \u00b7  {texture}')
        self.instruction_var.set(instruction)

        self.result_var.set('')
        self.detected_var.set('')
        self._set_status('Press Listen, then play the chord on your keyboard.')
        self.score_var.set(f'Score:  {self.score} / {self.total}')

    def _target_notes(self):
        return _parse_chord_notes(self.chords[self.index].get('ChordNotes', ''))

    # ── Audio Flow ────────────────────────────────────────────────────────────
    def _start_listening(self):
        if self._busy:
            return
        self._busy = True
        self.listen_btn.config(state='disabled', text='Listening...')
        self.result_var.set('')
        self.detected_var.set('')
        threading.Thread(target=self._listen_thread, daemon=True).start()

    def _listen_thread(self):
        audio = listen_for_chord(
            onset_threshold=0.018,
            silence_duration=0.45,
            max_record_seconds=4.0,
            timeout_seconds=12.0,
            sample_rate=SAMPLE_RATE,
            status_callback=lambda m: self.root.after(0, self._set_status, m),
        )
        detected = detect_notes_from_audio(audio, sample_rate=SAMPLE_RATE, max_notes=5)
        self.root.after(0, self._show_result, detected)

    def _show_result(self, detected: set):
        self._busy = False
        self.listen_btn.config(state='normal', text='\u25b6  Listen')

        target    = self._target_notes()
        detected  = {_normalize(n) for n in detected}

        if detected:
            self.detected_var.set('Detected:  ' + '  \u00b7  '.join(sorted(detected)))
        else:
            self.detected_var.set(
                'No notes detected \u2014 try playing louder or closer to the mic.')

        self.total += 1
        if detected == target:
            self.score += 1
            self.result_var.set('\u2713  Correct!  Well done!')
            self.result_lbl.config(fg=GREEN)
        else:
            missed = target - detected
            extra  = detected - target
            parts  = []
            if missed:
                parts.append('Missing: ' + ', '.join(sorted(missed)))
            if extra:
                parts.append('Extra: ' + ', '.join(sorted(extra)))
            detail = '  |  '.join(parts)
            self.result_var.set(f'\u2717  Not quite.  {detail}')
            self.result_lbl.config(fg=RED)

        self.score_var.set(f'Score:  {self.score} / {self.total}')

    # ── Navigation ────────────────────────────────────────────────────────────
    def _next_chord(self):
        self.index += 1
        self._show_chord()

    def _skip_chord(self):
        self.index += 1
        self._show_chord()

    def _set_status(self, msg):
        self.status_var.set(msg)


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    root = tk.Tk()
    PianoTrainerApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
