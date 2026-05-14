# trainer_app.py
# Piano Chord Trainer — microphone-based chord recognition GUI
# Run with:  python trainer_app.py

import json
import os
import random
import threading
import tkinter as tk
from datetime import datetime
from tkinter import font as tkfont

from chord_loader import load_chords
from audio_listener import listen_for_chord, verify_chord, SAMPLE_RATE, NOTE_NAMES

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'detection_log.jsonl')

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
_NOTE_TO_PC = {
    'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4,  'F': 5,
    'F#': 6, 'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11,
}

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

        # Load all chords — both Solid and Broken
        all_chords = load_chords(CHORD_FILE)
        self.chords = all_chords
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
                 wraplength=560, justify='center').pack(pady=(2, 12))

        tk.Button(card, text='\U0001f3b9  Show Keys',
                  font=SMALL, bg=CARD2, fg=TEXT,
                  activebackground='#0a2a50', relief='flat',
                  padx=18, pady=6, cursor='hand2',
                  command=self._show_keys_popup).pack(pady=(0, 18))

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
                 font=LABEL, bg=CARD2, fg=MUTED).pack(pady=(0, 4))

        self.confidence_var = tk.StringVar(value='')
        tk.Label(rcard, textvariable=self.confidence_var,
                 font=HINT, bg=CARD2, fg=MUTED).pack(pady=(0, 14))

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

    # ── Piano Keyboard Popup ──────────────────────────────────────────────────
    def _show_keys_popup(self):
        """Open a popup showing a 2-octave piano with the target chord highlighted."""
        target_pcs = set(self._target_pitch_classes())
        c          = self.chords[self.index]
        chord_lbl  = f"{c.get('Root')} {c.get('ChordType')}"
        subtitle   = f"{c.get('Hand')}  ·  {c.get('Texture')}"
        fingering  = str(c.get('Fingering', '')).strip()

        popup = tk.Toplevel(self.root)
        popup.title('Keys to Press')
        popup.configure(bg=BG)
        popup.resizable(False, False)
        popup.transient(self.root)

        BIG  = tkfont.Font(family='Segoe UI', size=18, weight='bold')
        SML  = tkfont.Font(family='Segoe UI', size=10, slant='italic')
        BTN2 = tkfont.Font(family='Segoe UI', size=12, weight='bold')
        KEY  = tkfont.Font(family='Segoe UI', size=8,  weight='bold')

        tk.Label(popup, text=chord_lbl, font=BIG, bg=BG, fg=TEXT).pack(pady=(18, 2))
        tk.Label(popup, text=subtitle,  font=SML, bg=BG, fg=MUTED).pack()

        # ── Canvas ────────────────────────────────────────────────────────────
        WW, WH = 38, 124   # white key size
        BW, BH = 24, 78    # black key size
        N_OCT  = 2
        PAD    = 10

        cw = N_OCT * 7 * WW + PAD * 2
        ch = WH + PAD + 4

        cv = tk.Canvas(popup, width=cw, height=ch, bg=BG, highlightthickness=0)
        cv.pack(padx=24, pady=14)

        # Pitch classes for each white and black key slot within an octave
        WHITE_PCS   = [0, 2, 4, 5, 7, 9, 11]   # C D E F G A B
        BLACK_PCS   = [1, 3, 6, 8, 10]          # C# D# F# G# A#
        # Index of the white key immediately LEFT of each black key
        BLACK_LEFT  = [0, 1, 3, 4, 5]

        # ── White keys ────────────────────────────────────────────────────────
        for oct in range(N_OCT):
            for wi, pc in enumerate(WHITE_PCS):
                x   = PAD + (oct * 7 + wi) * WW
                y   = PAD
                hit = pc in target_pcs
                cv.create_rectangle(
                    x, y, x + WW - 2, y + WH,
                    fill=ACCENT if hit else '#f2f2f2',
                    outline='#666', width=1,
                )
                if hit:
                    # White dot with note name inside
                    cx2, cy2 = x + WW // 2, y + WH - 18
                    cv.create_oval(cx2 - 11, cy2 - 11, cx2 + 11, cy2 + 11,
                                   fill='white', outline='')
                    cv.create_text(cx2, cy2, text=NOTE_NAMES[pc],
                                   font=KEY, fill=ACCENT)

        # ── Black keys (drawn on top) ─────────────────────────────────────────
        for oct in range(N_OCT):
            for bpc, left_wi in zip(BLACK_PCS, BLACK_LEFT):
                x   = PAD + (oct * 7 + left_wi) * WW + WW - BW // 2 - 1
                y   = PAD
                hit = bpc in target_pcs
                cv.create_rectangle(
                    x, y, x + BW, y + BH,
                    fill='#c0102a' if hit else '#111',
                    outline='#000', width=1,
                )
                if hit:
                    cx2, cy2 = x + BW // 2, y + BH - 14
                    cv.create_oval(cx2 - 9, cy2 - 9, cx2 + 9, cy2 + 9,
                                   fill='white', outline='')
                    cv.create_text(cx2, cy2, text=NOTE_NAMES[bpc],
                                   font=KEY, fill='#c0102a')

        # ── Footer ────────────────────────────────────────────────────────────
        if fingering:
            tk.Label(popup, text=f'Fingering:  {fingering}',
                     font=SML, bg=BG, fg=MUTED).pack(pady=(0, 4))

        tk.Label(popup, text='Red / highlighted = notes to press',
                 font=SML, bg=BG, fg=MUTED).pack(pady=(0, 10))

        tk.Button(popup, text='Close', font=BTN2,
                  bg='#424242', fg='white', activebackground='#212121',
                  relief='flat', padx=28, pady=8, cursor='hand2',
                  command=popup.destroy).pack(pady=(0, 18))

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
        self.confidence_var.set('')
        if texture == 'Broken':
            self._set_status('Press Listen, then play each note one by one. Hold each note briefly.')
        else:
            self._set_status('Press Listen, then press all notes together and hold.')
        self.score_var.set(f'Score:  {self.score} / {self.total}')

    def _target_notes(self):
        return _parse_chord_notes(self.chords[self.index].get('ChordNotes', ''))

    def _target_pitch_classes(self):
        notes = _parse_chord_notes(self.chords[self.index].get('ChordNotes', ''))
        return [_NOTE_TO_PC[n] for n in notes if n in _NOTE_TO_PC]

    # ── Audio Flow ────────────────────────────────────────────────────────────
    def _start_listening(self):
        if self._busy:
            return
        self._busy = True
        # Capture pitch classes on the main thread before spawning audio thread
        self._current_pcs = self._target_pitch_classes()
        self.listen_btn.config(state='disabled', text='Listening...')
        self.result_var.set('')
        self.detected_var.set('')
        self.confidence_var.set('')
        threading.Thread(target=self._listen_thread, daemon=True).start()

    def _listen_thread(self):
        audio = listen_for_chord(
            onset_threshold=0.018,
            silence_duration=0.8,
            max_record_seconds=4.0,
            timeout_seconds=12.0,
            sample_rate=SAMPLE_RATE,
            status_callback=lambda m: self.root.after(0, self._set_status, m),
        )
        if len(audio) == 0:
            # Nothing valid captured (noise burst / timeout) — reset without counting
            self.root.after(0, self._reset_after_no_audio)
            return
        result = verify_chord(audio, self._current_pcs, sample_rate=SAMPLE_RATE)
        self.root.after(0, self._show_result, result)

    def _show_result(self, result):
        self._busy = False
        self.listen_btn.config(state='normal', text='\u25b6  Listen')

        is_match, confidence, detected, missing, extra, chroma_debug = result

        if detected:
            self.detected_var.set('Detected:  ' + '  \u00b7  '.join(sorted(detected)))
        else:
            self.detected_var.set(
                'No notes detected \u2014 try playing louder or closer to the mic.')

        self.confidence_var.set(f'Confidence:  {int(confidence * 100)} %')

        self.total += 1
        if is_match:
            self.score += 1
            self.result_var.set('\u2713  Correct!  Well done!')
            self.result_lbl.config(fg=GREEN)
        else:
            parts = []
            if missing:
                parts.append('Missing: ' + ', '.join(sorted(missing)))
            if extra:
                parts.append('Extra: ' + ', '.join(sorted(extra)))
            detail = '  |  '.join(parts)
            self.result_var.set(f'\u2717  Not quite.  {detail}')
            self.result_lbl.config(fg=RED)

        self.score_var.set(f'Score:  {self.score} / {self.total}')

        # Write log entry for debugging
        c = self.chords[self.index]
        entry = {
            'time':       datetime.now().isoformat(timespec='seconds'),
            'chord':      f"{c.get('Root')} {c.get('ChordType')}",
            'texture':    c.get('Texture'),
            'hand':       c.get('Hand'),
            'expected':   sorted(self._target_notes()),
            'detected':   sorted(detected),
            'missing':    sorted(missing),
            'extra':      sorted(extra),
            'is_match':   is_match,
            'confidence': confidence,
            'chroma':     chroma_debug,
        }
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
        except OSError:
            pass

    def _reset_after_no_audio(self):
        self._busy = False
        self.listen_btn.config(state='normal', text='▶  Listen')
        # Status was already set by listen_for_chord (e.g. "Too short — please try again.")

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
