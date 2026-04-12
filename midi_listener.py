# midi_listener.py
# Listens to MIDI input from your piano and checks if the played chord is correct

import mido
from chord_matcher import match_chord

# MIDI note number to note name (e.g. 60 = C4 = middle C)
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def midi_note_to_name(note_number):
    return NOTE_NAMES[note_number % 12]

def listen(chords):
    # List available MIDI ports
    ports = mido.get_input_names()
    if not ports:
        print("No MIDI devices found. Make sure your piano is connected via USB.")
        return

    print("Available MIDI devices:")
    for i, port in enumerate(ports):
        print(f"  [{i}] {port}")

    choice = int(input("Select device number: "))
    selected_port = ports[choice]

    print(f"\nConnected to: {selected_port}")
    print("Play a chord on your piano...\n")

    held_notes = set()

    with mido.open_input(selected_port) as port:
        for msg in port:
            if msg.type == "note_on" and msg.velocity > 0:
                held_notes.add(midi_note_to_name(msg.note))
                print(f"Notes held: {sorted(held_notes)}")

            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                if held_notes:
                    result = match_chord(held_notes, chords)
                    if result:
                        print(f"Correct! You played: {result['Name']}\n")
                    else:
                        print(f"Not recognized. Notes played: {sorted(held_notes)}\n")
                held_notes.clear()
