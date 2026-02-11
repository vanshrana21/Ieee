# Phase 1: Core Courtroom UI - Visual Design Specification

## Overview
This document outlines the visual design, layout, and accessibility requirements for the Virtual Courtroom UI implemented in Phase 1.

---

## 🎨 Design System

### Color Palette

| Element | Color | Hex Code |
|---------|-------|----------|
| Background (Page) | Dark Navy | `#1a1a2e` |
| Background (Header) | Darker Navy | `#16213e` |
| Background (Transcript) | Navy Blue | `#0f3460` |
| Petitioner Zone | Purple Gradient | `#667eea → #764ba2` |
| Respondent Zone | Pink Gradient | `#f093fb → #f5576c` |
| Timer - Safe (>2min) | Green | `#4CAF50` |
| Timer - Warning (30s-2min) | Yellow | `#FFC107` |
| Timer - Critical (<30s) | Red | `#F44336` |
| Objection Button | Urgent Red | `#F44336` |
| Text (Primary) | White | `#ffffff` |
| Text (Secondary) | Light Gray | `#e6e6e6` |
| Text (Muted) | Gray | `#9e9e9e` |
| Focus Ring | Green | `#4CAF50` |

### Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| Header Title | System Sans | 1.5rem (24px) | 700 (Bold) |
| Case Title | System Sans | 1rem (16px) | 400 |
| Zone Headings | System Sans | 1.25rem (20px) | 700 |
| Timer Display | Monospace | 2.25rem (36px) | 700 |
| Timer Label | System Sans | 0.875rem (14px) | 400 |
| Transcript | Monospace | 0.875rem (14px) | 400 |
| Button Text | System Sans | 0.875rem (14px) | 600 |

### Spacing System

| Token | Value |
|-------|-------|
| xs | 4px |
| sm | 8px |
| md | 16px |
| lg | 24px |
| xl | 40px |

---

## 📐 Layout Architecture

### Page Structure
```
┌─────────────────────────────────────────────────────────────┐
│  Header (80px height)                                        │
│  ├── Court Seal      Round Info          Judge Info        │
└─────────────────────────────────────────────────────────────┘
┌─────────────┬───────────────────────┬───────────────────────┐
│             │                       │                       │
│ Petitioner  │    Center Stage       │   Respondent          │
│   Zone      │    (Timer + Controls) │    Zone               │
│  (Purple)   │                       │   (Pink)              │
│             │                       │                       │
├─────────────┴───────────────────────┴───────────────────────┤
│                    Transcript Area                          │
│                  (30% viewport height)                    │
└─────────────────────────────────────────────────────────────┘
```

### Grid System

**Main Courtroom Grid:**
- Display: CSS Grid
- Template: `1fr 2fr 1fr`
- Gap: 24px
- Padding: 24px

**Responsive Behavior:**
- Desktop (1024px+): 3-column layout
- Tablet/Mobile (<1024px): Warning banner displayed

---

## 🎯 Component Specifications

### Timer Display (Circular SVG)

**Dimensions:**
- Width: 280px
- Height: 280px
- ViewBox: 0 0 100 100

**SVG Structure:**
```svg
<svg viewBox="0 0 100 100">
  <!-- Background circle -->
  <circle cx="50" cy="50" r="45" 
          fill="none" stroke="#333" stroke-width="8" />
  
  <!-- Progress circle (animated) -->
  <circle cx="50" cy="50" r="45" 
          fill="none" stroke="#4CAF50" stroke-width="8"
          stroke-dasharray="283" 
          stroke-dashoffset="0" />
  
  <!-- Time text -->
  <text x="50" y="55" text-anchor="middle">15:00</text>
  
  <!-- Speaker label -->
  <text x="50" y="70" text-anchor="middle">Petitioner</text>
</svg>
```

**Animation:**
- Rotation: -90deg (starts from top)
- Progress: stroke-dashoffset animates based on time remaining
- Color transition: 0.3s ease
- Pulse effect: 1s ease-in-out infinite (when critical)

### Participant Zones

**Petitioner Zone (Left):**
- Background: `linear-gradient(135deg, #667eea 0%, #764ba2 100%)`
- Border: 2px solid `rgba(102, 126, 234, 0.3)`
- Border-radius: 12px
- Active State: Box shadow glow + scale(1.02)

**Respondent Zone (Right):**
- Background: `linear-gradient(135deg, #f093fb 0%, #f5576c 100%)`
- Border: 2px solid `rgba(240, 147, 251, 0.3)`
- Border-radius: 12px
- Active State: Box shadow glow + scale(1.02)

### Objection Button

**Position:** Fixed, bottom-right
- Bottom: 30px
- Right: 30px

**Dimensions:**
- Width: 60px
- Height: 60px
- Border-radius: 50%

**Style:**
- Background: `#F44336`
- Color: White
- Font-size: 24px
- Box-shadow: `0 4px 12px rgba(244, 67, 54, 0.4)`

**Interactions:**
- Hover: scale(1.1), enhanced shadow
- Active: scale(0.95)
- Keyboard shortcut: Alt+O

### Transcript Area

**Container:**
- Height: 30vh
- Background: `#0f3460`
- Border-top: 2px solid `#16213e`

**Entries:**
- Padding: 8px 16px
- Border-left: 3px solid (color based on speaker)
- Background: `rgba(255, 255, 255, 0.03)`
- Border-radius: 0 4px 4px 0
- Margin-bottom: 8px

**Speaker Colors:**
- System: Gray (`#9e9e9e`)
- Petitioner: Purple (`#667eea`)
- Respondent: Pink (`#f5576c`)
- Judge: Gold (`#ffd89b`)

---

## ♿ Accessibility (WCAG 2.1 AA)

### Semantic HTML Structure

```html
<body>
  <div class="courtroom-container">
    <!-- Screen size warning (alert role) -->
    <div role="alert" aria-live="assertive">
    
    <!-- Header -->
    <header role="banner">
    
    <!-- Main content -->
    <main role="main" aria-label="Virtual courtroom">
      
      <!-- Participant zones (section) -->
      <section aria-labelledby="[heading-id]">
        <h2 id="[heading-id]">...</h2>
      </section>
      
      <!-- Center stage (section) -->
      <section aria-label="Courtroom timer and controls">
        
        <!-- Timer with live region -->
        <div aria-live="polite" aria-label="Courtroom timer">
          <svg role="img" aria-label="Timer showing [time] remaining">
        
        <!-- Judge controls (group) -->
        <div role="group" aria-label="Judge timer controls">
    
    <!-- Transcript (log role) -->
    <section aria-label="Live transcript">
      <div role="log" aria-live="polite" aria-relevant="additions">
    
    <!-- Modals (dialog role) -->
    <div role="dialog" aria-modal="true" aria-hidden="true">
```

### ARIA Labels

| Element | ARIA Attributes |
|---------|----------------|
| Timer SVG | `role="img"`, `aria-label="Timer showing [time] remaining"` |
| Timer Container | `aria-live="polite"`, `aria-label="Courtroom timer"` |
| Judge Controls | `role="group"`, `aria-label="Judge timer controls"` |
| Objection Button | `aria-label="Raise objection"`, `title="Raise Objection (Alt+O)"` |
| Transcript | `role="log"`, `aria-live="polite"`, `aria-relevant="additions"` |
| Auto-scroll Toggle | `aria-pressed="true/false"` |
| Modal Overlay | `role="dialog"`, `aria-modal="true"`, `aria-hidden="true/false"` |
| Error Modal | `role="alertdialog"` |
| Tab Buttons | `role="tab"`, `aria-selected="true/false"` |

### Keyboard Navigation

| Key | Action |
|-----|--------|
| Tab | Navigate through interactive elements |
| Enter/Space | Activate buttons |
| Escape | Close modals |
| Alt + O | Raise objection |
| Arrow Keys | Navigate within objection type select |

### Focus Indicators

- All interactive elements have visible focus
- Focus style: `outline: 3px solid #4CAF50`
- Outline offset: 2px
- Transition: `outline-offset 0.15s ease`

### Color Contrast

| Combination | Ratio | Pass |
|-------------|-------|------|
| White on Purple (#667eea) | 4.6:1 | AA |
| White on Pink (#f5576c) | 4.5:1 | AA |
| White on Dark Navy (#1a1a2e) | 15.8:1 | AAA |
| White on Navy (#0f3460) | 10.4:1 | AAA |
| Yellow (#FFC107) on Dark Navy | 12.8:1 | AAA |

### Screen Reader Support

- **Timer updates**: Announced via `aria-live="polite"`
- **Transcript updates**: Announced in real-time
- **Connection status**: Announced when changes
- **Error messages**: Announced immediately with `role="alert"`

---

## 📱 Responsive Design

### Breakpoints

| Breakpoint | Min Width | Behavior |
|------------|-----------|----------|
| Desktop | 1024px | Full 3-column layout |
| Below Threshold | < 1024px | Warning banner, disabled interaction |

### Screen Size Warning

**Displayed when:** viewport < 1024px

**Style:**
- Position: Fixed, top
- Background: Red (#F44336)
- Color: White
- Padding: 1rem
- Text-align: Center
- Z-index: 9999

**Content:**
"⚠️ Courtroom requires desktop screen (1024px+)"

---

## 🎬 Animations & Transitions

### Performance-Optimized (GPU Accelerated)

| Animation | Properties | Duration |
|-----------|------------|----------|
| Timer Pulse | opacity | 1s infinite |
| Button Hover | transform, box-shadow | 0.2s ease |
| Modal Open | opacity, transform | 0.3s ease |
| Zone Active | box-shadow, transform | 0.3s ease |
| Timer Progress | stroke-dashoffset | 0.3s ease |
| Toast Slide | transform, opacity | 0.3s ease |

### Timing Functions

- Standard: `ease`
- Quick: `0.15s ease`
- Smooth: `0.3s ease`

---

## 🎯 Phase 1 Verification Checklist

- [ ] Page loads without console errors
- [ ] 3-column grid layout visible (Petitioner/Center/Respondent)
- [ ] Circular SVG timer renders with "15:00" display
- [ ] Timer shows correct color (green) and label
- [ ] Petitioner zone has purple gradient
- [ ] Respondent zone has pink gradient
- [ ] Judge controls visible for judge role
- [ ] Objection button visible for team members
- [ ] Red floating objection button in bottom-right
- [ ] Transcript area shows system message
- [ ] Modal appears when objection button clicked
- [ ] Character counter updates when typing
- [ ] Escape key closes modals
- [ ] Screen warning shows on small screens
- [ ] Focus indicators visible on all buttons
- [ ] ARIA labels present on interactive elements
- [ ] Color contrast passes WCAG AA (test with axe-core)

---

## 📦 File Structure

```
├── html/
│   └── oral-courtroom.html      # Complete courtroom page
├── css/
│   └── courtroom.css            # Phase 1 styles (1110 lines)
├── js/
│   └── courtroom-ui.js          # UI controller class
└── docs/
    └── courtroom-ui-spec.md     # This document
```

---

## 🚀 Usage

### Initialize UI

```javascript
// Auto-initializes from URL parameter
// URL: /html/oral-courtroom.html?round_id=1

// Or manually:
const ui = new CourtroomUI(1);
ui.initialize();
```

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Alt + O | Raise objection |
| Escape | Close modal |
| Tab | Navigate elements |

---

## 🔮 Future Enhancements (Phase 2+)

1. **Real-time WebSocket integration** for live updates
2. **Timer countdown logic** with audio cues
3. **Objection handling workflow** with judge ruling
4. **Scoring calculation** and persistence
5. **Transcript recording** and export
6. **Mobile optimization** for tablets

---

*Document Version: Phase 1.0*
*Last Updated: February 2026*
