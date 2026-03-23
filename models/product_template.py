# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # --- Drug registration fields (readonly — filled by wizard only) ---
    openmrs_concept_uuid = fields.Char(
        string='Active Ingredient (DCI)',
        readonly=True,
        help='International Common Denomination linked to this drug'
    )
    dosage_form_id = fields.Many2one(
        'drug.dosage.form',
        string='Dosage Form',
        readonly=True,
        help='Pharmaceutical dosage form (tablet, injection, syrup, etc.)'
    )
    strength = fields.Char(
        string='Strength', readonly=True,
        help='Drug strength (e.g. 500 mg, 10 mg/ml)'
    )
    is_synced_to_openmrs = fields.Boolean(
        string='Registered',
        default=False,
        readonly=True,
    )

    def action_open_drug_sync_wizard(self):
        """Open the drug registration wizard."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Drug Registration',
            'res_model': 'drug.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_tmpl_id': self.id,
                'default_drug_name': self.name,
                'default_strength': self.strength or '',
            },
        }
