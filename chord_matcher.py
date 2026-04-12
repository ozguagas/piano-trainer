# chord_matcher.py
# Compares the notes you played against the chord definitions in the Excel file

def parse_chord_notes(chord_notes_str):
    # Handles formats like "C–E–G" or "C–Eb(D#)–G"
    notes = []
    for part in chord_notes_str.split("–"):
        part = part.strip()
        # If there's a parenthetical alternate name like "Eb(D#)", take the first name
        if "(" in part:
            part = part[:part.index("(")].strip()
        # Normalize: replace 'b' flats to sharps where needed
        part = part.replace("Eb", "D#").replace("Bb", "A#").replace("Gb", "F#").replace("Ab", "G#").replace("Db", "C#")
        notes.append(part)
    return set(notes)

def match_chord(played_notes, chords):
    for chord in chords:
        chord_notes = parse_chord_notes(str(chord.get("ChordNotes", "")))
        if chord_notes == played_notes:
            return chord
    return None
