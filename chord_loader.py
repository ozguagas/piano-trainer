# chord_loader.py
# Reads the Excel file and returns chord data as a list of dicts

import pandas as pd

def load_chords(filepath):
    df = pd.read_excel(filepath)
    chords = df.to_dict(orient="records")
    return chords
