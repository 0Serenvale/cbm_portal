# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class StockLocation(models.Model):
    _inherit = 'stock.location'

    # Note: require_approval and responsible_user_ids fields are defined
    # in serenvale_stock_access_control (our dependency)

    # --- Anti-Hoarding Policy ---
    replenishment_policy = fields.Selection([
        ('none', 'No Restriction'),
        ('soft', 'Soft Warning'),
        ('hard', 'Hard Block')
    ], string="Anti-Hoarding Policy", default='none',
       help="Controls whether to warn or block requests when stock already exists at this location.")

    consumption_start_date = fields.Date(
        string="Trust Data From",
        help="The system ignores all stock history before this date when calculating 'trusted' inventory. "
             "Set this to ignore old/incorrect data (e.g., set to today to start fresh).")

    # Note: default_product_template_id field is defined in serenvale_purchase_portal module

    # --- Quick Pick System ---
    quick_pick_product_ids = fields.Many2many(
        'product.product',
        'location_quick_pick_product_rel',
        'location_id',
        'product_id',
        string='Produits Quick Pick',
        domain="[('type', '=', 'product')]",
        help='Produits fréquemment consommés à cet emplacement (max 15). '
             'Affichés comme boutons rapides dans le kiosque CBM.'
    )

    quick_pick_count = fields.Integer(
        string='Nombre Quick Pick',
        compute='_compute_quick_pick_count'
    )

    enable_quick_pick = fields.Boolean(
        string='Activer Quick Pick',
        default=False,
        help='Afficher la grille Quick Pick dans le kiosque CBM pour cet emplacement'
    )

    @api.depends('quick_pick_product_ids')
    def _compute_quick_pick_count(self):
        """Count quick pick products."""
        for location in self:
            location.quick_pick_count = len(location.quick_pick_product_ids)

    @api.constrains('quick_pick_product_ids')
    def _check_quick_pick_limit(self):
        """Enforce max 15 products in quick pick list."""
        for location in self:
            if len(location.quick_pick_product_ids) > 15:
                raise ValidationError(
                    'La liste Quick Pick ne peut pas dépasser 15 produits. '
                    'Veuillez sélectionner uniquement les articles les plus fréquemment consommés.'
                )
