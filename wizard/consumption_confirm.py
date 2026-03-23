# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockConsumptionConfirm(models.TransientModel):
    """
    Confirmation Wizard for Patient Consumption.
    Forces a double-check before consuming stock and creating billing.
    """
    _name = 'stock.consumption.confirm'
    _description = 'Consumption Confirmation Wizard'

    picking_id = fields.Many2one('stock.picking', required=True)
    partner_id = fields.Many2one(
        'res.partner', 
        related='picking_id.partner_id', 
        readonly=True, 
        string="Patient")
    location_id = fields.Many2one(
        'stock.location',
        related='picking_id.location_id',
        readonly=True,
        string="From Location")
    
    # Summary of items to consume (computed HTML)
    summary_lines = fields.Html(
        string="Items Summary",
        compute='_compute_summary')
    
    item_count = fields.Integer(
        string="Total Items",
        compute='_compute_summary')

    @api.depends('picking_id', 'picking_id.move_ids_without_package')
    def _compute_summary(self):
        for wiz in self:
            html = "<ul style='font-size: 14px; margin: 0; padding-left: 20px;'>"
            count = 0
            
            for line in wiz.picking_id.move_ids_without_package:
                if line.product_uom_qty > 0:
                    html += (
                        f"<li><b>{line.product_id.display_name}</b>: "
                        f"{line.product_uom_qty} {line.product_uom.name}</li>"
                    )
                    count += 1
                    
            html += "</ul>"
            
            if count == 0:
                html = "<p style='color: #999;'>No items to consume</p>"
            
            wiz.summary_lines = html
            wiz.item_count = count

    def action_confirm_consumption(self):
        """
        The Real Execution. Called only when user clicks CONFIRM.
        Propagates context and calls the actual billing logic.
        """
        self.ensure_one()
        
        # Validate we have items
        if self.item_count == 0:
            raise UserError(_("Cannot confirm: No items to consume."))
        
        # Get behavior from picking
        behavior = self.picking_id.portal_behavior
        
        # Call the actual execution logic with proper context
        return self.picking_id.with_context(
            portal_stock_behavior=behavior
        )._execute_consumption_submit()
