# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ClinicInventory(models.Model):
    _name = 'clinic.inventory'
    _description = 'Physical Inventory Session'
    _order = 'date desc, id desc'

    name = fields.Char('Session Name', required=True, translate=True)
    date = fields.Date('Session Date', required=True, default=fields.Date.today)
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
    ], string='State', default='draft', readonly=True, tracking=True)

    team_ids = fields.One2many(
        'clinic.inventory.team',
        'inventory_id',
        string='Teams',
        help='Teams assigned to this inventory session'
    )
    line_ids = fields.One2many(
        'clinic.inventory.line',
        'inventory_id',
        string='Count Lines',
        help='Inventory count lines (product counts per team)'
    )

    responsible_id = fields.Many2one(
        'res.users',
        'Responsible Manager',
        required=True,
        default=lambda self: self.env.user,
        help='Manager responsible for creating and approving this inventory'
    )
    notes = fields.Text('Notes')

    # Computed fields
    team_count = fields.Integer('Team Count', compute='_compute_team_count', store=False)
    line_count = fields.Integer('Line Count', compute='_compute_line_count', store=False)

    @api.depends('team_ids')
    def _compute_team_count(self):
        """Count number of teams in this inventory session"""
        for record in self:
            record.team_count = len(record.team_ids)

    @api.depends('line_ids')
    def _compute_line_count(self):
        """Count number of lines in this inventory session"""
        for record in self:
            record.line_count = len(record.line_ids)

    def action_start(self):
        """Start inventory counting (state: draft → active)"""
        self.ensure_one()
        if self.state != 'draft':
            raise ValueError('Only draft inventories can be started')
        self.write({'state': 'active'})
        _logger.info(f"[Inventory] Session {self.id} ({self.name}) started by {self.env.user.name}")
        return True

    def action_submit(self):
        """Submit inventory for approval (state: active → pending_approval)"""
        self.ensure_one()
        if self.state != 'active':
            raise ValueError('Only active inventories can be submitted for approval')
        if not self.line_ids:
            raise ValueError('Cannot submit inventory without counted lines')
        self.write({'state': 'pending_approval'})
        _logger.info(f"[Inventory] Session {self.id} ({self.name}) submitted for approval")
        return True

    def action_approve(self):
        """Approve inventory and apply to stock (state: pending_approval → approved)"""
        self.ensure_one()
        if self.state != 'pending_approval':
            raise ValueError('Only pending_approval inventories can be approved')

        # Apply stock adjustments
        self._apply_stock_adjustments()

        self.write({'state': 'approved'})
        _logger.info(f"[Inventory] Session {self.id} ({self.name}) approved by {self.env.user.name}")
        return True

    def action_cancel(self):
        """Cancel inventory session (any state → cancelled)"""
        self.ensure_one()
        if self.state == 'approved':
            raise ValueError('Cannot cancel already approved inventories')
        self.write({'state': 'cancelled'})
        _logger.info(f"[Inventory] Session {self.id} ({self.name}) cancelled")
        return True

    def _apply_stock_adjustments(self):
        """Apply counted inventory to stock.quant.inventory_quantity, then trigger Odoo's adjustment"""
        self.ensure_one()
        StockQuant = self.env['stock.quant']

        for line in self.line_ids:
            # Find or create stock.quant record for this product/lot/location combination
            quant = StockQuant.search([
                ('product_id', '=', line.product_id.id),
                ('lot_id', '=', line.lot_id.id if line.lot_id else False),
                ('location_id', '=', self.location_id.id),
            ], limit=1)

            if quant:
                # Set inventory_quantity to the counted quantity
                # Odoo will calculate adjustment when action_apply_inventory is called
                quant.write({'inventory_quantity': line.qty_counted})
                _logger.debug(
                    f"[Inventory] Updated quant {quant.id}: product={line.product_id.name}, "
                    f"lot={line.lot_id.name if line.lot_id else 'none'}, "
                    f"inventory_qty={line.qty_counted}"
                )
            else:
                # Create new quant if it doesn't exist
                quant = StockQuant.create({
                    'product_id': line.product_id.id,
                    'lot_id': line.lot_id.id if line.lot_id else False,
                    'location_id': self.location_id.id,
                    'quantity': 0,
                    'inventory_quantity': line.qty_counted,
                })
                _logger.debug(
                    f"[Inventory] Created new quant {quant.id}: product={line.product_id.name}, "
                    f"inventory_qty={line.qty_counted}"
                )

        # Trigger Odoo's stock adjustment workflow
        # This creates stock.move records and adjusts quantities
        quants = StockQuant.search([
            ('location_id', '=', self.location_id.id),
            ('product_id', 'in', self.line_ids.mapped('product_id').ids),
        ])
        quants.action_apply_inventory()
        _logger.info(f"[Inventory] Applied {len(quants)} quant adjustments for session {self.id}")


class ClinicInventoryTeam(models.Model):
    _name = 'clinic.inventory.team'
    _description = 'Inventory Counting Team'
    _order = 'inventory_id, name'

    inventory_id = fields.Many2one(
        'clinic.inventory',
        'Inventory Session',
        required=True,
        cascade='cascade',
        index=True,
        help='Parent inventory session'
    )
    name = fields.Char('Team Name', required=True, help='e.g., "Team A", "Team B"')
    user_ids = fields.Many2many(
        'res.users',
        'clinic_inventory_team_user_rel',
        'team_id',
        'user_id',
        string='Assigned Users',
        help='Users assigned to count for this team'
    )

    # Computed field
    line_count = fields.Integer('Line Count', compute='_compute_line_count', store=False)

    @api.depends('inventory_id.line_ids')
    def _compute_line_count(self):
        """Count lines belonging to this team"""
        for record in self:
            record.line_count = len(record.inventory_id.line_ids.filtered(
                lambda l: l.team_id.id == record.id
            ))


class ClinicInventoryLine(models.Model):
    _name = 'clinic.inventory.line'
    _description = 'Inventory Count Line'
    _order = 'inventory_id, product_id, lot_id'

    inventory_id = fields.Many2one(
        'clinic.inventory',
        'Inventory Session',
        required=True,
        cascade='cascade',
        index=True,
        help='Parent inventory session'
    )
    team_id = fields.Many2one(
        'clinic.inventory.team',
        'Team',
        required=True,
        index=True,
        ondelete='cascade',
        help='Team that counted this line'
    )
    product_id = fields.Many2one(
        'product.product',
        'Product',
        required=True,
        index=True,
        domain="[('active', '=', True)]",
        help='Product being counted'
    )
    lot_id = fields.Many2one(
        'stock.production.lot',
        'Lot/Serial',
        index=True,
        help='Lot or serial number of the product (optional)'
    )
    expiry_date = fields.Date(
        'Expiry Date',
        help='Expiry date (optional, extracted from barcode scan if GS1-128 encoded)'
    )
    qty_counted = fields.Float(
        'Quantity Counted',
        required=True,
        default=0.0,
        help='Actual quantity counted by the team'
    )
    note = fields.Char('Notes', help='Additional notes for this line')

    # Computed fields (with store=True for PDF performance)
    qty_system = fields.Float(
        'System Stock',
        compute='_compute_qty_system',
        store=True,
        help='Snapshot of system quantity at time of line creation'
    )
    uom_id = fields.Many2one(
        'uom.uom',
        'Unit of Measure',
        related='product_id.uom_id',
        store=True,
        readonly=True
    )
    variance = fields.Float(
        'Variance',
        compute='_compute_variance',
        store=True,
        help='Variance = Quantity Counted - System Stock (positive = overstocked, negative = understocked)'
    )

    @api.depends('product_id', 'lot_id', 'inventory_id.location_id')
    def _compute_qty_system(self):
        """Get current system stock quantity from stock.quant"""
        StockQuant = self.env['stock.quant']
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
        """Calculate variance: counted - system"""
        for record in self:
            record.variance = record.qty_counted - record.qty_system
