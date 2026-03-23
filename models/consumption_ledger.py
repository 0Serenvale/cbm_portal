# -*- coding: utf-8 -*-
"""
Consumption Ledger - Source of truth for patient consumption tracking.

This model tracks every stock movement (consumption and return) for patient billing.
It solves the lot traceability problem by recording the exact lot_id at the moment
of stock validation, enabling accurate returns with the correct lot.

Key features:
- Records exact lot_id from validated stock.move.line
- LIFO returns: most recent consumption returned first
- 3-month retention for audit/fraud detection
- Indexed for fast lookups by SO, patient, product
"""

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ConsumptionLedger(models.Model):
    _name = 'clinic.consumption.ledger'
    _description = 'Patient Consumption Ledger'
    _order = 'create_date desc, id desc'  # LIFO: newest first for returns
    _rec_name = 'display_name'

    # Core links
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        required=True,
        index=True,
        ondelete='cascade',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Patient',
        required=True,
        index=True,
        ondelete='restrict',
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Source Location',
        required=True,
        help='Location stock was consumed from (e.g., Hospitalisation)',
    )

    # Product and lot (the critical traceability data)
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        index=True,
        ondelete='restrict',
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lot',
        index=True,
        ondelete='restrict',
        help='Exact lot that was physically moved. Critical for accurate returns.',
    )

    # Quantities
    qty_consumed = fields.Float(
        string='Qty Consumed',
        digits='Product Unit of Measure',
        required=True,
        help='Original quantity consumed in this entry',
    )
    qty_returned = fields.Float(
        string='Qty Returned',
        digits='Product Unit of Measure',
        default=0.0,
        help='How much of this entry has been returned',
    )
    qty_available = fields.Float(
        string='Qty Available for Return',
        compute='_compute_qty_available',
        store=True,
        digits='Product Unit of Measure',
        help='qty_consumed - qty_returned',
    )

    # Stock movement links (for audit trail)
    picking_id = fields.Many2one(
        'stock.picking',
        string='Consumption Picking',
        index=True,
        ondelete='set null',
        help='The stock picking that consumed this stock',
    )
    move_line_id = fields.Many2one(
        'stock.move.line',
        string='Move Line',
        ondelete='set null',
        help='Exact stock.move.line for complete traceability',
    )

    # Return tracking
    return_picking_ids = fields.Many2many(
        'stock.picking',
        'consumption_ledger_return_picking_rel',
        'ledger_id',
        'picking_id',
        string='Return Pickings',
        help='Pickings that returned stock from this ledger entry',
    )

    # State
    state = fields.Selection([
        ('active', 'Active'),
        ('fully_returned', 'Fully Returned'),
        ('archived', 'Archived'),
    ], string='State', default='active', index=True)

    # Display
    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('qty_consumed', 'qty_returned')
    def _compute_qty_available(self):
        for rec in self:
            rec.qty_available = rec.qty_consumed - rec.qty_returned

    @api.depends('product_id', 'lot_id', 'qty_consumed')
    def _compute_display_name(self):
        for rec in self:
            lot_name = f" [{rec.lot_id.name}]" if rec.lot_id else ""
            rec.display_name = f"{rec.product_id.name}{lot_name} x {rec.qty_consumed}"

    def init(self):
        """Create database indexes for optimal query performance."""
        # Composite index for the most common query pattern:
        # "Get all active ledger entries for a patient's SO"
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS consumption_ledger_so_partner_state_idx
            ON clinic_consumption_ledger (sale_order_id, partner_id, state)
            WHERE state = 'active';
        """)

        # Index for product lookups within an SO (for delta calculation)
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS consumption_ledger_so_product_idx
            ON clinic_consumption_ledger (sale_order_id, product_id);
        """)

        # Index for LIFO returns: newest entries first for a product in an SO
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS consumption_ledger_lifo_idx
            ON clinic_consumption_ledger (sale_order_id, product_id, create_date DESC, id DESC)
            WHERE state = 'active' AND qty_available > 0;
        """)

        # Index for cleanup cron (find old archived entries)
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS consumption_ledger_cleanup_idx
            ON clinic_consumption_ledger (state, create_date)
            WHERE state = 'archived';
        """)

        _logger.info("Consumption ledger indexes created/verified")

    @api.model
    def get_patient_consumption(self, sale_order_id):
        """
        Get aggregated consumption for a patient's SO.
        Returns dict: {product_id: {'qty': total, 'entries': ledger_records}}

        This is the source of truth for loading patient data in the portal.
        """
        entries = self.search([
            ('sale_order_id', '=', sale_order_id),
            ('state', '=', 'active'),
        ], order='product_id, create_date desc, id desc')

        result = {}
        for entry in entries:
            pid = entry.product_id.id
            if pid not in result:
                result[pid] = {
                    'product_id': pid,
                    'qty': 0.0,
                    'entries': self.env['clinic.consumption.ledger'],
                }
            result[pid]['qty'] += entry.qty_available
            result[pid]['entries'] |= entry

        return result

    @api.model
    def get_entries_for_return(self, sale_order_id, product_id, qty_to_return):
        """
        Get ledger entries to use for a return, using LIFO.
        Returns list of (entry, qty_from_entry, lot_id) tuples.

        Example: need to return 5 units
        - Entry 1 (newest): qty_available=3, lot=A -> return 3 from lot A
        - Entry 2 (older): qty_available=4, lot=B -> return 2 from lot B
        Total: 5 units returned from 2 lots
        """
        entries = self.search([
            ('sale_order_id', '=', sale_order_id),
            ('product_id', '=', product_id),
            ('state', '=', 'active'),
            ('qty_available', '>', 0),
        ], order='create_date desc, id desc')  # LIFO

        result = []
        remaining = qty_to_return

        for entry in entries:
            if remaining <= 0:
                break
            take = min(entry.qty_available, remaining)
            result.append({
                'entry': entry,
                'qty': take,
                'lot_id': entry.lot_id.id if entry.lot_id else False,
            })
            remaining -= take

        if remaining > 0:
            _logger.warning(
                "Return qty exceeds available: SO=%s, product=%s, requested=%.2f, short=%.2f",
                sale_order_id, product_id, qty_to_return, remaining
            )

        return result

    def mark_returned(self, qty, return_picking_id=False):
        """Mark a quantity as returned from this ledger entry."""
        self.ensure_one()
        new_returned = self.qty_returned + qty
        vals = {'qty_returned': new_returned}

        if new_returned >= self.qty_consumed:
            vals['state'] = 'fully_returned'

        if return_picking_id:
            vals['return_picking_ids'] = [(4, return_picking_id)]

        self.write(vals)
        _logger.info(
            "Ledger %s: marked %.2f returned (total returned: %.2f/%0.2f)",
            self.id, qty, new_returned, self.qty_consumed
        )

    @api.model
    def create_from_move_line(self, move_line, sale_order_id):
        """
        Create ledger entry from a validated stock.move.line.
        Called after consumption picking is validated.
        """
        return self.create({
            'sale_order_id': sale_order_id,
            'partner_id': move_line.picking_id.partner_id.id,
            'location_id': move_line.location_id.id,
            'product_id': move_line.product_id.id,
            'lot_id': move_line.lot_id.id if move_line.lot_id else False,
            'qty_consumed': move_line.qty_done,
            'picking_id': move_line.picking_id.id,
            'move_line_id': move_line.id,
        })

    @api.model
    def migrate_from_sale_order(self, sale_order):
        """
        Migration fallback: Create ledger entries from existing SO + stock history.
        Used when loading a patient with existing SO but no ledger entries.
        """
        _logger.info("Migrating SO %s to consumption ledger", sale_order.name)

        # Find all done consumption pickings for this SO's patient
        # that have products matching SO lines
        pickings = self.env['stock.picking'].search([
            ('partner_id', '=', sale_order.partner_id.id),
            ('state', '=', 'done'),
            ('portal_behavior', '=', 'billable'),
        ], order='date_done desc')

        created_entries = self.env['clinic.consumption.ledger']
        so_products = {line.product_id.id: line for line in sale_order.order_line}

        for picking in pickings:
            for move_line in picking.move_line_ids:
                if move_line.product_id.id in so_products:
                    # Check if we already have enough in ledger
                    existing_qty = sum(
                        e.qty_consumed for e in created_entries
                        if e.product_id.id == move_line.product_id.id
                    )
                    so_qty = so_products[move_line.product_id.id].product_uom_qty

                    if existing_qty < so_qty:
                        # Need more, create entry
                        take_qty = min(move_line.qty_done, so_qty - existing_qty)
                        entry = self.create({
                            'sale_order_id': sale_order.id,
                            'partner_id': sale_order.partner_id.id,
                            'location_id': move_line.location_id.id,
                            'product_id': move_line.product_id.id,
                            'lot_id': move_line.lot_id.id if move_line.lot_id else False,
                            'qty_consumed': take_qty,
                            'picking_id': picking.id,
                            'move_line_id': move_line.id,
                        })
                        created_entries |= entry
                        _logger.info(
                            "Migrated: %s x %.2f (lot=%s) from %s",
                            move_line.product_id.name, take_qty,
                            move_line.lot_id.name if move_line.lot_id else 'N/A',
                            picking.name
                        )

        return created_entries

    @api.model
    def cleanup_old_entries(self, months=3):
        """
        Cron job: Archive entries older than X months.
        Does NOT delete - keeps for audit trail.
        """
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=months * 30)

        old_entries = self.search([
            ('state', 'in', ['active', 'fully_returned']),
            ('create_date', '<', cutoff),
            ('sale_order_id.state', 'in', ['done', 'cancel']),  # Only if SO is closed
        ])

        if old_entries:
            old_entries.write({'state': 'archived'})
            _logger.info("Archived %d old consumption ledger entries", len(old_entries))

        return True
