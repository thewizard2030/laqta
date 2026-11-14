# UI Primitives

## Overview
Reusable UI component primitives, accessible modal dialogs with focus trapping, confirmation dialogs, non-blocking toast notifications, error boundaries, accessible toggles, and brand SVG marks.

## Interface
- ErrorBoundary.tsx: ErrorBoundary - Class component catching UI rendering errors and rendering offline recovery UI
- Toast.tsx: Toast - Non-blocking notification banner with polite/assertive ARIA live regions
- Toast.tsx: ToastType - Notification variants ('info' | 'success' | 'error' | 'warning')
- BrandLogo.tsx: BrandLogo - Primary Laqta brand mark with bilingual typography
- BrandIcons.tsx: GitHubIcon, YouTubeIcon - SVG vector brand icons
- ConfirmDialog.tsx: ConfirmDialog - Modal confirmation dialog for destructive actions (e.g. deletion, reset)
- Modal.tsx: Modal - Accessible dialog component with focus trapping, backdrop blur, and scroll lock
- Button.tsx: Button - Accessible button with loading spinners, variants, and size modifiers
- Button.tsx: ButtonVariant, ButtonSize - Styling variant types ('primary' | 'secondary' | 'danger' | 'ghost')
- LaqtaMark.tsx: LaqtaMark - Stylized scissors icon SVG component
- Switch.tsx: Switch - Accessible boolean toggle switch with ARIA checked state

## Invariants
- Modal traps focus between focusable elements, locks document.body scroll overflow, and restores focus to opener element upon unmount
- Toast uses role='alert' with assertive live region for errors and role='status' with polite region for info/success
- ErrorBoundary catches render errors locally and logs to console without phoning home to remote telemetry

## Side Effects
- Modifies document.body.style.overflow during modal presentation
- Schedules window setTimeout for toast auto-dismissal

## Verification
- Run: `npm --prefix frontend test`
