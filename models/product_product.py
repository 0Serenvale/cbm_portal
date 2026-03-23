# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    discrepancy_count = fields.Integer(
        string='Discrepancies',
        compute='_compute_discrepancy_count',
        help='Number of pending stock discrepancy alerts for this product'
    )

    def _compute_discrepancy_count(self):
        """Count pending discrepancy alerts for this product."""
        for product in self:
            product.discrepancy_count = self.env['clinic.stock.discrepancy'].search_count([
                ('product_id', '=', product.id),
                ('state', '=', 'pending')
            ])

    def action_open_drug_sync_wizard(self):
        """Delegate to product.template so the button works on product.product form."""
        self.ensure_one()
        return self.product_tmpl_id.action_open_drug_sync_wizard()

    def action_view_discrepancies(self):
        """Open discrepancy alerts for this product."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Stock Discrepancies',
            'res_model': 'clinic.stock.discrepancy',
            'view_mode': 'tree,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('product_id', '=', self.id), ('state', '=', 'pending')],
            'context': {'default_product_id': self.id},
        }

    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        """
        Override name_search to:
        1. Filter by location when portal_source_location_id in context
        2. Search by barcode and lot.ref in addition to product name
        """
        args = args or []

        # Check if we're in portal mode with a specific source location
        portal_location_id = self.env.context.get('portal_source_location_id')

        if portal_location_id:
            # Find ALL products that have quant records at this location (any quantity)
            quants = self.env['stock.quant'].sudo().search([
                ('location_id', '=', portal_location_id),
            ])
            product_ids = quants.mapped('product_id').ids

            if product_ids:
                args = args + [('id', 'in', product_ids)]
            else:
                # No products at location, return empty
                args = args + [('id', '=', -1)]

        # First, search by barcode (exact match)
        if name:
            barcode_product = self.search([('barcode', '=', name.strip())] + args, limit=limit)
            if barcode_product:
                return barcode_product._name_get()

            # Search by lot.ref (for scanned lot barcodes)
            lot = self.env['stock.lot'].search([('ref', '=', name.strip())], limit=1)
            if lot:
                matching = self.search([('id', '=', lot.product_id.id)] + args, limit=limit)
                if matching:
                    return matching._name_get()

        # Fall back to standard search (name, default_code, etc.)
        return super()._name_search(
            name=name,
            args=args,
            operator=operator,
            limit=limit,
            name_get_uid=name_get_uid,
        )
