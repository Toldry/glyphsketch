# glyphsketch notices

glyphsketch (https://github.com/Toldry/glyphsketch) is free software under the GNU Affero
General Public License, version 3 only (the LICENSE file next to this one).

The model files included in this library (glyphsketch-model.bin, glyphsketch-index.bin,
glyphsketch-charset.json) were made from these sources, which ask for attribution:

- Contains information from the Detexify database (https://github.com/kirel/detexify-data),
  which is made available under the Open Database License (ODbL) v1.0. The model is a
  Produced Work of that database.
- Trained in part on UJI Pen Characters v2 by F. Prat, M. J. Castro, D. Llorens, A. Marzal
  and J. M. Vilar, licensed under Creative Commons Attribution 4.0
  (https://archive.ics.uci.edu/dataset/177, https://creativecommons.org/licenses/by/4.0/).
- Trained in part on Omniglot by Brenden Lake, MIT License
  (https://github.com/brendenlake/omniglot).
- Character frequencies derived from Wikipedia (CC BY-SA 4.0 and GFDL),
  https://dumps.wikimedia.org.
- Character names and properties from the Unicode Character Database, Copyright © 1991-2026
  Unicode, Inc., under the Unicode License V3: its full text is Unicode-3.0.txt next to
  this file.
- The glyph index was computed from renders of free fonts (SIL Open Font License and
  others); no font data is included. The full list, with licenses, is THIRD_PARTY.md in
  the source repository.

An app that uses this library should show `recognizer.charset.attribution` in its about
screen.
