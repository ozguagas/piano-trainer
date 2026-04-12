# Piano Trainer - Main entry point
# Run this file to start the app

from chord_loader import load_chords
from midi_listener import listen

def main():
    print("Loading chord data...")
    chords = load_chords("chords.xlsx")
    print(f"Loaded {len(chords)} chords.")
    print("\nStarting piano listener... Press Ctrl+C to stop.\n")
    listen(chords)

if __name__ == "__main__":
    main()
