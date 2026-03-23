# Clinic Staff Portal - Administration & Technical Guide

**Module:** clinic_staff_portal
**Version:** 16.0.3.4.0
**Odoo:** 16.0 Community / Bahmni
**Last Updated:** February 2026

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Installation & Configuration](#3-installation--configuration)
4. [Security Model](#4-security-model)
5. [Dashboard Tiles](#5-dashboard-tiles)
6. [Consumption Workflow](#6-consumption-workflow)
7. [Consumption Ledger](#7-consumption-ledger)
8. [Request Workflow](#8-request-workflow)
9. [Stock Discrepancy Alerts](#9-stock-discrepancy-alerts)
10. [Anti-Hoarding System](#10-anti-hoarding-system)
11. [Cashier Sessions & Z-Reports](#11-cashier-sessions--z-reports)
12. [Convention / Insurance Billing](#12-convention--insurance-billing)
13. [Financial Dashboard](#13-financial-dashboard)
14. [Cron Jobs](#14-cron-jobs)
15. [Troubleshooting](#15-troubleshooting)
16. [Document Acknowledgement](#16-document-acknowledgement)
17. [Session Auto-Logout](#17-session-auto-logout)

---

## 1. Overview

The Clinic Staff Portal is a single-page OWL application running inside Odoo 16. It replaces the standard Odoo interface for clinical staff with a touch-optimized kiosk designed for nurses, pharmacists, and cashiers operating in a hospital environment.

### What it does

| Capability | Description |
|---|---|
| Patient Consumption | Dispense products from ward stock, create billing on patient SO |
| Stock Requests | Pull products from central pharmacy to ward |
| Internal Consumption | Non-billable usage tracking (department, magasin) |
| Returns | Return stock with exact lot traceability (LIFO) |
| Cashier | Daily payment sessions with Z-Report reconciliation |
| Financial Dashboard | Executive gains/losses view |
| Discrepancy Alerts | Automated alerts when stock mismatches block operations |
| Anti-Hoarding | Visual warnings when wards accumulate excess inventory |
| Access Logging | IP, resolution, user-agent tracking per session |

### Key dependencies

| Module | Purpose |
|---|---|
| serenvale_stock_access_control | Location-based access control enforcement |
| stock, sale, account, purchase | Core Odoo modules |
| maintenance, hr_holidays | Maintenance requests, time-off integration |
| web_responsive | Responsive layout base |

---

## 2. Architecture

### Frontend

Single OWL 2 component (`CBMKiosk`) managing all screens via `state.currentState`:

```
home -> consumption_menu -> consumption_patient -> consumption_products -> success
     -> request -> success
     -> history
     -> financial (executive only)
     -> cashier
```

Assets loaded in order:
1. `kiosk_body_class.js` — adds CSS class before DOM renders (prevents navbar flash)
2. SCSS files (portal, kiosk, cashier, timeoff)
3. `cbm_kiosk.js` — main SPA component (~3500 lines)
4. `cbm_brain_patch.js` — patches Odoo NavBar/Sidebar to hide in kiosk mode

### Backend

All business logic in Python models. The controller (`controllers/main.py`) acts as a thin JSON-RPC layer between the OWL frontend and the Odoo ORM.

Critical models:
- `stock.picking` — extended with `_execute_consumption_submit()` engine
- `clinic.consumption.ledger` — source of truth for lot traceability
- `clinic.stock.discrepancy` — stock alert system
- `cashier.session` — daily payment sessions
- `clinic.portal.tile` — configurable dashboard tiles

### Data Flow: Patient Consumption

```
Nurse selects patient
    -> Frontend loads draft SO via /cbm/get_patient_draft_quotation
    -> Ledger entries loaded as source of truth (migration fallback for legacy SOs)
    -> Nurse modifies products (add/remove/change qty)
    -> Frontend calculates delta (current vs original)
    -> /cbm/submit_consumption called with lines[]
        -> Backend separates: consumption_lines, return_lines, unchanged
        -> If return_lines exist AND confirm_deletion=False:
            -> Return requires_confirmation response (show modal)
        -> If confirmed:
            -> Return picking created + validated FIRST
            -> Ledger mark_returned() called per entry
            -> SO lines updated (qty reduced)
            -> Consumption picking created
            -> _execute_consumption_submit():
                -> Stock check, discrepancy alerts for OOS
                -> SO lines created/merged (no lot_id yet)
                -> Picking confirmed + validated
                -> Ledger entries created from validated move_lines (lot captured)
                -> _sync_so_lines_from_ledger() rebuilds SO lines per product+lot
```

---

## 3. Installation & Configuration

### Install

The module is deployed as part of the `extra-odoo-addons` volume in Docker. To update:

```bash
# Restart Odoo with module update
docker compose restart odoo

# Or force module upgrade
python3 odoo-bin -u clinic_staff_portal -c /etc/odoo/odoo.conf
```

### Settings

Navigate to: **Settings > Clinic Staff Portal**

#### Locations

| Setting | Purpose | Example |
|---|---|---|
| Pharmacy Location | Central pharmacy (source for requests) | WH/Stock/Pharmacy |
| Patient Location | Virtual location for consumption destination | Virtual/Patient Consumption |
| Magasin Location | General supplies warehouse | WH/Stock/Magasin |
| Maintenance Location | Technical/maintenance supplies | WH/Stock/Maintenance |

#### Lot Selection

| Option | Behavior |
|---|---|
| Auto FEFO | System selects lot automatically (First Expiry, First Out) |
| Manual | User must select lot manually |

#### Enforcement

| Setting | Default | Description |
|---|---|---|
| Pending Enforcement Enabled | Yes | Global toggle for transfer blocking |
| Pending Transfer Warn Threshold | 5 | Show warning at N pending transfers |
| Pending Transfer Block Threshold | 0 | Block new transfers at N pending (0=disabled) |
| Pending PO Warn Days | 7 | Warn if PO pending > N days |

#### Cashier Journals

| Setting | Description |
|---|---|
| Cash Journal | Journal for cash payments (especes) |
| Card Journal | Journal for card payments (carte) |
| Cheque Journal | Journal for cheque payments |
| Convention Journal | Receivables journal for insurance/convention |
| Loss Account | Account for refund losses |

#### Admin Users

| Setting | Description |
|---|---|
| DRH User | HR liaison for escalation notifications |
| Executive Users | Users who see the financial dashboard |
| Admin Users | Full portal access (all tiles, all operations) |

### Sync Users

To configure all existing users for the kiosk:

**Settings > Clinic Staff Portal > Sync CBM Portal Users**

This action:
1. Sets each user's default action to the CBM Kiosk
2. Enables fullscreen kiosk mode
3. Adds users to `group_clinic_portal_user`

To reverse: **Unsync CBM Portal Users**

---

## 4. Security Model

### Groups (hierarchical)

```
group_clinic_portal_user (Clinical Staff)
    |
    v
group_clinic_portal_approver (Department Supervisor)
    |
    v
group_clinic_portal_manager (Operations Manager)
    |
    v
group_clinic_portal_executive (Executive Director)

group_clinic_portal_cashier (Independent — not in hierarchy)
```

### Permissions Matrix

| Model | User | Approver | Manager | Executive |
|---|---|---|---|---|
| portal.tile | R | R | RWCD | RWCD |
| stock.discrepancy | RC | RC | RWCD | RWCD |
| cashier.session | RWC | RWC | RWCD | RWCD |
| consumption.ledger | R | R | RWCD | RWCD |
| clinic.document | R | R | RWCD | RWCD |
| stock.picking.type | R | R | RWC | RWC |

### Tile Visibility

Tiles can be restricted by:
1. **Location** (`limit_location_ids`) — only users with access to these locations see the tile
2. **Group** (`group_ids`) — only members of these groups see the tile
3. **Both** — both conditions must be met

---

## 5. Dashboard Tiles

### Tile Types

| Type | Behavior |
|---|---|
| stock | Opens a stock picking form (request, consumption, return) |
| action | Opens an Odoo action (ir.actions.act_window) |
| client_action | Opens a client-side action (e.g., Discuss) |
| folder | Opens a sub-grid of child tiles (POS-style selector) |

### Tile Configuration

Each tile has:
- **Name** — displayed label (translatable)
- **Icon** — Heroicon selection (50+ options)
- **Color** — hex background color
- **Icon Color** — hex icon color
- **Sequence** — display order
- **Active** — show/hide toggle

### Stock Tile Behaviors

| Behavior | Patient Required | Department Required | Creates SO | Creates Invoice |
|---|---|---|---|---|
| billable | Yes | No | Yes | Yes (on confirm) |
| surgery | Yes | No | Yes | Yes |
| request | No | No | No | No |
| internal | No | No | No | No |
| return | No | No | No | No |

### Consumption Source

| Source | Stock consumed from |
|---|---|
| ward | User's assigned ward/location |
| pharmacy | Central pharmacy location |
| magasin | General supplies warehouse |

---

## 6. Consumption Workflow

### Flow Diagram

```
SELECT PATIENT
    |
    v
LOAD EXISTING SO (if any)
    |-- Ledger entries loaded as source of truth
    |-- Migration fallback for legacy SOs without ledger
    |
    v
MODIFY PRODUCTS (add/remove/change qty)
    |
    v
SUBMIT (delta calculation)
    |
    |-- Returns detected? --> CONFIRMATION MODAL
    |       |-- Cancel: stop
    |       |-- Confirm: proceed
    |
    v
RETURN PICKING (if returns exist)
    |-- Created with LIFO lot selection from ledger
    |-- Validated immediately
    |-- Ledger entries updated (mark_returned)
    |-- SO lines qty reduced
    |
    v
CONSUMPTION PICKING (if new items)
    |-- SO lines created (product + qty, no lot)
    |-- Picking confirmed + assigned + validated
    |-- Ledger entries created from validated move_lines
    |-- SO lines rebuilt from ledger (_sync_so_lines_from_ledger)
    |       |-- One SO line per product+lot
    |       |-- Multi-lot FEFO splits handled
    |
    v
SUCCESS
```

### Delta Calculation

For each product in the submission:

| Scenario | Action |
|---|---|
| `current_qty > original_qty` | Consume the delta (additional stock out) |
| `current_qty < original_qty` | Return the delta (stock back in) |
| `current_qty == original_qty` | Skip (no movement) |
| `original_qty == null` | New item, consume full qty |
| `current_qty == 0` | Full return of original qty |

### SO Line Management

The system enforces Bahmni's constraint: **one SO line per lot per SO** (no duplicate lots).

- SO lines are created WITHOUT lot_id (unknown before validation)
- After picking validation, `_sync_so_lines_from_ledger()` rebuilds lines:
  - Groups ledger entries by product+lot
  - Matches to existing SO lines
  - Splits lines if FEFO assigned multiple lots to one product
  - Assigns lot_id from ledger

---

## 7. Consumption Ledger

### Purpose

The consumption ledger (`clinic.consumption.ledger`) solves a fundamental problem: Odoo's `stock.move.line` records the exact lot used during validation, but this information is not easily accessible for returns. The SO line `lot_id` is unreliable (set before validation, or not set at all for portal consumption).

The ledger captures the exact lot at the moment of physical stock movement.

### Fields

| Field | Type | Description |
|---|---|---|
| sale_order_id | Many2one | Patient billing SO |
| partner_id | Many2one | Patient |
| location_id | Many2one | Source location |
| product_id | Many2one | Product consumed |
| lot_id | Many2one | Exact lot (from validated move_line) |
| qty_consumed | Float | Original qty consumed |
| qty_returned | Float | Qty already returned |
| qty_available | Float | Computed: consumed - returned |
| picking_id | Many2one | Consumption picking reference |
| move_line_id | Many2one | Exact stock.move.line |
| return_picking_ids | Many2many | Return pickings linked |
| state | Selection | active / fully_returned / archived |

### LIFO Returns

When returning stock, the system uses Last-In-First-Out:

```
Ledger entries for Product X on SO S10646:
  Entry 25 (Feb 19): qty_consumed=5, lot=15435, qty_available=5  <-- newest
  Entry 12 (Feb 15): qty_consumed=3, lot=11186, qty_available=3
  Entry  8 (Feb 10): qty_consumed=2, lot=09234, qty_available=2

Return 4 units of Product X:
  -> Take 4 from Entry 25 (lot 15435): return 4, qty_available=1
  -> Done. Return picking uses lot 15435 x 4.

Return 3 more units:
  -> Take 1 from Entry 25 (lot 15435): return 1, qty_available=0, state=fully_returned
  -> Take 2 from Entry 12 (lot 11186): return 2, qty_available=1
  -> Done. Return picking uses lot 15435 x 1 + lot 11186 x 2.
```

### Lifecycle

| Event | Ledger Action |
|---|---|
| Consumption validated | Entry created (state=active) |
| Partial return | qty_returned increased |
| Full return | state=fully_returned |
| SO confirmed (invoiced) | state=archived |
| SO cancelled | state=archived |
| Cron (weekly) | Entries older than 3 months with closed SO: state=archived |

### Database Indexes

Four indexes created on module install (via `init()`):

1. `consumption_ledger_so_partner_state_idx` — SO + partner + state (WHERE active)
2. `consumption_ledger_so_product_idx` — SO + product
3. `consumption_ledger_lifo_idx` — SO + product + date DESC (WHERE active, qty_available > 0)
4. `consumption_ledger_cleanup_idx` — state + date (WHERE archived)

### Backend View

**Inventory > Operations > Consumption Ledger** (Manager group only)

Tree view showing all entries with filtering by patient, product, state, date range.

---

## 8. Request Workflow

### Flow

```
NURSE creates request
    |-- Selects products + quantities
    |-- Stock availability shown (from source location)
    |
    v
SUBMIT
    |-- Picking created (state=draft)
    |-- Managers of source location notified
    |
    v
MANAGER validates
    |-- Picking confirmed + goods transferred
    |-- Nurse notified of completion
```

### Pending Transfer Enforcement

| Setting | Effect |
|---|---|
| Warn Threshold (default 5) | Shows warning banner: "You have N pending transfers" |
| Block Threshold (default 0) | Prevents new request creation entirely |

Thresholds are configurable per operation type (`stock.picking.type`) and globally in Settings.

---

## 9. Stock Discrepancy Alerts

### When Created

Automatically when a consumption is blocked because system stock = 0 for a requested product. The consumption proceeds for other products — only the OOS product is skipped.

### Alert Data

Each alert captures:
- Who tried to consume (user, timestamp)
- What they tried to consume (product, qty)
- What the system showed (system_qty, usually 0)
- Where (location, picking type)
- Associated picking (if partially processed)

### Investigation States

| State | Description |
|---|---|
| pending | New alert, not yet investigated |
| nurse_error | Investigation concluded: user made a mistake |
| inventory_issue | Investigation concluded: actual stock discrepancy |
| resolved | Issue corrected |

### Notifications

When created, alerts:
1. Post a message to Portal Admin group
2. Create a scheduled activity for the location responsible
3. Log the incident with full context

### Backend View

**Inventory > Operations > Stock Discrepancies** (Manager group only)

---

## 10. Anti-Hoarding System

### Purpose

Prevents wards from accumulating excess stock by warning or blocking when recent incoming transfers exceed consumption.

### Configuration

Per location (`stock.location`):

| Field | Options |
|---|---|
| Replenishment Policy | none / soft / hard |
| Consumption Start Date | Date to start tracking from |

### Algorithm

```
ward_qty_trusted = SUM(incoming moves since start_date) - SUM(consumed moves since start_date)
```

| Policy | Effect |
|---|---|
| none | No warnings |
| soft | Visual badge: "Has Stock" (yellow) |
| hard | Visual badge: "Check Stock!" (red) |

No popups, no blocking — visual feedback only. The nurse can still proceed.

---

## 11. Cashier Sessions & Z-Reports

### Session Lifecycle

```
OPEN SESSION (automatic on first cashier action of the day)
    |
    v
PROCESS PAYMENTS (validate quotations, register payments)
    |-- Cash, card, cheque tracked separately
    |-- Convention/insurance splits handled
    |
    v
COUNT CASH (enter physical count)
    |
    v
CLOSE SESSION
    |-- Difference calculated: counted - system total
    |-- Z-Report PDF generated
```

### Automatic Cleanup

A daily cron (`ir_cron_close_stale_cashier_sessions`) runs at 00:05 and closes any sessions from previous days.

### Z-Report Contents

- Session reference, cashier name, open/close times
- Total by payment method (cash, card, cheque)
- Transaction count
- Cash count vs system total (difference highlighted)
- List of invoices processed during session

### Backend View

**Clinic Staff Portal > Cashier Sessions** (Manager group only)

---

## 12. Convention / Insurance Billing

### Setup

1. Create a pricelist with convention coverage:
   - `convention_coverage_pct` — % covered by insurance (e.g., 80%)
   - `payer_partner_id` — insurance partner (CNAS, CASNOS, etc.)
   - `payer_journal_id` — receivable journal for the payer

2. Run **Settings > Sync Convention Products** to create CONV_* products

3. Run **Settings > Sync Convention Partners** to create partner records

### How It Works

When a patient with a convention pricelist is billed:
- Patient pays (100% - coverage_pct)
- Convention payer is invoiced for coverage_pct
- Separate journal entries for each

---

## 13. Financial Dashboard

### Access

Executive group only (`group_clinic_portal_executive`).

### Metrics

| Metric | Source |
|---|---|
| Total Revenue | Sum of posted customer invoices |
| Total Refunds | Sum of credit notes |
| Convention Revenue | Split by payer |
| Internal Consumption | Non-billable stock usage value |
| Profitability | Revenue - Cost of Goods |

---

## 14. Cron Jobs

| Cron | Schedule | Action |
|---|---|---|
| Close Stale Cashier Sessions | Daily 00:05 | Closes sessions opened before today |
| Cleanup Consumption Ledger | Weekly | Archives entries > 3 months for closed SOs |

---

## 15. Troubleshooting

### "Duplicate batch no is not allowed"

**Cause:** Two SO lines with the same lot_id on one SO.
**Fix:** The `_sync_so_lines_from_ledger()` method prevents this. If it occurs on legacy data, manually remove the duplicate SO line in the backend.

### Return picking stuck in "confirmed" state

**Cause:** lot_id was NULL on the return move_line (historical bug, now fixed).
**Fix:** Cancel the stuck picking via SQL:
```sql
UPDATE stock_move SET state = 'cancel' WHERE picking_id = <id>;
UPDATE stock_picking SET state = 'cancel' WHERE id = <id>;
```

### "Operation non autorisee" on return validation

**Cause:** `serenvale_stock_access_control` blocks `unlink()` on move_lines, even with `sudo()`.
**Fix:** The code now uses `write()` in-place instead of delete+recreate for move_line lot assignment.

### Modal has no background / invisible text

**Cause:** Modals were rendered outside the `.cbm_kiosk` wrapper div, so CSS variables (`--cbm-card-bg`, etc.) were undefined.
**Fix:** All modals must be children of the `.cbm_kiosk` div to inherit theme variables.

### Submit button disabled when all products removed

**Cause:** The disabled condition only checked `selectedProducts.length`, not `removedProducts.length`.
**Fix:** Condition now checks both: `(!selectedProducts.length && !removedProducts.length)`.

### Confirmation popup not firing

**Cause:** OWL template `t-on-click="() => submitConsumption(false)"` must use `this`:
`t-on-click="() => this.submitConsumption(false)"`.
Without `this`, the function loses component context and `this.state` is undefined.

### Ledger shows qty_returned = 0 after return

**Cause:** Return picking validation failed silently (exception caught). Check Odoo logs for the actual error.
**Verify:** `docker compose logs odoo --tail=200 | grep "mark_returned\|Failed to validate"`

### Products not merging on SO (duplicate lines)

**Cause:** SO line merge must match on product only (not product+lot), because lot_id is unknown at SO line creation time.
**Fix:** `_sync_so_lines_from_ledger()` runs after validation to assign lots and split lines as needed.

---

## 16. Document Acknowledgement

### Purpose

Certain documents (policies, terms of service, safety procedures) require staff to explicitly confirm they have read and understood the content. The acknowledgement feature adds a "terms of use" style flow: the document opens fullscreen, the user reads it, and clicks **"J'ai lu et j'accepte"** (I have read and agree). Their agreement is logged with a timestamp.

### How It Works

#### Admin Setup (Tile Manager > Documents)

1. Create or edit a document (PDF type).
2. Check **"Requires Acknowledgement"**.
3. **Targeting** (who must see it):
   - **Target Users** field: set specific users. Only those users will see the document.
   - **Location** field: set locations. Users with matching `allowed_location_ids` will see it.
   - **Both empty**: the document is global — all portal users see it.
   - Priority: `target_user_ids` > `location_ids` > global.
4. Save. If "Notify Users" is checked, target users receive a mail notification.

#### User Experience

1. **On login / page load**: If the user has unacknowledged documents, they are automatically redirected to the CBM Kiosk, where the first pending document opens fullscreen.
2. The PDF fills the entire screen with a header bar showing the document title, a green **"J'ai lu et j'accepte"** button, and a close (X) button.
3. The user can click the agree button at any time while viewing.
4. On click: the viewer closes, a success toast appears, and the next pending document (if any) opens automatically.
5. After acknowledgement, the document remains visible in the Documents list with a green **"Lu"** (Read) checkmark badge.
6. The agree button no longer appears on subsequent views.

#### Acknowledgement Log

In the admin form view (Tile Manager > Documents), when "Requires Acknowledgement" is checked, a **"Acknowledgements"** tab appears at the bottom showing:
- User name
- Date/time of acknowledgement

This provides an audit trail for compliance.

#### Technical Details

| Component | Location |
|---|---|
| Model | `clinic.document.acknowledgement` (`models/clinic_document_acknowledgement.py`) |
| Fields on `clinic.document` | `requires_acknowledgement`, `target_user_ids`, `acknowledgement_ids` |
| Acknowledge endpoint | `POST /cbm/documents/acknowledge` (param: `document_id`) |
| Pending check endpoint | `POST /cbm/session/config` (returns `has_pending_acknowledgements`) |
| Global redirect service | `static/src/js/cbm_global_service.js` |
| Kiosk auto-open | `checkPendingAcknowledgements()` in `cbm_kiosk.js` |
| Security | `group_clinic_portal_user`: read + create. `group_clinic_portal_manager`: full CRUD |

---

## 17. Session Auto-Logout

### Purpose

Clinic workstations are shared. To prevent unauthorized access when staff walk away, the portal automatically logs out inactive users after a configurable timeout.

### Configuration

**Settings > Clinic Portal > Session & Security > Inactivity Timeout (minutes)**

- Default: **5 minutes**
- Set to **0** to disable
- The value is stored in `ir.config_parameter` key `clinic_staff_portal.inactivity_timeout`

### How It Works

1. A global Odoo JS service (`cbm_global_service`) starts on every page load for every logged-in user.
2. It tracks the last user activity timestamp (mouse, keyboard, scroll, touch).
3. Every 30 seconds, it checks if the elapsed time since last activity exceeds the configured timeout.
4. If yes, the user is redirected to `/web/session/logout` (full logout, back to login page).
5. When the browser tab is inactive/hidden, `setTimeout` is unreliable (browsers throttle background timers). The service uses `setInterval` + `Date.now()` comparison instead, and also checks on `visibilitychange` when the tab becomes visible again.

### Activity Events That Reset the Timer

- `mousedown`
- `mousemove`
- `keydown`
- `scroll`
- `touchstart`

### Important Notes

- The timer runs on the **client side** (browser). It does not affect Odoo's server-side session expiry (`session_expiry` in `odoo.conf`).
- If a user has multiple Odoo tabs open, each tab runs its own timer independently.
- The timeout applies to **all** Odoo pages (not just the kiosk), because the service is registered as a global Odoo service in `web.assets_backend`.

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Users not being logged out | Timeout not set in Settings | Go to Settings > Clinic Portal > Session & Security, set a value > 0, and **Save** |
| Users not being logged out (value is set) | Browser assets cached from before the update | Hard refresh (`Ctrl+Shift+R`) or clear browser cache, then update the module |
| Logged out too quickly | Timeout too low | Increase the value in Settings |
| Timer resets on its own | Background RPC polling (e.g., mail, bus) does not reset the timer — only DOM events do. Check if something is triggering mouse events programmatically | Inspect with browser DevTools |

---

## Appendix: Key Files

| File | Purpose |
|---|---|
| `models/stock_picking.py` | Core consumption engine, SO integration |
| `models/consumption_ledger.py` | Lot traceability, LIFO returns |
| `models/stock_discrepancy.py` | Alert system |
| `models/cashier_session.py` | Payment sessions, Z-Reports |
| `models/portal_tile.py` | Dashboard configuration |
| `models/sale_order.py` | Ledger archival on SO confirm/cancel |
| `controllers/main.py` | JSON-RPC endpoints for frontend |
| `static/src/js/cbm_kiosk.js` | OWL SPA component |
| `static/src/xml/cbm_kiosk.xml` | OWL template (all screens) |
| `static/src/scss/cbm_kiosk.scss` | Theme, layout, components |
| `security/ir.model.access.csv` | Group permissions |
| `data/consumption_ledger_cron.xml` | Weekly ledger cleanup |
| `data/cashier_session_cron.xml` | Daily session cleanup |
| `models/clinic_document.py` | Document model (acknowledgement fields, target users) |
| `models/clinic_document_acknowledgement.py` | Acknowledgement log model |
| `controllers/documents.py` | Document list, acknowledge, session config endpoints |
| `static/src/js/cbm_global_service.js` | Global service (auto-logout, ack redirect) |

---

*Generated from source code v16.0.3.4.0 — February 2026*
