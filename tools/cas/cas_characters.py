"""User-approved representations for printed CAS glyphs."""
import re

BASIC_BOX='─│┌┐└┘┼'
BOX_MAP=str.maketrans({ch:'┼' for ch in '├┤┬┴'})

def printed_text(text):
    text=text.replace('*','✲')
    # A box border remains a straight stroke beside its output asterisk.
    text=re.sub(r'[├┤┬┴┼]([✲])',r'│\1',text)
    return text.translate(BOX_MAP)
