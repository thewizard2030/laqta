# Caption Visual QA — Arabic RTL (PRD §5 FR-08, §11 Gate D)

Manual QA checklist for caption rendering. **No automated test in this
repository claims Arabic bidi correctness.** Gate D requires a human to
visually review rendered frames before shipping Arabic output.

## 1. Why manual review is mandatory

- Text is stored in **logical order**; Laqta never manually reverses or
  reorders glyphs. bidi layout, mirroring and Arabic joining are delegated
  to libass (FriBiDi + HarfBuzz).
- Different platforms ship different libass versions; pixel results can
  differ from the host used during development.
- Unless stated otherwise, findings below were verified on the dev host
  (Fedora 44, ffmpeg with libass **0.17.4**, FriBidi **1.0.16**,
  HarfBuzz, font *Noto Sans Arabic*). They are documented host-specific
  findings, not universal guarantees.

## 2. Bidi base direction: what libass actually does (verbatim of source)

Investigation (October 2026), verified by rendering color-tagged test
lines through FFmpeg/libass and measuring the left-to-right pixel order:

1. libass resolves the **paragraph direction per event** from the event's
   effective *font Encoding* (style `Encoding`, override-able per line with
   the `\fe` tag). If the value is any real charset number (0..255),
   `ass_resolve_base_direction` returns **`FRIBIDI_PAR_LTR` — a hardcoded
   LTR base direction** (VSFilter compatibility).
2. With a hardcoded LTR base, Arabic runs are shaped/joined correctly, but
 the *word order of multi-word Arabic lines is visually reversed*, and
   explicit bidi controls (U+200F RLM, U+202B RLE, U+2067 RLI) have **no
   effect** on paragraph direction (they only affect their own run).
3. The value **`Encoding: -1`** (equivalently a `{\fe-1}` override tag) is
   a documented libass extension that switches the event to
   **auto-detection** (first strong character → paragraph direction) and
   enables whole-text layout shaping across tags.
4. In autodetect mode, a leading **U+200F RIGHT-TO-LEFT MARK** is a strong
   RTL character: it pins the paragraph direction to RTL *even when the
   line starts with Latin letters or digits*. The mark itself is never
   rendered (libass treats U+200F as default-ignorable/skipped).

Measured example (logical text `واحد اثنين THREE`, blue/red/green color
tags, alignment=5):

| Script variant                                    | Observed left→right visual order | Base direction |
| ------------------------------------------------- | -------------------------------- | -------------- |
| plain (`Encoding: 1`)                             | واحد → اثنين → THREE             | LTR (forced) ❌ |
| `Encoding: 1` + RLM prefix                        | واحد → اثنين → THREE             | LTR (forced) ❌ |
| `Encoding: 1` + RLE/RLE-wrapped text              | واحد → اثنين → THREE             | LTR (forced) ❌ |
| `{\fe-1}`, Arabic-first line                      | THREE → اثنين → واحد             | RTL (auto) ✅  |
| `{\fe-1}` + RLM, Latin-initial line               | THREE → اثنين → HELLO            | RTL (forced) ✅ |
| `{\fe-1}`, Latin-initial line, **no** RLM         | HELLO → اثنين → THREE            | LTR (auto)      |

## 3. What Laqta generates (FR-08 policy)

- **ASS**: for any cue whose text contains Arabic script, every Dialogue
  line is emitted as `{\fe-1}` + `<RLM>` before the first visible line and
  `<RLM>` before each subsequent (`\N`-separated) visual line — libass
  treats each `\N` line as its own bidi paragraph, so every line carries
  the mark. Latin-only cues get no bidi prefix.
- **SRT**: pure logical-order text; **no** bidi control characters. This
  keeps the file clean for editing and round-tripping into other tools
  (they apply their own bidi logic to logical text).
- Karaoke (`\k`) is emitted only when the user opted in **and** word
  timings passed reliability checks; otherwise segment-timed cues without
  karaoke tags (warnings surface the reason, e.g. `missing_words`,
  `low_confidence`).
- **Karaoke tags are inline.** All words of a visual line live on that
  line; only real line breaks use `\N`. (An earlier revision emitted one
  `\N`-separated line per word, which rendered a vertical word list
  instead of a caption.)
- In karaoke mode the ASS **PrimaryColour paints the already-spoken**
  part of the line and the **SecondaryColour the part still to come**, so
  the highlight colour fills the caption as the speaker reaches each
  word. Without karaoke the PrimaryColour is simply the text colour.

## 3a. Cue timing and layout (measured, October 2026)

Two defects were found by rendering a real 40 s clip and comparing it
against a local Whisper word-level re-timing of the same audio:

1. **Overlapping cues.** Platform caption tracks (YouTube) publish
   *rolling* cues: a cue stays on screen for roughly twice the interval
   until the next cue starts, so consecutive cues overlap. Using the raw
   cue end painted two blocks of text at once and kept the previous,
   already-spoken block on screen. The platform replaces a cue when the
   next one starts, so the effective window is `[cue.start, next.start)`.
   Measured against the local re-timing, the platform cue **starts** line
   up with the real word boundaries (often to within 40 ms) while the cue
   **ends** do not. The generator therefore resolves every window to
   `min(cue.end, next_cue.start)`, which is a no-op for ordinary
   non-overlapping ASR segments.
2. **Text far too small and lines too wide.** The old layout used a fixed
   42-characters-per-line budget with a 64 px font, which measured
   ~1134 px on a 1080 px canvas: the lines spilled outside the safe area
   while still *looking* small. Line widths are now derived from the
   actual font advance (Arabic joins, so it is ~0.25 em per character, not
   the ~0.5 em a Latin assumption predicts — measured by rendering
   through libass itself), so a line never leaves the safe area.

Long cues are split into several shorter cues whose time is distributed
proportionally to their text length (`WARNING_TEXT_SPLIT` discloses it);
a genuinely unbreakable overflow still raises `WARNING_TEXT_OVERFLOW`.

## 4. How to reproduce a QA render locally (Fedora, repo layout)

```bash
cd backend
.venv/bin/python -m pytest tests/test_captions.py tests/test_render.py -q
```

For a visual smoke render of the bilingual test line, generate captions
via the API (or reuse `format_ass` in a Python snippet), then:

```bash
ffmpeg -f lavfi -i "color=c=black:s=1080x1920:d=3:r=1" \
       -vf "subtitles=<project>/captions/<candidate_id>.ass" \
       -c:v libopenh264 -preset fast -c:a aac <out>.mp4
```

Extract a representative PNG frame and view it. Fixture video for layout
tests: `testsrc` lavfi source is sufficient; **never commit private
source media** to the repository.

## 5. Visual checklist

Run each item on at least one 1080×1920 render covering the *actual*
watched video content (real captions from a real transcript), not only
synthetic text.

*Arabic correctness*

- **V1** Arabic words are joined (letter shaping): you must not see
  isolated forms like `م ر ح ب ا` inside a word.
- **V2** Multi-word lines read **right-to-left**: the *first* word of the
  transcript sentence must appear at the RIGHT edge of the line block.
  (This is the check that catches a re-occurrence of the hard-coded-LTR
  regression described in §2.)
- **V3** Latin words embedded in Arabic sentences (e.g. brand names like
  "Cairo", "Ahmad") appear as separate LTR islands; their internal letter
  order is normal and their position matches the sentence context.
- **V4** Western numerals / digits inside Arabic sentences render as a
  single LTR run (e.g. `2024` not `4202`) and sit correctly in the
  sentence flow.
- **V5** Mixed punctuation (Arabic comma `،`, Latin `! ?` , quotes) sits
  on the correct side of the adjacent word.
- **V6** Lines that *start* with a Latin word keep the whole caption in
  RTL paragraph direction (our RLM prefix) — the Latin word may lead the
  line, but subsequent Arabic continuation flows right-to-left.
- **V7** Two-line wrapping (`\N`-separated): the **second** line is also
  RTL — check that a mixed line like "هنالك أيضا HELLO" flips correctly
  when wrapped standalone.

*Layout / styling*

- **V8** Safe margins: no glyph crosses the configured horizontal/vertical
  margins for both `bottom` and `middle` positions.
- **V9** Two-line cues do not collide with each other or with the frame
  edge; long single words overflow the char budget without being split
  (an overflow warning must already have surfaced in the API response).
- **V9b** **Only one caption block is on screen at a time.** Overlapping
  cues (a stale block behind the current one) are the defect that made
  the first real render look wrong; check several timestamps in the
  middle of a sentence.
- **V9c** The caption text matches what is being said at that moment:
  check a few cue boundaries against the audio.
- **V10** Colors match the configured foreground/outline at video true
  colors (no gamma surprises at `YCbCr Matrix: TV.709`).
- **V11** Font fallback: when the configured font lacks Arabic glyphs,
  the render still shows shaped Arabic via fallback — and the API produced
  the `arabic_font` warning (`fc-list :lang=ar` probe). If no Arabic
  script font exists on the host, expect tofu boxes in the render; that is
  an environment problem, not a code bug — report it, do not ship.

*Karaoke (optional feature)*

- **V12** With user opt-in and reliable word timings, each `\k` word
  highlights in order; with RTL filling the sweep should advance right→
  left. libass's sweep direction for RTL karaoke is known-width-dependent;
  visually confirm and record the Libass result — **do not hard-code
  claims here.** Karaoke is off by default.
- **V12b** The karaoke words stay **on one visual line** (only real line
  breaks use `\N`) — a vertical word list means the karaoke tag emission
  regressed.
- **V12c** The highlighted word is the one being spoken at that instant.
- **V13** Without opt-in or with unreliable timings, plain no-karaoke
  cues are burned (no partial highlight artifacts).

## 6. Sign-off convention

Record per render: libass version (`ffmpeg -hide_banner -v debug -i <file>
2>&1 | grep -i "libass"`), fonts in use, fixture transcript snippet, and
the PNG frame paths. A Gate D pass or fail verdict must cite V1–V11 as
minimum. V12/V13 only when the karaoke feature is in scope for release.
