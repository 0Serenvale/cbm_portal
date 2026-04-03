# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the CBM portal home screen to match the "Precision Curator" Stitch design system — editorial cards, tonal layering, progress-bar sidebar, live recent activity — while preserving all existing functional logic.

**Architecture:** New `cbm_dashboard.scss` holds all design tokens and new component classes. `cbm_kiosk.xml` home screen section is restructured in-place (no new files). `cbm_kiosk.js` gains one new state field and one new method for recent activity. No backend changes needed.

**Tech Stack:** OWL (Odoo 16), SCSS, Odoo JSON-RPC (`/cbm/get_history` already exists)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `static/src/scss/cbm_dashboard.scss` | **Create** | All design tokens + new component classes (cards, sidebar, progress bars, recent items) |
| `__manifest__.py` | **Modify** | Register `cbm_dashboard.scss` in `web.assets_backend` |
| `static/src/xml/cbm_kiosk.xml` | **Modify** | Restructure home screen: new layout, header cleanup, primary cards, secondary grid, sidebar |
| `static/src/js/cbm_kiosk.js` | **Modify** | Add `recentActivity: []` state + `loadRecentActivity()` method called in `onWillStart` |

---

## Task 1: Create `cbm_dashboard.scss` with design tokens

**Files:**
- Create: `static/src/scss/cbm_dashboard.scss`

- [ ] **Step 1: Create the file with all design tokens and base typography**

```scss
// =============================================================================
// CBM Dashboard Design System — "Precision Curator"
// Tokens from: dashboard/stitch_inventory_counting_dashboard/DESIGN.md
// =============================================================================

// --- Google Fonts ---
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Inter:wght@400;500;600&display=swap');

// --- Color Tokens ---
$cbm-surface:              #f7fafc;
$cbm-surface-low:          #eff4f7;
$cbm-surface-lowest:       #ffffff;
$cbm-surface-container:    #e7eff3;
$cbm-surface-high:         #dfeaef;
$cbm-surface-highest:      #d7e5eb;

$cbm-primary:              #455f88;
$cbm-primary-dim:          #39537c;
$cbm-primary-container:    #d6e3ff;
$cbm-on-primary:           #f6f7ff;

$cbm-secondary:            #546073;
$cbm-secondary-container:  #d8e3fa;
$cbm-on-secondary:         #f8f8ff;

$cbm-tertiary:             #5d5c78;
$cbm-tertiary-container:   #d9d7f8;
$cbm-on-tertiary:          #fbf7ff;

$cbm-on-surface:           #283439;
$cbm-on-surface-variant:   #546166;
$cbm-outline-variant:      #a7b4ba;

$cbm-error:                #9f403d;
$cbm-error-container:      #fe8983;
$cbm-amber:                #c08a20;

// --- Border Radius ---
$cbm-radius-lg:            0.5rem;
$cbm-radius-xl:            0.75rem;
$cbm-radius-full:          9999px;

// --- Shadow (no pure black) ---
$cbm-shadow-sm: 0 1px 3px rgba(40, 52, 57, 0.06), 0 1px 2px rgba(40, 52, 57, 0.04);

// --- Typography ---
// Applied within .cbm_kiosk scope to avoid bleeding into Odoo backend
.cbm_kiosk {
    h1, h2, h3, h4,
    .cbm_portal_title,
    .cbm_card_title,
    .cbm_section_title,
    .cbm_sidebar_heading {
        font-family: 'Manrope', sans-serif;
    }

    font-family: 'Inter', sans-serif;
}

// =============================================================================
// LAYOUT
// =============================================================================

.cbm_home_layout_v2 {
    display: flex;
    flex-direction: row;
    gap: 2rem;
    align-items: flex-start;
    padding: 2rem 2.5rem;

    @media (max-width: 992px) {
        flex-direction: column;
        padding: 1rem;
    }
}

.cbm_home_main {
    flex: 1 1 0;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2rem;
}

.cbm_sidebar_v2 {
    width: 340px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;

    @media (max-width: 992px) {
        width: 100%;
    }
}

// =============================================================================
// HEADER (v2 — simplified)
// =============================================================================

.cbm_kiosk_header_v2 {
    position: sticky;
    top: 0;
    z-index: 50;
    background: $cbm-surface-low;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.625rem 2.5rem;
    // No border — tonal separation only

    .cbm_portal_title {
        font-size: 1.25rem;
        font-weight: 800;
        color: $cbm-primary;
        letter-spacing: -0.02em;
        margin: 0;
    }

    .cbm_header_actions {
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }

    .cbm_header_location {
        display: flex;
        align-items: center;
        gap: 0.25rem;
        font-size: 0.8125rem;
        color: $cbm-on-surface-variant;
        background: $cbm-surface-container;
        padding: 0.25rem 0.75rem;
        border-radius: $cbm-radius-full;
    }

    .cbm_theme_toggle {
        background: none;
        border: none;
        cursor: pointer;
        padding: 0.4rem;
        border-radius: $cbm-radius-full;
        color: $cbm-primary;
        display: flex;
        align-items: center;
        justify-content: center;

        &:hover {
            background: $cbm-surface-container;
        }
    }

    .cbm_logout_btn {
        font-size: 0.8125rem;
        padding: 0.375rem 0.875rem;
        border-radius: $cbm-radius-full;
        border: 1px solid rgba($cbm-outline-variant, 0.5);
        color: $cbm-on-surface-variant;
        text-decoration: none;
        display: flex;
        align-items: center;
        gap: 0.25rem;
        transition: background 0.15s;

        &:hover {
            background: $cbm-surface-container;
        }
    }

    .cbm_financial_header {
        cursor: pointer;
        font-size: 0.8125rem;
        color: $cbm-on-surface-variant;

        &:hover {
            color: $cbm-on-surface;
        }
    }
}

// =============================================================================
// WELCOME SECTION
// =============================================================================

.cbm_welcome_section {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;

    h1 {
        font-size: 2rem;
        font-weight: 800;
        color: $cbm-primary;
        letter-spacing: -0.03em;
        margin: 0;
        line-height: 1.2;
    }

    p {
        font-size: 0.9375rem;
        color: $cbm-on-surface-variant;
        margin: 0;
    }
}

// =============================================================================
// PRIMARY CARDS (Demande, Dispensation, Prescription)
// =============================================================================

.cbm_cards_primary {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1.25rem;

    @media (max-width: 768px) {
        grid-template-columns: 1fr;
    }
}

.cbm_card_primary {
    background: $cbm-surface-lowest;
    border-radius: $cbm-radius-xl;
    border: 1px solid transparent;
    box-shadow: $cbm-shadow-sm;
    padding: 1.5rem;
    cursor: pointer;
    transition: border-color 0.2s ease;
    display: flex;
    flex-direction: column;
    gap: 0.875rem;

    &:hover {
        border-color: rgba($cbm-primary, 0.2);

        .cbm_card_icon_wrap {
            background: var(--cbm-card-color-solid);
            color: var(--cbm-card-icon-on-solid);
        }
    }

    // Blocked state
    &.cbm_card_primary--blocked {
        border-color: rgba($cbm-error, 0.2);

        .cbm_card_icon_wrap {
            position: relative;

            &::after {
                content: '';
                position: absolute;
                inset: 0;
                border-radius: $cbm-radius-lg;
                background: rgba($cbm-error, 0.15);
            }
        }
    }
}

.cbm_card_top_row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.5rem;
}

.cbm_card_icon_wrap {
    width: 48px;
    height: 48px;
    border-radius: $cbm-radius-lg;
    background: var(--cbm-card-color-container);
    color: var(--cbm-card-color);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: background 0.2s ease, color 0.2s ease;
    position: relative;

    svg {
        width: 24px;
        height: 24px;
        fill: currentColor;
    }
}

// Per-card color variables (set via style attribute on .cbm_card_primary)
// Demande:      --cbm-card-color: #455f88; --cbm-card-color-container: #d6e3ff; --cbm-card-color-solid: #455f88; --cbm-card-icon-on-solid: #f6f7ff
// Dispensation: --cbm-card-color: #5d5c78; --cbm-card-color-container: #d9d7f8; --cbm-card-color-solid: #5d5c78; --cbm-card-icon-on-solid: #fbf7ff
// Prescription: --cbm-card-color: #546073; --cbm-card-color-container: #d8e3fa; --cbm-card-color-solid: #546073; --cbm-card-icon-on-solid: #f8f8ff

.cbm_card_status_chip {
    font-size: 0.6875rem;
    font-weight: 600;
    color: $cbm-on-surface-variant;
    background: $cbm-surface-low;
    padding: 0.2rem 0.625rem;
    border-radius: $cbm-radius-full;
    white-space: nowrap;
    flex-shrink: 0;

    &.cbm_chip_blocked {
        color: $cbm-error;
        background: rgba($cbm-error, 0.08);
    }
}

.cbm_card_title {
    font-size: 1.125rem;
    font-weight: 700;
    color: $cbm-on-surface;
    margin: 0;
}

.cbm_card_hint {
    font-size: 0.875rem;
    color: $cbm-on-surface-variant;
    line-height: 1.5;
    margin: 0;
}

// =============================================================================
// SECONDARY MODULES GRID
// =============================================================================

.cbm_section_header {
    display: flex;
    align-items: center;
    gap: 0.625rem;
    margin-bottom: 0.875rem;

    .cbm_section_accent {
        width: 3px;
        height: 24px;
        background: $cbm-primary;
        border-radius: $cbm-radius-full;
        flex-shrink: 0;
    }

    .cbm_section_title {
        font-size: 1.0625rem;
        font-weight: 700;
        color: $cbm-on-surface;
        margin: 0;
    }
}

.cbm_cards_modules_grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.875rem;

    @media (min-width: 576px) {
        grid-template-columns: repeat(3, 1fr);
    }
}

.cbm_card_module {
    background: $cbm-surface-low;
    border-radius: $cbm-radius-xl;
    border: 1px solid transparent;
    padding: 1.125rem;
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease;
    display: flex;
    flex-direction: column;
    gap: 0.625rem;

    svg {
        width: 24px;
        height: 24px;
        fill: $cbm-primary;
        transition: transform 0.15s ease;
    }

    span.cbm_module_label {
        font-size: 0.875rem;
        font-weight: 600;
        color: $cbm-on-surface;
    }

    &:hover {
        background: $cbm-surface-lowest;
        border-color: rgba($cbm-outline-variant, 0.15);

        svg {
            transform: scale(1.1);
        }
    }
}

// =============================================================================
// SIDEBAR
// =============================================================================

.cbm_sidebar_v2 {
    // Suivi tile
    .cbm_suivi_tile {
        background: $cbm-surface-lowest;
        border-radius: $cbm-radius-xl;
        border: 1px solid transparent;
        box-shadow: $cbm-shadow-sm;
        padding: 1rem 1.25rem;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 0.75rem;
        transition: border-color 0.15s ease;

        svg {
            width: 22px;
            height: 22px;
            fill: $cbm-primary;
            flex-shrink: 0;
        }

        .cbm_suivi_text {
            flex: 1;

            .cbm_suivi_label {
                font-size: 0.9375rem;
                font-weight: 700;
                color: $cbm-on-surface;
                display: block;
            }

            .cbm_suivi_hint {
                font-size: 0.75rem;
                color: $cbm-on-surface-variant;
            }
        }

        .cbm_suivi_chevron {
            color: $cbm-on-surface-variant;
            font-size: 1rem;
        }

        &:hover {
            border-color: rgba($cbm-primary, 0.2);
        }
    }

    // Progress section
    .cbm_sidebar_card {
        background: $cbm-surface-lowest;
        border-radius: $cbm-radius-xl;
        box-shadow: $cbm-shadow-sm;
        padding: 1.5rem;
    }

    .cbm_sidebar_heading {
        font-size: 1rem;
        font-weight: 700;
        color: $cbm-on-surface;
        margin: 0 0 1.25rem 0;
    }

    .cbm_progress_list {
        display: flex;
        flex-direction: column;
        gap: 1.25rem;
    }

    .cbm_progress_item {
        cursor: pointer;

        &:hover .cbm_progress_bar_fill {
            filter: brightness(1.1);
        }
    }

    .cbm_progress_item_header {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        margin-bottom: 0.5rem;
    }

    .cbm_progress_label {
        font-size: 0.8125rem;
        font-weight: 500;
        color: $cbm-on-surface-variant;
    }

    .cbm_progress_value {
        font-size: 0.8125rem;
        font-weight: 700;
        color: $cbm-on-surface;

        &.cbm_progress_value--error {
            color: $cbm-error;
        }
    }

    .cbm_progress_bar_track {
        height: 6px;
        background: $cbm-surface-high;
        border-radius: $cbm-radius-full;
        overflow: hidden;
    }

    .cbm_progress_bar_fill {
        height: 100%;
        border-radius: $cbm-radius-full;
        background: $cbm-primary;
        transition: width 0.4s ease;

        &.cbm_bar_error    { background: $cbm-error; }
        &.cbm_bar_secondary { background: $cbm-secondary; }
        &.cbm_bar_tertiary  { background: $cbm-tertiary; }
        &.cbm_bar_amber     { background: $cbm-amber; }
    }

    // Recent updates section
    .cbm_recent_heading {
        font-size: 0.6875rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: $cbm-on-surface-variant;
        margin: 0 0 1rem 0;
    }

    .cbm_recent_list {
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }

    .cbm_recent_item {
        display: flex;
        gap: 0.875rem;
        align-items: flex-start;
    }

    .cbm_recent_dot {
        width: 8px;
        height: 8px;
        border-radius: $cbm-radius-full;
        flex-shrink: 0;
        margin-top: 0.3rem;

        &.dot_done     { background: $cbm-primary; }
        &.dot_pending  { background: $cbm-amber; }
        &.dot_cancel   { background: $cbm-error; }
        &.dot_draft    { background: $cbm-outline-variant; }
    }

    .cbm_recent_name {
        font-size: 0.8125rem;
        font-weight: 700;
        color: $cbm-on-surface;
        margin: 0 0 0.125rem 0;
    }

    .cbm_recent_meta {
        font-size: 0.75rem;
        color: $cbm-on-surface-variant;
        margin: 0;
    }

    .cbm_recent_empty {
        font-size: 0.8125rem;
        color: $cbm-on-surface-variant;
        text-align: center;
        padding: 0.5rem 0;
    }
}
```

- [ ] **Step 2: Verify the file exists**

```bash
ls static/src/scss/cbm_dashboard.scss
```
Expected: file listed.

---

## Task 2: Register `cbm_dashboard.scss` in `__manifest__.py`

**Files:**
- Modify: `__manifest__.py`

- [ ] **Step 1: Add the new SCSS file to web assets**

In `__manifest__.py`, in the `'web.assets_backend'` list, add `cbm_dashboard.scss` immediately after `cbm_kiosk.scss`:

```python
'clinic_staff_portal/static/src/scss/cbm_kiosk.scss',
'clinic_staff_portal/static/src/scss/cbm_dashboard.scss',   # ← add this line
'clinic_staff_portal/static/src/scss/cbm_cashier.scss',
```

- [ ] **Step 2: Commit**

```bash
git add static/src/scss/cbm_dashboard.scss __manifest__.py
git commit -m "feat(dashboard): add cbm_dashboard.scss design tokens + register in manifest"
```

---

## Task 3: Add `recentActivity` state and `loadRecentActivity()` to `cbm_kiosk.js`

**Files:**
- Modify: `static/src/js/cbm_kiosk.js`

- [ ] **Step 1: Add `recentActivity: []` to the state object**

Find the line (around line 313):
```js
            // Inventory Session (for inventory counting)
            inventorySession: null,  // Populated on goToInventory()
        });
```

Add `recentActivity` before `inventorySession`:
```js
            // Dashboard recent activity feed
            recentActivity: [],

            // Inventory Session (for inventory counting)
            inventorySession: null,  // Populated on goToInventory()
        });
```

- [ ] **Step 2: Add `loadRecentActivity()` method**

Find the `showToast` method (around line 358) and add `loadRecentActivity` before it:

```js
    async loadRecentActivity() {
        try {
            const items = await this.rpc('/cbm/get_history', { limit: 5 });
            this.state.recentActivity = (items || []).map(p => ({
                name: p.name,
                state: p.state,
                portal_behavior: p.portal_behavior,
                create_date: p.create_date,
                partner_name: p.partner_name || false,
            }));
        } catch (e) {
            // Non-blocking — dashboard still works without recent activity
            this.state.recentActivity = [];
        }
    }

    _formatRelativeTime(isoString) {
        if (!isoString) return '';
        const date = new Date(isoString);
        const diffMs = Date.now() - date.getTime();
        const diffMin = Math.floor(diffMs / 60000);
        if (diffMin < 1) return 'À l\'instant';
        if (diffMin < 60) return `Il y a ${diffMin} min`;
        const diffH = Math.floor(diffMin / 60);
        if (diffH < 24) return `Il y a ${diffH}h`;
        if (diffH < 48) return 'Hier';
        return `Il y a ${Math.floor(diffH / 24)}j`;
    }

    _recentDotClass(state) {
        if (state === 'done') return 'dot_done';
        if (['assigned', 'confirmed', 'waiting'].includes(state)) return 'dot_pending';
        if (state === 'cancel') return 'dot_cancel';
        return 'dot_draft';
    }
```

- [ ] **Step 3: Call `loadRecentActivity()` in `onWillStart`**

Find the `onWillStart` block (around line 317):
```js
        onWillStart(async () => {
            await this.loadUserContext();
            await this.loadCustomTiles();
            await this.loadPendingApprovals();
            await this.loadFinancials();
            await this.loadBrainStatus();
            await this.checkCashierAccess();
            // Log kiosk access (IP, screen resolution) - fire and forget
            this.logKioskAccess();
        });
```

Add `loadRecentActivity` as a non-blocking fire-and-forget (same pattern as `logKioskAccess`):
```js
        onWillStart(async () => {
            await this.loadUserContext();
            await this.loadCustomTiles();
            await this.loadPendingApprovals();
            await this.loadFinancials();
            await this.loadBrainStatus();
            await this.checkCashierAccess();
            // Log kiosk access (IP, screen resolution) - fire and forget
            this.logKioskAccess();
            // Load recent activity for dashboard sidebar - fire and forget
            this.loadRecentActivity();
        });
```

- [ ] **Step 4: Commit**

```bash
git add static/src/js/cbm_kiosk.js
git commit -m "feat(dashboard): add recentActivity state and loadRecentActivity() method"
```

---

## Task 4: Restructure the home screen XML — header + layout shell

**Files:**
- Modify: `static/src/xml/cbm_kiosk.xml` (home screen section only — `t-elif="state.currentState === 'home'"`)

- [ ] **Step 1: Replace the header and layout wrapper**

The current home screen starts at line 58. Replace the opening structure — from `<div t-elif="state.currentState === 'home'"...>` through the `<InventoryBanner/>` and `<div class="cbm_home_layout">` opening tag — with:

```xml
<!-- Home Screen -->
<div t-elif="state.currentState === 'home'" class="cbm_kiosk_home">

    <!-- Announcement / Inventory Warning Banner -->
    <InventoryBanner/>

    <!-- Header (v2 — simplified, no search/nav) -->
    <header class="cbm_kiosk_header_v2">
        <h1 class="cbm_portal_title">Portail CBM</h1>
        <div class="cbm_header_actions">
            <!-- Financial Summary (Executives Only) -->
            <div t-if="state.financials.is_executive"
                 class="cbm_financial_header"
                 t-on-click="goToFinancialDashboard"
                 title="Accountability Dashboard - Transferts en Attente">
                <span class="cbm_fin_at_risk">
                    <span class="cbm_icon_warning cbm_icon_warning_sm"/>
                    <t t-esc="state.financials.pending_count || 0"/> transferts ·
                    <t t-esc="(state.financials.total_at_risk || 0).toLocaleString()"/>
                    <t t-esc="state.financials.currency_symbol || 'DA'"/>
                </span>
            </div>

            <!-- Ward Location -->
            <div class="cbm_header_location" t-if="state.userContext?.ward_name">
                <span class="cbm_icon_location me-1"/>
                <span t-esc="state.userContext.ward_name"/>
            </div>

            <!-- Theme Toggle -->
            <button class="cbm_theme_toggle" t-on-click="toggleKioskTheme" title="Changer le thème">
                <t t-if="state.kioskDarkMode">
                    <span class="cbm_icon_sun"/>
                </t>
                <t t-else="">
                    <span class="cbm_icon_moon"/>
                </t>
            </button>

            <!-- Logout -->
            <a href="/web/session/logout" class="cbm_logout_btn" title="Déconnexion">
                <span class="cbm_icon_logout cbm_icon_logout_sm me-1"/>Déconnexion
            </a>
        </div>
    </header>

    <!-- Two-column layout -->
    <div class="cbm_home_layout_v2">
```

Note: the old `<div class="cbm_kiosk_header">` block (which included the welcome text) is fully replaced. The welcome text moves inside `cbm_home_main` in Task 5.

- [ ] **Step 2: Commit checkpoint**

```bash
git add static/src/xml/cbm_kiosk.xml
git commit -m "feat(dashboard): replace header with v2 simplified header + layout shell"
```

---

## Task 5: Add welcome section and primary cards to XML

**Files:**
- Modify: `static/src/xml/cbm_kiosk.xml`

- [ ] **Step 1: Add `cbm_home_main` with welcome section + primary cards grid**

Inside `<div class="cbm_home_layout_v2">`, add the left column:

```xml
        <!-- LEFT: Main content -->
        <div class="cbm_home_main">

            <!-- Welcome -->
            <section class="cbm_welcome_section">
                <h1>Bonjour, <t t-esc="state.userContext?.user_name"/></h1>
                <p>Bienvenue sur votre portail CBM. Voici l'état actuel de vos opérations.</p>
            </section>

            <!-- Primary Cards: Demande, Dispensation, Prescription -->
            <section class="cbm_cards_primary">

                <!-- Demande d'Approvisionnement -->
                <div t-if="hasRequestOpType" class="cbm_tooltip_trigger">
                    <div t-att-class="'cbm_card_primary' + ((state.pendingApprovals.request_status || state.pendingApprovals.transfer_status) === 'blocked' ? ' cbm_card_primary--blocked' : '')"
                         style="--cbm-card-color:#455f88;--cbm-card-color-container:#d6e3ff;--cbm-card-color-solid:#455f88;--cbm-card-icon-on-solid:#f6f7ff"
                         t-on-click="(state.pendingApprovals.request_status || state.pendingApprovals.transfer_status) === 'blocked' ? showBlockedNotification : goToRequest">
                        <div class="cbm_card_top_row">
                            <div class="cbm_card_icon_wrap">
                                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="m16 2h-.171a3.006 3.006 0 0 0 -2.829-2h-2a3.006 3.006 0 0 0 -2.829 2h-.171a5.006 5.006 0 0 0 -5 5v12a5.006 5.006 0 0 0 5 5h8a5.006 5.006 0 0 0 5-5v-12a5.006 5.006 0 0 0 -5-5zm-7 5h2v-2a1 1 0 0 1 2 0v2h2a1 1 0 0 1 0 2h-2v2a1 1 0 0 1 -2 0v-2h-2a1 1 0 0 1 0-2zm3 13h-4a1 1 0 0 1 0-2h4a1 1 0 0 1 0 2zm4-4h-8a1 1 0 0 1 0-2h8a1 1 0 0 1 0 2z"/></svg>
                            </div>
                            <span t-att-class="'cbm_card_status_chip' + ((state.pendingApprovals.request_status || state.pendingApprovals.transfer_status) === 'blocked' ? ' cbm_chip_blocked' : '')">
                                <t t-if="(state.pendingApprovals.request_status || state.pendingApprovals.transfer_status) === 'blocked'">Accès bloqué</t>
                                <t t-else="">Demander des produits</t>
                            </span>
                        </div>
                        <p class="cbm_card_title">Demande</p>
                        <p class="cbm_card_hint">Réapprovisionner votre stock depuis la pharmacie.</p>
                    </div>
                    <!-- Tooltip (unchanged) -->
                    <div class="cbm_tooltip cbm_tooltip_bottom">
                        <div class="cbm_tooltip_card">
                            <div class="cbm_tooltip_header">
                                <div class="cbm_tooltip_icon">
                                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 0 0 2.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 0 0-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75 2.25 2.25 0 0 0-.1-.664m-5.8 0A2.251 2.251 0 0 1 13.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25Z"/></svg>
                                </div>
                                <h3 class="cbm_tooltip_title" t-if="(state.pendingApprovals.request_status || state.pendingApprovals.transfer_status) === 'blocked'">Accès Bloqué</h3>
                                <h3 class="cbm_tooltip_title" t-else="">Demande d'Approvisionnement</h3>
                            </div>
                            <div class="cbm_tooltip_content">
                                <p class="cbm_tooltip_text" t-if="(state.pendingApprovals.request_status || state.pendingApprovals.transfer_status) === 'blocked'">Traitez vos demandes en attente avant de créer une nouvelle demande.</p>
                                <p class="cbm_tooltip_text" t-else="">Demander des produits à la pharmacie centrale pour réapprovisionner votre stock.</p>
                            </div>
                            <div class="cbm_tooltip_arrow"></div>
                        </div>
                    </div>
                </div>

                <!-- Dispensation -->
                <div t-if="hasConsumptionOpTypes" class="cbm_tooltip_trigger">
                    <div t-att-class="'cbm_card_primary' + ((state.pendingApprovals.consumption_status || state.pendingApprovals.transfer_status) === 'blocked' ? ' cbm_card_primary--blocked' : '')"
                         style="--cbm-card-color:#5d5c78;--cbm-card-color-container:#d9d7f8;--cbm-card-color-solid:#5d5c78;--cbm-card-icon-on-solid:#fbf7ff"
                         t-on-click="(state.pendingApprovals.consumption_status || state.pendingApprovals.transfer_status) === 'blocked' ? showBlockedNotification : goToConsumptionMenu">
                        <div class="cbm_card_top_row">
                            <div class="cbm_card_icon_wrap">
                                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="m24,24h-10v-2c0-1.654,1.346-3,3-3h4c1.654,0,3,1.346,3,3v2Zm-5-6c-1.379,0-2.5-1.121-2.5-2.5s1.121-2.5,2.5-2.5,2.5,1.121,2.5,2.5-1.121,2.5-2.5,2.5Zm-7,4c0-2.029,1.22-3.772,2.96-4.555-.286-.591-.46-1.246-.46-1.945,0-1.325.586-2.505,1.5-3.33V3c0-1.654-1.346-3-3-3H3C1.346,0,0,1.346,0,3v21h12v-2Zm0-7h-3v-2h3v2Zm-5,4h-3v-2h3v2Zm0-4h-3v-2h3v2Zm-2-7v-2h2v-2h2v2h2v2h-2v2h-2v-2h-2Zm4,9h3v2h-3v-2Z"/></svg>
                            </div>
                            <span t-att-class="'cbm_card_status_chip' + ((state.pendingApprovals.consumption_status || state.pendingApprovals.transfer_status) === 'blocked' ? ' cbm_chip_blocked' : '')">
                                <t t-if="(state.pendingApprovals.consumption_status || state.pendingApprovals.transfer_status) === 'blocked'">Accès bloqué</t>
                                <t t-else="">Prêt à délivrer</t>
                            </span>
                        </div>
                        <p class="cbm_card_title">Dispensation</p>
                        <p class="cbm_card_hint">Délivrer des médicaments aux patients.</p>
                    </div>
                    <!-- Tooltip (unchanged) -->
                    <div class="cbm_tooltip cbm_tooltip_bottom">
                        <div class="cbm_tooltip_card">
                            <div class="cbm_tooltip_header">
                                <div class="cbm_tooltip_icon"><span class="cbm_icon_user"/></div>
                                <h3 class="cbm_tooltip_title" t-if="(state.pendingApprovals.consumption_status || state.pendingApprovals.transfer_status) === 'blocked'">Accès Bloqué</h3>
                                <h3 class="cbm_tooltip_title" t-else="">Dispensation Patient</h3>
                            </div>
                            <div class="cbm_tooltip_content">
                                <p class="cbm_tooltip_text" t-if="(state.pendingApprovals.consumption_status || state.pendingApprovals.transfer_status) === 'blocked'">Traitez vos demandes en attente avant de créer une nouvelle dispensation.</p>
                                <p class="cbm_tooltip_text" t-else="">Enregistrer la délivrance de médicaments aux patients depuis votre stock.</p>
                            </div>
                            <div class="cbm_tooltip_arrow"></div>
                        </div>
                    </div>
                </div>

                <!-- Prescription -->
                <div t-if="hasPatientConsumptionOpTypes" class="cbm_tooltip_trigger">
                    <div class="cbm_card_primary"
                         style="--cbm-card-color:#546073;--cbm-card-color-container:#d8e3fa;--cbm-card-color-solid:#546073;--cbm-card-icon-on-solid:#f8f8ff"
                         t-on-click="goToPrescription">
                        <div class="cbm_card_top_row">
                            <div class="cbm_card_icon_wrap">
                                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M19.5,0H7.5A2,2,0,0,0,5.5,2V22a2,2,0,0,0,2,2h12a2,2,0,0,0,2-2V2A2,2,0,0,0,19.5,0Zm-6,20H9.5a1,1,0,0,1,0-2h4a1,1,0,0,1,0,2Zm4-4H9.5a1,1,0,0,1,0-2h8a1,1,0,0,1,0,2ZM17,12H10a1,1,0,0,1,0-2h7a1,1,0,0,1,0,2Zm0-4H10A1,1,0,0,1,10,6h7a1,1,0,0,1,0,2ZM5,2.5V4H4A2,2,0,0,0,2,6V20a2,2,0,0,0,2,2H5v-1.5H4a.5.5,0,0,1-.5-.5V6A.5.5,0,0,1,4,5.5H5Z"/></svg>
                            </div>
                            <span class="cbm_card_status_chip">Ordonnances Bahmni</span>
                        </div>
                        <p class="cbm_card_title">Prescription</p>
                        <p class="cbm_card_hint">Administrer les médicaments prescrits par les médecins.</p>
                    </div>
                    <!-- Tooltip (unchanged) -->
                    <div class="cbm_tooltip cbm_tooltip_bottom">
                        <div class="cbm_tooltip_card">
                            <div class="cbm_tooltip_header">
                                <div class="cbm_tooltip_icon"><span class="cbm_icon_user"/></div>
                                <h3 class="cbm_tooltip_title">Prescription Patient</h3>
                            </div>
                            <div class="cbm_tooltip_content">
                                <p class="cbm_tooltip_text">Administrer les médicaments prescrits par les médecins depuis Bahmni et ajouter les consommables.</p>
                            </div>
                            <div class="cbm_tooltip_arrow"></div>
                        </div>
                    </div>
                </div>

            </section>
```

- [ ] **Step 2: Commit checkpoint**

```bash
git add static/src/xml/cbm_kiosk.xml
git commit -m "feat(dashboard): add welcome section and primary cards (Demande, Dispensation, Prescription)"
```

---

## Task 6: Add secondary modules grid to XML

**Files:**
- Modify: `static/src/xml/cbm_kiosk.xml`

- [ ] **Step 1: Add secondary modules section inside `cbm_home_main`, after primary cards**

```xml
            <!-- Secondary Modules -->
            <section class="cbm_cards_modules">
                <div class="cbm_section_header">
                    <div class="cbm_section_accent"/>
                    <h2 class="cbm_section_title">Modules</h2>
                </div>
                <div class="cbm_cards_modules_grid">

                    <!-- Cashier -->
                    <div t-if="state.hasCashierAccess" class="cbm_tooltip_trigger">
                        <div class="cbm_card_module" t-on-click="goToCashier">
                            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="m12,21c4.971,0,9-4.029,9-9v-.018c-.002-.704-.103-1.383-.258-2.041-.147.023-.292.06-.442.06-.77,0-1.542-.292-2.129-.88-1.132-1.132-1.158-2.945-.099-4.121h2.876l-1.363,1.293c-.39.391-.39,1.024,0,1.414.391.391,1.024.391,1.414,0l2.451-2.381c.729-.729.729-1.922,0-2.651l-2.451-2.381c-.391-.391-1.024-.391-1.414,0s-.391,1.024,0,1.414l1.363,1.293h-8.948C7.03,3,3,7.029,3,12v.018c.001.704.103,1.383.258,2.041.147-.023.292-.06.442-.06.77,0,1.542.292,2.129.88,1.132,1.132,1.158,2.945.099,4.121h-2.876l1.363-1.293c.39-.391.39-1.024,0-1.414-.391-.391-1.024-.391-1.414,0l-2.451,2.381c-.729.729-.729,1.922,0,2.651l2.451,2.381c.391.391,1.024.391,1.414,0s.391-1.024,0-1.414l-1.363-1.293h8.949Z"/></svg>
                            <span class="cbm_module_label">Caisse</span>
                        </div>
                    </div>

                    <!-- Achats -->
                    <div t-if="state.brainStatus.user_location_type === 'reception'" class="cbm_tooltip_trigger">
                        <div class="cbm_card_module" t-on-click="() => this.goToPOList()">
                            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M18,12a5.993,5.993,0,0,1-5.191-9H4.242L4.2,2.648A3,3,0,0,0,1.222,0H1A1,1,0,0,0,1,2h.222a1,1,0,0,1,.993.883l1.376,11.7A5,5,0,0,0,8.557,19H19a1,1,0,0,0,0-2H8.557a3,3,0,0,1-2.821-2H17.657a5,5,0,0,0,4.921-4.113l.238-1.319A5.984,5.984,0,0,1,18,12Z"/><circle cx="7" cy="22" r="2"/><circle cx="17" cy="22" r="2"/><path d="M15,7h2V9a1,1,0,0,0,2,0V7h2a1,1,0,0,0,0-2H19V3a1,1,0,0,0-2,0V5H15a1,1,0,0,0,0,2Z"/></svg>
                            <span class="cbm_module_label">Achats</span>
                        </div>
                    </div>

                    <!-- Documents -->
                    <div class="cbm_tooltip_trigger">
                        <div class="cbm_card_module" t-on-click="goToDocuments">
                            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M19.5,0H6.5C5.122,0,4,1.122,4,2.5V4H2.5c-.276,0-.5,.224-.5,.5s.224,.5,.5,.5h1.5v2H2.5c-.276,0-.5,.224-.5,.5s.224,.5,.5,.5h1.5v2H2.5c-.276,0-.5,.224-.5,.5s.224,.5,.5,.5h1.5v2H2.5c-.276,0-.5,.224-.5,.5s.224,.5,.5,.5h1.5v2H2.5c-.276,0-.5,.224-.5,.5s.224,.5,.5,.5h1.5v2H2.5c-.276,0-.5,.224-.5,.5s.224,.5,.5,.5h1.5v1.5c0,1.378,1.122,2.5,2.5,2.5h13c1.378,0,2.5-1.122,2.5-2.5V2.5c0-1.378-1.122-2.5-2.5-2.5Zm-3.5,17h-6c-.276,0-.5-.224-.5-.5s.224-.5,.5-.5h6c.276,0,.5,.224,.5,.5s-.224,.5-.5,.5Zm2-4h-8c-.276,0-.5-.224-.5-.5s.224-.5,.5-.5h8c.276,0,.5,.224,.5,.5s-.224,.5-.5,.5Zm0-4h-8c-.276,0-.5-.224-.5-.5s.224-.5,.5-.5h8c.276,0,.5,.224,.5,.5s-.224,.5-.5,.5Z"/></svg>
                            <span class="cbm_module_label">Documents</span>
                        </div>
                    </div>

                    <!-- Custom Tiles from Tile Manager -->
                    <t t-foreach="state.customTiles" t-as="tile" t-key="tile.id">
                        <div class="cbm_tooltip_trigger">
                            <div class="cbm_card_module" t-on-click="() => this.openCustomTile(tile)">
                                <span t-att-class="'cbm_tile_icon_svg cbm_icon_' + getIconClass(tile.icon)"/>
                                <span class="cbm_module_label" t-esc="tile.name"/>
                                <span t-if="tile.pending_count > 0" class="cbm_tile_badge" t-esc="tile.pending_count"/>
                            </div>
                            <div class="cbm_tooltip cbm_tooltip_bottom" t-if="tile.description">
                                <div class="cbm_tooltip_card">
                                    <div class="cbm_tooltip_header">
                                        <h3 class="cbm_tooltip_title" t-esc="tile.name"/>
                                    </div>
                                    <div class="cbm_tooltip_content">
                                        <p class="cbm_tooltip_text" t-esc="tile.description"/>
                                    </div>
                                    <div class="cbm_tooltip_arrow"></div>
                                </div>
                            </div>
                        </div>
                    </t>

                </div>
            </section>

        </div><!-- end cbm_home_main -->
```

- [ ] **Step 2: Commit checkpoint**

```bash
git add static/src/xml/cbm_kiosk.xml
git commit -m "feat(dashboard): add secondary modules grid"
```

---

## Task 7: Add sidebar to XML

**Files:**
- Modify: `static/src/xml/cbm_kiosk.xml`

- [ ] **Step 1: Add `cbm_sidebar_v2` after `cbm_home_main`, inside `cbm_home_layout_v2`**

```xml
        <!-- RIGHT: Sidebar -->
        <aside class="cbm_sidebar_v2">

            <!-- Suivi tile -->
            <div class="cbm_suivi_tile" t-on-click="goToHistory">
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="m14.181.207a1 1 0 0 0 -1.181.983v2.879a8.053 8.053 0 1 0 6.931 6.931h2.886a1 1 0 0 0 .983-1.181 12.047 12.047 0 0 0 -9.619-9.612zm1.819 12.793h-2.277a1.994 1.994 0 1 1 -2.723-2.723v-3.277a1 1 0 0 1 2 0v3.277a2 2 0 0 1 .723.723h2.277a1 1 0 0 1 0 2z"/></svg>
                <div class="cbm_suivi_text">
                    <span class="cbm_suivi_label">Suivi</span>
                    <span class="cbm_suivi_hint">Historique des opérations</span>
                </div>
                <span class="cbm_icon_chevron_right cbm_suivi_chevron"/>
            </div>

            <!-- Progress bars card -->
            <div class="cbm_sidebar_card">
                <h3 class="cbm_sidebar_heading">En Attente</h3>
                <div class="cbm_progress_list">

                    <!-- Mes Demandes -->
                    <div class="cbm_progress_item" t-on-click="goToHistory" title="Voir toutes vos demandes">
                        <div class="cbm_progress_item_header">
                            <span class="cbm_progress_label">Mes Demandes</span>
                            <span class="cbm_progress_value">
                                <t t-if="state.pendingApprovals.my_requests_count > 0"><t t-esc="state.pendingApprovals.my_requests_count"/> en attente</t>
                                <t t-else="">Aucune</t>
                            </span>
                        </div>
                        <div class="cbm_progress_bar_track">
                            <div class="cbm_progress_bar_fill"
                                 t-attf-style="width: #{Math.min(100, (state.pendingApprovals.my_requests_count / 20) * 100)}%"/>
                        </div>
                    </div>

                    <!-- À Valider -->
                    <div t-if="state.pendingApprovals.has_transfer_approvals"
                         class="cbm_progress_item" t-on-click="openToApprove" title="Transferts à approuver">
                        <div class="cbm_progress_item_header">
                            <span class="cbm_progress_label">À Valider</span>
                            <span class="cbm_progress_value">
                                <t t-if="state.pendingApprovals.to_approve_count"><t t-esc="state.pendingApprovals.to_approve_count"/> en attente</t>
                                <t t-else="">À jour</t>
                            </span>
                        </div>
                        <div class="cbm_progress_bar_track">
                            <div class="cbm_progress_bar_fill cbm_bar_amber"
                                 t-attf-style="width: #{Math.min(100, (state.pendingApprovals.to_approve_count / 20) * 100)}%"/>
                        </div>
                    </div>

                    <!-- Réceptions -->
                    <div t-if="state.pendingApprovals.has_reception_access"
                         class="cbm_progress_item" t-on-click="goToReceptions" title="Livraisons à recevoir">
                        <div class="cbm_progress_item_header">
                            <span class="cbm_progress_label">Réceptions</span>
                            <span class="cbm_progress_value">
                                <t t-if="state.pendingApprovals.my_receptions_count"><t t-esc="state.pendingApprovals.my_receptions_count"/> à recevoir</t>
                                <t t-else="">Tout reçu</t>
                            </span>
                        </div>
                        <div class="cbm_progress_bar_track">
                            <div class="cbm_progress_bar_fill"
                                 t-attf-style="width: #{Math.min(100, (state.pendingApprovals.my_receptions_count / 30) * 100)}%"/>
                        </div>
                    </div>

                    <!-- Bons de commande -->
                    <div t-if="state.pendingApprovals.pending_po_count > 0 || state.pendingApprovals.is_po_approver"
                         class="cbm_progress_item" t-on-click="openPendingPO" title="Bons de commande en attente">
                        <div class="cbm_progress_item_header">
                            <span class="cbm_progress_label">Bons de commande</span>
                            <span class="cbm_progress_value">
                                <t t-if="state.pendingApprovals.pending_po_count"><t t-esc="state.pendingApprovals.pending_po_count"/> en attente</t>
                                <t t-else="">À jour</t>
                            </span>
                        </div>
                        <div class="cbm_progress_bar_track">
                            <div class="cbm_progress_bar_fill cbm_bar_secondary"
                                 t-attf-style="width: #{Math.min(100, (state.pendingApprovals.pending_po_count / 20) * 100)}%"/>
                        </div>
                    </div>

                    <!-- Divergences Stock -->
                    <div t-if="(state.userContext.stock_alert_visibility === 'all' || (state.userContext.stock_alert_visibility === 'admin_only' and state.userContext.is_admin)) and state.pendingApprovals.pending_discrepancy_count > 0"
                         class="cbm_progress_item" t-on-click="openStockDiscrepancies" title="Divergences de stock">
                        <div class="cbm_progress_item_header">
                            <span class="cbm_progress_label">Divergences Stock</span>
                            <span class="cbm_progress_value cbm_progress_value--error">
                                <t t-esc="state.pendingApprovals.pending_discrepancy_count"/> à investiguer
                            </span>
                        </div>
                        <div class="cbm_progress_bar_track">
                            <div class="cbm_progress_bar_fill cbm_bar_error"
                                 t-attf-style="width: #{Math.min(100, (state.pendingApprovals.pending_discrepancy_count / 10) * 100)}%"/>
                        </div>
                    </div>

                    <!-- Maintenance -->
                    <div t-if="state.pendingApprovals.is_maintenance_responsible and state.pendingApprovals.my_maintenance_count > 0"
                         class="cbm_progress_item" t-on-click="openMaintenanceList" title="Demandes de maintenance">
                        <div class="cbm_progress_item_header">
                            <span class="cbm_progress_label">Maintenance</span>
                            <span class="cbm_progress_value">
                                <t t-esc="state.pendingApprovals.my_maintenance_count"/> nouvelle(s)
                            </span>
                        </div>
                        <div class="cbm_progress_bar_track">
                            <div class="cbm_progress_bar_fill cbm_bar_secondary"
                                 t-attf-style="width: #{Math.min(100, (state.pendingApprovals.my_maintenance_count / 10) * 100)}%"/>
                        </div>
                    </div>

                    <!-- Brain Suggestions -->
                    <div t-if="state.brainStatus.has_suggestions"
                         class="cbm_progress_item" t-on-click="openBrainSuggestions" title="Suggestions de réapprovisionnement">
                        <div class="cbm_progress_item_header">
                            <span class="cbm_progress_label">Suggestions</span>
                            <span class="cbm_progress_value">
                                <t t-if="state.brainStatus.critical_count > 0"><t t-esc="state.brainStatus.critical_count"/> critique(s)</t>
                                <t t-else=""><t t-esc="state.brainStatus.suggestion_count"/> produit(s)</t>
                            </span>
                        </div>
                        <div class="cbm_progress_bar_track">
                            <div t-att-class="'cbm_progress_bar_fill ' + (state.brainStatus.critical_count > 0 ? 'cbm_bar_error' : 'cbm_bar_tertiary')"
                                 t-attf-style="width: #{Math.min(100, (state.brainStatus.suggestion_count / 20) * 100)}%"/>
                        </div>
                    </div>

                </div>
            </div>

            <!-- Recent Activity card -->
            <div class="cbm_sidebar_card">
                <h4 class="cbm_recent_heading">Mises à jour récentes</h4>
                <div t-if="state.recentActivity.length > 0" class="cbm_recent_list">
                    <t t-foreach="state.recentActivity" t-as="item" t-key="item.name">
                        <div class="cbm_recent_item">
                            <div t-att-class="'cbm_recent_dot ' + _recentDotClass(item.state)"/>
                            <div>
                                <p class="cbm_recent_name" t-esc="item.name"/>
                                <p class="cbm_recent_meta">
                                    <t t-esc="_formatRelativeTime(item.create_date)"/>
                                    <t t-if="item.portal_behavior"> · <t t-esc="item.portal_behavior"/></t>
                                </p>
                            </div>
                        </div>
                    </t>
                </div>
                <p t-else="" class="cbm_recent_empty">Aucune activité récente</p>
            </div>

        </aside>

    </div><!-- end cbm_home_layout_v2 -->
```

- [ ] **Step 2: Close the home div**

Make sure the closing `</div>` for `<div t-elif="state.currentState === 'home'"...>` is still present after the layout. The old `</div>` that closed `cbm_home_layout` and `cbm_kiosk_home` must be adjusted — remove the extra closing `</div>` for the old `cbm_home_layout` and the old sidebar sections that were inside it (since they are now replaced). The new structure closes as: `</div><!-- layout_v2 -->` then `</div><!-- cbm_kiosk_home -->`.

- [ ] **Step 3: Remove old home screen content**

Delete the old layout blocks that are now replaced:
- The old `<div class="cbm_home_layout">` and its children (old `cbm_tiles_primary`, `cbm_tiles_secondary`, `cbm_tiles_tertiary`, `cbm_tiles_custom`, and old `cbm_approvals_sidebar`)

These are the blocks from around line 101 to the closing `</div>` of `cbm_home_layout` (before the `</div><!-- cbm_kiosk_home -->`).

- [ ] **Step 4: Commit**

```bash
git add static/src/xml/cbm_kiosk.xml
git commit -m "feat(dashboard): add sidebar (Suivi tile, progress bars, recent activity)"
```

---

## Task 8: Update Odoo module and verify

**Files:**
- No new files

- [ ] **Step 1: Restart Odoo and update the module**

```bash
sudo service odoo restart
```

Wait 5 seconds, then update the module:

```bash
# From the Odoo root (adjust path to your odoo-bin):
python3 /opt/odoo/odoo-bin -u clinic_staff_portal -c /etc/odoo/odoo.conf --stop-after-init
```

Or via Odoo UI: Settings → Technical → Update Apps → search `clinic_staff_portal` → Update.

- [ ] **Step 2: Open the portal and verify visually**

Navigate to the CBM portal (`/odoo/action-clinic_staff_portal.action_cbm_kiosk` or the menu entry).

Check:
- [ ] Announcement banner appears above header when inventory event is scheduled
- [ ] Header shows logo + ward + dark mode toggle + logout — no search bar, no nav links
- [ ] Welcome section shows user name
- [ ] 3 primary cards (Demande, Dispensation, Prescription) render with colored icon containers
- [ ] Hover on a card: border appears, icon container fills to solid color
- [ ] Blocked card: red tint on border + chip says "Accès bloqué"
- [ ] Secondary modules grid (Caisse, Achats, Documents, custom tiles) renders in 2-3 col grid
- [ ] Sidebar renders on right: Suivi tile on top, progress bars, recent activity at bottom
- [ ] Suivi tile click → navigates to history screen
- [ ] Progress bar items are clickable (Mes Demandes → history, À Valider → openToApprove, etc.)
- [ ] Recent activity shows last 5 pickings with colored dots and relative time
- [ ] On mobile (< 992px): sidebar stacks below main content

- [ ] **Step 3: Final commit**

```bash
git add .
git commit -m "feat(dashboard): complete dashboard redesign — Precision Curator design system"
```
