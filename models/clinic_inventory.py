# -*- coding: utf-8 -*-
"""
Inventory Models - Physical inventory session, teams, and count lines.

One model does everything:
- clinic.inventory: the session (schedule, teams, lines, announcement, tile sync)
- clinic.inventory.team: teams assigned to count
- clinic.inventory.line: individual product counts per team

Flow:
1. Admin creates session (date, duration, location, teams with users, announcement)
2. Admin clicks "Start" → state=active, tile appears for team users, banner shows
3. Staff scan barcodes, count products → lines saved per team
4. Staff click "Terminer" → state=pending_approval
5. Manager reviews reconciliation → clicks "Approve" → stock adjusted
6. Cron auto-creates sessions on quarterly dates (Jan 1, Apr 1, Jul 1, Oct 1)
"""
import logging
from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ClinicInventory(models.Model):
    _name = 'clinic.inventory'
    _description = 'Physical Inventory Session'
    _order = 'date desc, id desc'

    # ============================================================
    # CORE FIELDS
    # ============================================================

    name = fields.Char('Session Name', required=True, translate=True)
    date = fields.Date('Start Date', required=True, default=fields.Date.today)
    duration_days = fields.Integer(
        'Duration (Days)',
        required=True,
        default=2,
        help='How many days the inventory will take (2-3 typical)'
    )
    location_id = fields.Many2one(
        'stock.location',
        'Location',
        required=True,
        domain="[('usage', '=', 'internal')]",
        help='Location where inventory counting takes place'
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active (Counting)'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('cancelled', 'Cancelled'),
    ], string='State', default='draft', readonly=True)

    responsible_id = fields.Many2one(
        'res.users',
        'Responsible Manager',
        required=True,
        default=lambda self: self.env.user,
    )
    is_full_inventory = fields.Boolean(
        'Full Inventory',
        default=True,
        help='If checked, uncounted products at this location will be set to 0. '
             'Uncheck for partial inventory (only adjust counted products).'
    )
    notes = fields.Text('Notes')

    # ============================================================
    # RELATIONS
    # ============================================================

    team_ids = fields.One2many(
        'clinic.inventory.team', 'inventory_id',
        string='Teams',
    )
    line_ids = fields.One2many(
        'clinic.inventory.line', 'inventory_id',
        string='Count Lines',
    )

    # ============================================================
    # ANNOUNCEMENT (dashboard banner)
    # ============================================================

    announcement_text = fields.Text(
        'Announcement Text',
        help='Custom banner text for CBM dashboard. Auto-generated from dates if empty.'
    )

    @api.depends('announcement_text', 'date', 'duration_days')
    def _compute_announcement(self):
        for rec in self:
            if rec.announcement_text:
                rec.generated_announcement = rec.announcement_text
            elif rec.date and rec.duration_days:
                date_str = rec.date.strftime('%d/%m/%Y')
                duration_str = f"{rec.duration_days} jour" if rec.duration_days == 1 else f"{rec.duration_days} jours"
                rec.generated_announcement = (
                    f"La pharmacie sera fermee le {date_str} pour inventaire pendant {duration_str}."
                )
            else:
                rec.generated_announcement = ''

    generated_announcement = fields.Text(
        'Generated Announcement',
        compute='_compute_announcement',
        store=True,
    )

    # ============================================================
    # COMPUTED FIELDS
    # ============================================================

    @api.depends('date', 'duration_days')
    def _compute_end_date(self):
        for rec in self:
            if rec.date and rec.duration_days:
                rec.end_date = rec.date + timedelta(days=rec.duration_days - 1)
            else:
                rec.end_date = False

    end_date = fields.Date(
        'End Date',
        compute='_compute_end_date',
        store=True,
        help='Auto-calculated: date + duration_days - 1'
    )

    team_count = fields.Integer('Team Count', compute='_compute_team_count', store=False)
    line_count = fields.Integer('Line Count', compute='_compute_line_count', store=False)

    @api.depends('team_ids')
    def _compute_team_count(self):
        for record in self:
            record.team_count = len(record.team_ids)

    @api.depends('line_ids')
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)

    # ============================================================
    # CONSTRAINTS
    # ============================================================

    @api.constrains('duration_days')
    def _check_duration(self):
        for rec in self:
            if rec.duration_days < 1 or rec.duration_days > 10:
                raise UserError(_('Duration must be between 1 and 10 days'))

    # ============================================================
    # STATE ACTIONS
    # ============================================================

    def get_reconciliation_data(self):
        """Build grouped reconciliation data for the final PDF report.

        Groups lines by (product, lot, expiry). Per team, averages across
        individual user counts (identified by create_uid).

        Returns list of dicts sorted by product name, each with:
        - product, lot, expiry, qty_system
        - lines_by_team: {team_id: [line, ...]}
        - avg_counted, variance
        """
        self.ensure_one()
        StockQuant = self.env['stock.quant'].sudo()
        grouped = {}

        for line in self.line_ids:
            key = (line.product_id.id, line.lot_id.id if line.lot_id else False, line.expiry_date)
            if key not in grouped:
                quant = StockQuant.search([
                    ('product_id', '=', line.product_id.id),
                    ('lot_id', '=', line.lot_id.id if line.lot_id else False),
                    ('location_id', '=', self.location_id.id),
                ], limit=1)
                grouped[key] = {
                    'product': line.product_id,
                    'lot': line.lot_id,
                    'expiry': line.expiry_date,
                    'qty_system': quant.quantity if quant else 0.0,
                    'lines_by_team': {},
                    'counts': [],
                }
            team_id = line.team_id.id
            if team_id not in grouped[key]['lines_by_team']:
                grouped[key]['lines_by_team'][team_id] = []
            grouped[key]['lines_by_team'][team_id].append(line)
            grouped[key]['counts'].append(line.qty_counted)

        result = []
        for data in grouped.values():
            avg_counted = sum(data['counts']) / len(data['counts']) if data['counts'] else 0.0
            data['avg_counted'] = avg_counted
            data['variance'] = avg_counted - data['qty_system']
            result.append(data)

        result.sort(key=lambda d: d['product'].name)
        return result

    def get_intra_team_discrepancies(self):
        """Find products where users in the same team counted differently.

        Uses create_uid to identify who counted each line.
        Only relevant when a team has multiple members (each counts independently).

        Returns list of dicts:
        - team, product, lot
        - user_counts: [(user_name, qty_counted), ...]
        - max_diff
        """
        self.ensure_one()
        discrepancies = []

        for team in self.team_ids:
            if len(team.user_ids) < 2:
                continue

            # Group by (product, lot) — collect one line per user (create_uid)
            grouped = {}
            for line in self.line_ids.filtered(lambda l: l.team_id.id == team.id):
                key = (line.product_id.id, line.lot_id.id if line.lot_id else False)
                if key not in grouped:
                    grouped[key] = {
                        'product': line.product_id,
                        'lot': line.lot_id,
                        'user_counts': [],
                    }
                grouped[key]['user_counts'].append((line.create_uid.name, line.qty_counted))

            for data in grouped.values():
                if len(data['user_counts']) < 2:
                    continue
                counts = [uc[1] for uc in data['user_counts']]
                max_diff = max(counts) - min(counts)
                if max_diff > 0:
                    discrepancies.append({
                        'team': team,
                        'product': data['product'],
                        'lot': data['lot'],
                        'user_counts': data['user_counts'],
                        'max_diff': max_diff,
                    })

        discrepancies.sort(key=lambda d: (d['team'].name, d['product'].name))
        return discrepancies

    def action_start(self):
        """Start inventory counting (draft → active). Tile appears for team users."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft inventories can be started'))
        if not self.team_ids:
            raise UserError(_('Create at least one team before starting'))
        if not any(t.user_ids for t in self.team_ids):
            raise UserError(_('Assign users to at least one team before starting'))
        self.write({'state': 'active'})
        self._sync_tile_visibility()
        _logger.info("[Inventory] Session %s started by %s", self.id, self.env.user.name)
        return True

    def action_submit(self):
        """Submit for approval (active → pending_approval).

        Called directly from backend button. For staff portal per-user
        submission, use action_user_submit() instead.
        """
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_('Only active inventories can be submitted for approval'))
        if not self.line_ids:
            raise UserError(_('Cannot submit inventory without counted lines'))
        self.write({'state': 'pending_approval'})
        _logger.info("[Inventory] Session %s submitted for approval", self.id)
        return True

    def action_user_submit(self, user, team):
        """Record a single user's submission within their team.

        Adds user to team.submitted_user_ids. If all users in all teams
        have submitted, auto-transitions session to pending_approval.

        Args:
            user: res.users record
            team: clinic.inventory.team record
        """
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_('Session is not active'))

        # Add user to submitted list
        if user not in team.submitted_user_ids:
            team.write({'submitted_user_ids': [(4, user.id)]})
            _logger.info(
                "[Inventory] User %s submitted count for team %s in session %s",
                user.name, team.name, self.name
            )

        # Check if all users in all teams have submitted
        all_submitted = True
        for t in self.team_ids:
            for u in t.user_ids:
                if u not in t.submitted_user_ids:
                    all_submitted = False
                    break
            if not all_submitted:
                break

        if all_submitted:
            self._auto_complete()

        return all_submitted

    def _auto_complete(self):
        """All users submitted — refresh system qty and transition to pending_approval."""
        self.ensure_one()
        # Force recomputation of stored computed fields (direct call doesn't persist)
        Line = self.env['clinic.inventory.line']
        self.env.add_to_compute(Line._fields['qty_system'], self.line_ids)
        self.env.add_to_compute(Line._fields['variance'], self.line_ids)
        self.flush_recordset()
        self.line_ids.flush_recordset()
        self.write({'state': 'pending_approval'})
        _logger.info(
            "[Inventory] Session %s auto-completed — all users submitted",
            self.name
        )

    def action_approve(self):
        """Approve and apply to stock (pending_approval → approved)."""
        self.ensure_one()
        if self.state != 'pending_approval':
            raise UserError(_('Only pending inventories can be approved'))
        self._apply_stock_adjustments()
        self.write({'state': 'approved'})
        self._sync_tile_visibility()
        _logger.info("[Inventory] Session %s approved by %s", self.id, self.env.user.name)
        return True

    def action_request_recount(self):
        """Manager requests recount (pending_approval → active).

        Clears submitted_user_ids on all teams so staff can re-enter
        counting UI. Existing lines are preserved for editing.
        """
        self.ensure_one()
        if self.state != 'pending_approval':
            raise UserError(_('Can only request recount on pending inventories'))
        for team in self.team_ids:
            team.write({'submitted_user_ids': [(5, 0, 0)]})
        self.write({'state': 'active'})
        self._sync_tile_visibility()
        _logger.info(
            "[Inventory] Session %s sent back for recount by %s",
            self.name, self.env.user.name
        )
        return True

    def action_cancel(self):
        """Cancel session (any non-approved state → cancelled)."""
        self.ensure_one()
        if self.state == 'approved':
            raise UserError(_('Cannot cancel already approved inventories'))
        self.write({'state': 'cancelled'})
        self._sync_tile_visibility()
        _logger.info("[Inventory] Session %s cancelled", self.id)
        return True

    # ============================================================
    # TILE VISIBILITY SYNC
    # ============================================================

    @api.model
    def _sync_tile_visibility(self):
        """Sync inventory tile: visible only to users assigned to active session teams."""
        tile = self.env.ref('clinic_staff_portal.tile_inventory', raise_if_not_found=False)
        if not tile:
            _logger.warning("[Inventory] tile_inventory not found, skipping sync")
            return

        active_teams = self.env['clinic.inventory.team'].search([
            ('inventory_id.state', '=', 'active'),
        ])
        all_user_ids = active_teams.mapped('user_ids').ids

        if all_user_ids:
            tile.sudo().write({
                'active': True,
                'assigned_user_ids': [(6, 0, all_user_ids)],
            })
            _logger.info("[Inventory] Tile activated for %d users", len(all_user_ids))
        else:
            tile.sudo().write({
                'active': False,
                'assigned_user_ids': [(5, 0, 0)],
            })
            _logger.info("[Inventory] Tile deactivated (no active sessions)")

    # ============================================================
    # STOCK ADJUSTMENTS
    # ============================================================

    def _apply_stock_adjustments(self):
        """Apply counted inventory to stock.quant via Odoo's inventory mechanism.

        Steps:
        1. Refresh qty_system on all lines (stock may have changed since counting)
        2. Aggregate lines by (product, lot) — average across teams if multiple
        3. Set inventory_quantity on quants using sudo + inventory_mode context
        4. If full inventory: zero out uncounted products at this location
        5. Call _apply_inventory() directly (bypasses wizard returns)
        """
        self.ensure_one()
        # sudo() required: portal manager may not have stock.group_stock_manager
        # inventory_mode context required: enables Odoo's inventory adjustment flow
        StockQuant = self.env['stock.quant'].sudo().with_context(inventory_mode=True)

        # --- Step 1: Refresh qty_system on all lines ---
        Line = self.env['clinic.inventory.line']
        self.env.add_to_compute(Line._fields['qty_system'], self.line_ids)
        self.env.add_to_compute(Line._fields['variance'], self.line_ids)
        self.line_ids.flush_recordset()

        # --- Step 2: Aggregate lines by (product_id, lot_id) ---
        # If multiple teams counted the same product+lot, average their counts
        aggregated = {}  # key: (product_id, lot_id) → list of qty_counted
        for line in self.line_ids:
            key = (line.product_id.id, line.lot_id.id if line.lot_id else False)
            if key not in aggregated:
                aggregated[key] = {
                    'product_id': line.product_id.id,
                    'lot_id': line.lot_id.id if line.lot_id else False,
                    'counts': [],
                }
            aggregated[key]['counts'].append(line.qty_counted)

        # --- Step 3: Set inventory_quantity on quants ---
        # Pre-fetch all quants at this location in one query to avoid N+1
        all_location_quants = StockQuant.search([
            ('location_id', '=', self.location_id.id),
        ])
        quant_map = {
            (q.product_id.id, q.lot_id.id if q.lot_id else False): q
            for q in all_location_quants
        }

        touched_quants = self.env['stock.quant'].sudo()
        for key, data in aggregated.items():
            # Average across teams
            avg_qty = sum(data['counts']) / len(data['counts'])

            quant = quant_map.get(key)

            if quant:
                quant.inventory_quantity = avg_qty
            else:
                # Create quant in inventory mode — Odoo handles the rest
                quant = StockQuant.create({
                    'product_id': data['product_id'],
                    'lot_id': data['lot_id'],
                    'location_id': self.location_id.id,
                    'inventory_quantity': avg_qty,
                })

            touched_quants |= quant

        _logger.info(
            "[Inventory] Set inventory_quantity on %d quants for session %s",
            len(touched_quants), self.id
        )

        # --- Step 4: Full inventory — zero out uncounted products ---
        if self.is_full_inventory:
            counted_keys = set(aggregated.keys())

            # Reuse pre-fetched quants — filter to those with positive stock not counted
            for quant in all_location_quants.filtered(lambda q: q.quantity > 0):
                qkey = (quant.product_id.id, quant.lot_id.id if quant.lot_id else False)
                if qkey not in counted_keys:
                    quant.inventory_quantity = 0
                    touched_quants |= quant
                    _logger.info(
                        "[Inventory] Zeroed uncounted product %s (lot %s) at %s",
                        quant.product_id.name,
                        quant.lot_id.name if quant.lot_id else 'N/A',
                        self.location_id.name,
                    )

        # --- Step 5: Apply inventory adjustments ---
        # Use _apply_inventory() directly instead of action_apply_inventory()
        # action_apply_inventory() can return wizard actions for conflicts,
        # which would silently fail when called from Python code
        quants_to_apply = touched_quants.filtered(lambda q: q.inventory_quantity_set)
        if quants_to_apply:
            # _apply_inventory checks stock.group_stock_manager — must use sudo
            quants_to_apply.sudo()._apply_inventory()
            _logger.info(
                "[Inventory] Applied %d quant adjustments for session %s",
                len(quants_to_apply), self.id
            )

    # ============================================================
    # CRON: QUARTERLY AUTO-CREATE
    # ============================================================

    @api.model
    def action_trigger_quarterly_inventory(self):
        """Cron: if today is a quarterly date, create a new draft session.

        Trigger dates: January 1, April 1, July 1, October 1.
        Creates a draft session using the most recent completed/approved session as template.
        Admin still needs to assign teams and click Start.
        """
        try:
            today = fields.Date.today()

            trigger_months = [1, 4, 7, 10]
            if today.month not in trigger_months or today.day != 1:
                return False

            _logger.info("[Inventory Cron] Trigger date: %s", today)

            # Check for existing session on this date
            existing = self.search([
                ('date', '=', today),
                ('state', 'in', ['draft', 'active', 'pending_approval', 'approved']),
            ], limit=1)
            if existing:
                _logger.info("[Inventory Cron] Session already exists for %s, skipping", today)
                return True

            # Use last session as template for location
            last_session = self.search([
                ('state', 'in', ['approved', 'active', 'pending_approval']),
            ], order='date desc', limit=1)

            quarter_names = {1: 'Q1', 4: 'Q2', 7: 'Q3', 10: 'Q4'}
            session_name = f"Inventaire {quarter_names[today.month]} {today.year}"

            vals = {
                'name': session_name,
                'date': today,
                'duration_days': last_session.duration_days if last_session else 2,
                'location_id': last_session.location_id.id if last_session else False,
            }

            session = self.create(vals)
            _logger.info("[Inventory Cron] Created draft session %s (id=%s)", session.name, session.id)
            return True

        except Exception as e:
            _logger.error("[Inventory Cron] Error: %s", str(e))
            return False


class ClinicInventoryTeam(models.Model):
    _name = 'clinic.inventory.team'
    _description = 'Inventory Counting Team'
    _order = 'inventory_id, name'

    inventory_id = fields.Many2one(
        'clinic.inventory',
        'Inventory Session',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char('Team Name', required=True, help='e.g., "Team A", "Team B"')
    user_ids = fields.Many2many(
        'res.users',
        'clinic_inventory_team_user_rel',
        'team_id',
        'user_id',
        string='Assigned Users',
    )
    submitted_user_ids = fields.Many2many(
        'res.users',
        'clinic_inventory_team_submitted_rel',
        'team_id',
        'user_id',
        string='Submitted Users',
        help='Users who have finished counting and clicked Valider',
    )

    line_count = fields.Integer('Line Count', compute='_compute_line_count', store=False)

    @api.depends('inventory_id.line_ids')
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.inventory_id.line_ids.filtered(
                lambda l: l.team_id.id == record.id
            ))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if any('user_ids' in vals for vals in vals_list):
            self.env['clinic.inventory']._sync_tile_visibility()
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'user_ids' in vals:
            self.env['clinic.inventory']._sync_tile_visibility()
        return result

    def unlink(self):
        result = super().unlink()
        self.env['clinic.inventory']._sync_tile_visibility()
        return result


class ClinicInventoryLine(models.Model):
    _name = 'clinic.inventory.line'
    _description = 'Inventory Count Line'
    _order = 'inventory_id, product_id, lot_id'

    inventory_id = fields.Many2one(
        'clinic.inventory',
        'Inventory Session',
        required=True,
        ondelete='cascade',
        index=True,
    )
    team_id = fields.Many2one(
        'clinic.inventory.team',
        'Team',
        required=True,
        index=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        'Product',
        required=True,
        index=True,
        domain="[('active', '=', True)]",
    )
    lot_id = fields.Many2one(
        'stock.lot',
        'Lot/Serial',
        index=True,
    )
    expiry_date = fields.Date(
        'Expiry Date',
        compute='_compute_expiry_date',
        store=True,
        readonly=False,
        help='Auto-populated from lot expiration date. Can be overridden manually.',
    )
    qty_counted = fields.Float(
        'Quantity Counted',
        required=True,
        default=0.0,
    )
    note = fields.Char('Notes')

    # Computed fields (store=True for PDF performance)
    qty_system = fields.Float(
        'System Stock',
        compute='_compute_qty_system',
        store=True,
    )
    uom_id = fields.Many2one(
        'uom.uom',
        'Unit of Measure',
        related='product_id.uom_id',
        store=True,
        readonly=True,
    )
    variance = fields.Float(
        'Variance',
        compute='_compute_variance',
        store=True,
    )

    @api.depends('lot_id')
    def _compute_expiry_date(self):
        for record in self:
            if record.lot_id:
                exp = getattr(record.lot_id, 'expiration_date', None)
                if exp:
                    record.expiry_date = exp.date() if hasattr(exp, 'date') else exp
            # No lot or lot has no expiration: leave expiry_date unchanged (manual value preserved)

    @api.depends('product_id', 'lot_id', 'inventory_id.location_id')
    def _compute_qty_system(self):
        StockQuant = self.env['stock.quant'].sudo()
        for record in self:
            if not record.product_id or not record.inventory_id:
                record.qty_system = 0.0
                continue
            quant = StockQuant.search([
                ('product_id', '=', record.product_id.id),
                ('lot_id', '=', record.lot_id.id if record.lot_id else False),
                ('location_id', '=', record.inventory_id.location_id.id),
            ], limit=1)
            record.qty_system = quant.quantity if quant else 0.0

    @api.depends('qty_counted', 'qty_system')
    def _compute_variance(self):
        for record in self:
            record.variance = record.qty_counted - record.qty_system
