# CBM Portal Dashboard Redesign — Design Spec
**Date:** 2026-04-02
**Scope:** Home screen only (`currentState === 'home'` in CBMKiosk). Inner screens (request flow, consumption, inventory) are out of scope for this iteration.

---

## 1. Goals

Redesign the CBM portal home screen to match the "Precision Curator" Stitch design system — editorial aesthetic, tonal layering, no dividers, Manrope headlines, Inter body — while preserving 100% of existing functional logic (blocked states, conditional visibility, navigation handlers, dark mode).

---

## 2. Design System Tokens (SCSS variables)

Translate the Stitch Tailwind palette into SCSS variables in `cbm_kiosk.scss`:

| Variable | Value |
|---|---|
| `$cbm-surface` | `#f7fafc` |
| `$cbm-surface-low` | `#eff4f7` |
| `$cbm-surface-lowest` | `#ffffff` |
| `$cbm-surface-container` | `#e7eff3` |
| `$cbm-surface-high` | `#dfeaef` |
| `$cbm-surface-highest` | `#d7e5eb` |
| `$cbm-primary` | `#455f88` |
| `$cbm-primary-dim` | `#39537c` |
| `$cbm-primary-container` | `#d6e3ff` |
| `$cbm-on-primary` | `#f6f7ff` |
| `$cbm-secondary` | `#546073` |
| `$cbm-secondary-container` | `#d8e3fa` |
| `$cbm-tertiary` | `#5d5c78` |
| `$cbm-tertiary-container` | `#d9d7f8` |
| `$cbm-on-surface` | `#283439` |
| `$cbm-on-surface-variant` | `#546166` |
| `$cbm-outline-variant` | `#a7b4ba` |
| `$cbm-error` | `#9f403d` |
| `$cbm-error-container` | `#fe8983` |

Fonts: add Google Fonts import for Manrope (400, 600, 700, 800) + Inter (400, 500, 600). Apply `font-family: 'Manrope', sans-serif` to `h1, h2, h3` within `.cbm_kiosk`. Body stays Inter.

Border radius scale:
- `$cbm-radius-lg`: `0.5rem`
- `$cbm-radius-xl`: `0.75rem`
- `$cbm-radius-full`: `9999px`

Shadow: `0 1px 3px rgba(40, 52, 57, 0.06), 0 1px 2px rgba(40, 52, 57, 0.04)` (no pure black shadows).

---

## 3. Layout

Replace the current `cbm_home_layout` (flex row) with a new two-column structure:

```
InventoryBanner  ← existing component, above everything, conditional self-show
cbm_kiosk_header (sticky)
cbm_home_layout_v2
├── cbm_home_main (flex-grow)
│   ├── cbm_welcome_section
│   ├── cbm_cards_primary (3 cards: Demande, Dispensation, Prescription)
│   └── cbm_cards_modules (secondary modules grid)
└── cbm_sidebar_v2 (fixed width ~360px)
    ├── cbm_suivi_tile
    ├── cbm_progress_section ("En Attente")
    └── cbm_recent_section ("Mises à jour récentes")
```

`InventoryBanner` position: rendered **before** the sticky header, so it pushes the header down rather than overlapping. No logic change to `InventoryBanner` — it manages its own visibility internally.

The sidebar is **always visible** — remove the `t-if="state.pendingApprovals.show_sidebar"` gate. On mobile (< 768px) the sidebar collapses below main content (stacks vertically).

---

## 4. Header

**Keep:**
- "Portail CBM" logo (Manrope bold, `$cbm-primary`)
- Ward name chip (`cbm_header_location`)
- Financial summary widget (executives only — logic unchanged)
- Dark mode toggle button
- Logout button

**Remove:**
- Search bar
- Nav menu links (Dashboard / Logistique / Finances)

No avatar added (not in current implementation).

Header background: `$cbm-surface-low`, no bottom border (tonal separation only). Sticky, `z-index: 50`.

---

## 5. Primary Cards

Suivi moves to the sidebar. The main grid shows **3 cards**: Demande, Dispensation, Prescription.

### Card structure (new class: `cbm_card_primary`)

```
cbm_card_primary
├── top row
│   ├── cbm_card_icon_wrap  ← colored container, 48px, radius-xl
│   │   └── svg icon
│   └── cbm_card_status_chip  ← pill badge, surface-low bg
├── cbm_card_title  ← Manrope bold, 20px
└── cbm_card_hint   ← Inter, on-surface-variant, 14px
```

Card base: `background: $cbm-surface-lowest`, `border-radius: $cbm-radius-xl`, shadow, `border: 1px solid transparent`.

Hover: `border-color: rgba($cbm-primary, 0.2)`, icon wrap transitions to solid color fill.

Icon container colors per card:
- Demande: `$cbm-primary-container` / icon color `$cbm-primary` → hover fill `$cbm-primary` / icon `$cbm-on-primary`
- Dispensation: `$cbm-tertiary-container` / icon `$cbm-tertiary` → hover fill `$cbm-tertiary` / icon `#fbf7ff`
- Prescription: `$cbm-secondary-container` / icon `$cbm-secondary` → hover fill `$cbm-secondary` / icon `$cbm-on-primary`

**Blocked state preserved:** red overlay on icon wrap + status chip shows "Accès bloqué" in error color. Class `cbm_card_primary--blocked` adds error border tint.

**Conditional visibility preserved:** `t-if="hasRequestOpType"`, `t-if="hasConsumptionOpTypes"`, `t-if="hasPatientConsumptionOpTypes"` — unchanged.

**Tooltips:** kept as-is, no visual change.

Status chip content (same data as before, now displayed as pill):
- Demande: pending request count or "Demander des produits"
- Dispensation: "Prêt à délivrer" or blocked message
- Prescription: new prescription count or hint

---

## 6. Secondary Modules Grid

Current tiles (Caisse, Achats, Documents, custom tiles) restyled. New class: `cbm_card_module`.

Structure:
```
cbm_card_module
├── svg icon (24px, $cbm-primary)
└── span label (Inter semibold, 14px)
```

Background: `$cbm-surface-low`, hover: `$cbm-surface-lowest` + `border-color: rgba($cbm-outline-variant, 0.15)`. Radius `$cbm-radius-xl`. Icon scales `1.1x` on hover (CSS transform).

Grid: `grid-cols-2` default, `grid-cols-3` at md breakpoint. Gap `1rem`.

Section header: Manrope bold 18px + primary accent bar (3px × 24px, `$cbm-primary`, radius-full) to the left of the title — matching Stitch "Modules Secondaires" header style.

Conditional visibility and click handlers unchanged.

---

## 7. Sidebar

### 7a. Suivi tile (`cbm_suivi_tile`)

Full-width compact card at the top of the sidebar. Matches `cbm_card_module` style but full-width with a right chevron. Clicking calls `goToHistory`. Shows clock icon + "Suivi" label + "Historique des opérations" hint.

### 7b. Progress bars section (`cbm_progress_section`)

Title: "En Attente" (Manrope bold 16px).

Each item (`cbm_progress_item`): clickable, navigates to same target as current chip.

```
cbm_progress_item
├── top row: label (left) + value text (right, bold)
└── cbm_progress_bar_track (h: 6px, radius-full, $cbm-surface-high)
    └── cbm_progress_bar_fill (colored, radius-full, CSS width %)
```

Max values for % calculation (caps bar at 100%, never shows 0% as empty when count > 0):
- Mes Demandes: max 20
- À Valider: max 20
- Réceptions: max 30
- Bons de commande: max 20
- Divergences Stock: max 10 (error color)
- Maintenance: max 10
- Suggestions: max 20

Bar colors:
- Default: `$cbm-primary`
- Divergences Stock: `$cbm-error`
- Maintenance: `$cbm-secondary`
- Suggestions (critical): `$cbm-error`, else `$cbm-tertiary`

Conditional visibility: all existing `t-if` conditions on chips are preserved on progress items.

Value text: show count + unit (e.g. "4 à investiguer", "12 dossiers", "24/30"). Reuse existing text logic.

### 7c. Recent updates section (`cbm_recent_section`)

Title: "Mises à jour récentes" (Inter 11px uppercase tracking-wide, `$cbm-on-surface-variant`).

**New state field:** `state.recentActivity: []`

**New method:** `loadRecentActivity()` — calls `/cbm/get_history` with `limit=5`, maps each picking to:
```js
{
  name: picking.name,
  state: picking.state,
  portal_behavior: picking.portal_behavior,
  create_date: picking.create_date,
  partner_name: picking.partner_name,
}
```
Formats `create_date` into relative time string ("Il y a X min", "Il y a X h", "Hier").

Called in `onMounted` (non-blocking, parallel to other loads).

Each item (`cbm_recent_item`):
```
cbm_recent_item
├── cbm_recent_dot  ← 8px circle, color by state
└── div
    ├── p.cbm_recent_name  ← picking name, bold, 13px
    └── p.cbm_recent_meta  ← relative time + portal_behavior label, on-surface-variant 12px
```

Dot colors:
- `done` → `$cbm-primary` (green-tinted using primary)
- `assigned` / `confirmed` / `waiting` → amber (`#c08a20`)
- `cancel` → `$cbm-error`
- `draft` → `$cbm-outline-variant`

Empty state: "Aucune activité récente" in `$cbm-on-surface-variant`.

---

## 8. Files Changed

| File | Change |
|---|---|
| `static/src/scss/cbm_dashboard.scss` | **New file** — all design tokens (SCSS variables), new card/sidebar/progress/recent classes |
| `static/src/scss/cbm_kiosk.scss` | Header-only updates (remove search/nav styles); no new tokens or layout classes added here |
| `__manifest__.py` | Register `cbm_dashboard.scss` in web assets |
| `static/src/xml/cbm_kiosk.xml` | Restructure home screen HTML — new layout, cards, sidebar |
| `static/src/js/cbm_kiosk.js` | Add `recentActivity` state, `loadRecentActivity()` method |
| `controllers/main.py` | No change — `/cbm/get_history` already exists with limit param |

**Rationale for new file:** `cbm_kiosk.scss` is already large. All dashboard-specific design system tokens and new component classes live in `cbm_dashboard.scss` to keep concerns separated and the new design system self-contained.

---

## 9. Out of Scope

- Inner screens (request, consumption, prescription, inventory flows)
- Dark mode token updates (preserve existing dark mode behavior, update later)
- Mobile bottom nav bar (no change)
- InventoryBanner component (no change)
- Accountability / financial dashboard (no change)
