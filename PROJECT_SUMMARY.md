# Piano Trainer — Project Summary

## Overview

A Python console application that listens to a MIDI-connected piano/keyboard and recognizes chords in real time by comparing played notes against a built-in chord database.

---

## Project Structure

```
piano-trainer/
├── main.py                          # Entry point
├── midi_listener.py                 # MIDI input handler and note detection
├── chord_loader.py                  # Excel file reader for chord data
├── chord_matcher.py                 # Chord recognition/matching logic
├── requirements.txt                 # Python dependencies
└── notes/
    ├── pianoNotes.xlsx              # Chord database (Excel)
    └── pianoNotes.xlsx - Sheet1.csv # CSV export of the chord database
```

---

## What Each File Does

### `main.py` — Entry Point
- Initializes the app by loading chord data from Excel
- Starts the MIDI listening service
- Provides console feedback during startup

### `midi_listener.py` — MIDI Input Handler
- Listens to MIDI input from a connected piano/keyboard
- Maps MIDI note numbers to note names (C, C#, D, D#, etc.)
- Tracks which notes are currently held down
- Detects note release events (`note_off` or `note_on` with velocity=0)
- When all notes are released, passes the held notes to the chord matcher
- Lets the user select which MIDI device to use at startup
- Provides real-time console feedback as keys are pressed

### `chord_loader.py` — Data Import
- Reads the Excel file using `pandas`
- Converts the spreadsheet into a list of dictionaries
- Each record includes: chord name, root note, chord type, texture, fingering, notes, etc.

### `chord_matcher.py` — Chord Recognition Engine
- Parses chord note strings from the database (handles formats like `C–E–G` and `C–Eb(D#)–G`)
- Normalizes flat notes to sharp equivalents (e.g. `Eb→D#`, `Bb→A#`, `Gb→F#`)
- Compares played notes (as a set) against stored chord definitions
- Returns the matching chord info if found, or `None` if unrecognized

---

## Features Implemented

- Real-time chord recognition from MIDI input
- Immediate console feedback: correct chord name or "not recognized"
- Automatic detection of connected MIDI devices with user selection
- Proper handling of `note_on` / `note_off` MIDI events
- Support for 191 chord definitions across 12 root notes

---

## Chord Database Schema

Stored in `notes/pianoNotes.xlsx` with 191 chord entries:

| Field | Description |
|---|---|
| `#` | Sequential ID |
| `Hand` | Left hand or Right hand |
| `Root` | Root note (C, C#, D, …) |
| `ChordType` | Major, Minor, Dominant7, Diminished |
| `Texture` | Solid (all notes) or Broken (arpeggiated) |
| `Name` | Human-readable chord name |
| `ChordNotes` | Notes that make up the chord |
| `Fingering` | Finger positions (1=thumb … 5=pinky) |
| `BrokenOrder` | Instructions for arpeggiated playing |
| `KeyboardZone` | Where on the keyboard to play |

---

## Technologies Used

| Library | Purpose |
|---|---|
| `pandas` | Excel file reading and data manipulation |
| `openpyxl` | Backend Excel support for pandas |
| `mido` | MIDI message handling |
| `python-rtmidi` | Real-time MIDI I/O interface |

---

## Key Architectural Decisions

- **Modular design** — loading, listening, and matching are clearly separated into individual modules
- **Set-based chord matching** — order of key presses is ignored; only the set of notes matters
- **Flat-to-sharp normalization** — all notes are normalized to sharps before comparison for consistency
- **Data-driven** — all chord definitions live in an external Excel file, no code changes needed to extend the database
- **Event-driven MIDI loop** — non-blocking loop processes messages as they arrive in real time

---

## Known Limitations

- `main.py` has a hardcoded path `"chords.xlsx"` that doesn't match the actual location (`notes/pianoNotes.xlsx`)
- Console-only interface, no visual UI
- No scoring or progress tracking
- Exact note matching only — no fuzzy or partial chord recognition
- Single-threaded; blocks until all notes are released before recognizing a chord
