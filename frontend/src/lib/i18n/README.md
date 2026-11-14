# I18N

## Overview
Bidirectional text handling library and React component for Arabic and mixed RTL/LTR subtitles, determining text direction from the first strong directional character and applying CSS plaintext bidi formatting.

## Interface
- bidi.ts: detectTextDirection - Detects 'rtl' or 'ltr' from first strong directional Unicode character
- bidi.ts: isMixedDirection - Boolean check whether string contains both Arabic/Hebrew and Latin glyphs
- bidi.ts: bidiContainerStyle - Returns React CSS properties including unicodeBidi: 'plaintext'
- bidi.ts: formatMsAsClock - Converts milliseconds to [h:]mm:ss formatted clock string
- BidiText.tsx: BidiText - Text component rendering strings with automatic directional styling

## Invariants
- First strong directional character determines container direction ('rtl' for Hebrew/Arabic/N'Ko ranges, 'ltr' for Latin)
- Mixed directional text applies unicode-bidi: plaintext to maintain consistent rendering of embedded Latin runs within Arabic sentences

## Side Effects
- None

## Verification
- Run: `npm --prefix frontend test`
