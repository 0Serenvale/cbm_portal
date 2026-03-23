# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductPricelist(models.Model):
    """Extend pricelist to support convention/insurance split payments."""
    _inherit = 'product.pricelist'
    
    # Convention fields for split payment calculation
    convention_coverage_pct = fields.Float(
        string="Convention Coverage %",
        help="Percentage of invoice covered by the convention (0-100). "
             "For example, 80 means 80% covered by payer, 20% by patient.",
        default=0.0,
    )
    
    payer_partner_id = fields.Many2one(
        'res.partner',
        string="Payer (Convention Body)",
        help="The insurance/convention partner (e.g., CNAS, CASNOS) "
             "who will be billed for the convention share.",
    )
    
    payer_journal_id = fields.Many2one(
        'account.journal',
        string="Payer Journal",
        domain=[('type', 'in', ['sale', 'general'])],
        help="Journal to record the receivable from the convention payer. "
             "Typically an Accounts Receivable journal for the payer.",
    )
    
    @api.constrains('convention_coverage_pct')
    def _check_coverage_pct(self):
        for pricelist in self:
            if pricelist.convention_coverage_pct < 0 or pricelist.convention_coverage_pct > 100:
                raise models.ValidationError(
                    "Convention coverage percentage must be between 0 and 100."
                )
