# glyphsketch notices

glyphsketch (https://github.com/Toldry/glyphsketch) is free software under the GNU Affero
General Public License, version 3 only (the LICENSE file next to this one).

The model files included in this library (glyphsketch-model.bin, glyphsketch-index.bin,
glyphsketch-charset.json) were made from these sources, which ask for attribution:

- Contains information from the Detexify database (https://github.com/kirel/detexify-data),
  which is made available under the Open Database License (ODbL) v1.0. The model is a
  Produced Work of that database.
- Character frequencies derived from Wikipedia (CC BY-SA 4.0 and GFDL),
  https://dumps.wikimedia.org.
- Character data from the Unicode Character Database (Unicode License V3),
  https://www.unicode.org/license.txt.
- The glyph index was computed from renders of free fonts (SIL Open Font License and
  others); no font data is included. The full list, with licenses, is THIRD_PARTY.md in
  the source repository.

An app that uses this library should show `recognizer.charset.attribution` in its about
screen.
