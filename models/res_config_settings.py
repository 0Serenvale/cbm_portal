# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Global Pharmacy/Warehouse Location
    clinic_pharmacy_location_id = fields.Many2one(
        'stock.location',
        string='Pharmacy Location',
        config_parameter='clinic_staff_portal.pharmacy_location_id',
        domain="[('usage', '=', 'internal')]",
        help='Central pharmacy location. Source for medication requests.')
    
    # Patient/Virtual Location for consumption
    clinic_patient_location_id = fields.Many2one(
        'stock.location',
        string='Patient Location',
        config_parameter='clinic_staff_portal.patient_location_id',
        domain="[('usage', 'in', ['customer', 'production'])]",
        help='Virtual location for consumed items (destination).')
    
    # Magasin (Supplies) Location
    clinic_magasin_location_id = fields.Many2one(
        'stock.location',
        string='Magasin Location',
        config_parameter='clinic_staff_portal.magasin_location_id',
        domain="[('usage', '=', 'internal')]",
        help='Supplies/warehouse location for non-pharmacy consumption.')
    
    # Maintenance Location
    clinic_maintenance_location_id = fields.Many2one(
        'stock.location',
        string='Maintenance Location',
        config_parameter='clinic_staff_portal.maintenance_location_id',
        domain="[('usage', '=', 'internal')]",
        help='Maintenance supplies location.')
    
    # Informatique Location
    clinic_informatique_location_id = fields.Many2one(
        'stock.location',
        string='Informatique Location',
        config_parameter='clinic_staff_portal.informatique_location_id',
        domain="[('usage', '=', 'internal')]",
        help='IT supplies location.')
    
    # Cuisine Location
    clinic_cuisine_location_id = fields.Many2one(
        'stock.location',
        string='Cuisine Location',
        config_parameter='clinic_staff_portal.cuisine_location_id',
        domain="[('usage', '=', 'internal')]",
        help='Kitchen/food supplies location.')
    
    # --- CBM Portal Global Settings ---
    
    # Lot Selection Mode
    clinic_lot_selection_mode = fields.Selection([
        ('auto_fefo', 'Auto-Select (First Expiry First Out)'),
        ('manual', 'Manual Selection (Show Lot Dropdown)'),
    ], string='Lot Selection Mode',
       config_parameter='clinic_staff_portal.lot_selection_mode',
       default='auto_fefo',
       help='How to handle lot selection for lot-tracked products:\n'
            'Auto FEFO: Automatically select the lot with earliest expiry date.\n'
            'Manual: Show a dropdown for user to select lot.')
    
    # Stock Alert Visibility
    clinic_stock_alert_visibility = fields.Selection([
        ('admin_only', 'Administrators Only'),
        ('all', 'All Users'),
        ('none', 'Hidden'),
    ], string='Stock Discrepancy Alerts',
       config_parameter='clinic_staff_portal.stock_alert_visibility',
       default='admin_only',
       help='Who can see stock discrepancy alerts in the portal:\n'
            'Admin Only: Only administrators see alerts.\n'
            'All: All portal users see alerts.\n'
            'None: Alerts are hidden (still logged).')
    
    # --- Pending Enforcement Settings ---
    
    # Enable/Disable Enforcement
    clinic_pending_enforcement_enabled = fields.Boolean(
        string='Enable Pending Enforcement',
        config_parameter='clinic_staff_portal.pending_enforcement_enabled',
        default=False,
        help='When enabled, show visual warnings on sidebar chips when pending '
             'transfers or purchase orders exceed thresholds.')
    
    # Transfer Thresholds
    clinic_pending_transfer_warn_threshold = fields.Integer(
        string='Transfer Warning Threshold',
        config_parameter='clinic_staff_portal.pending_transfer_warn_threshold',
        default=5,
        help='Show warning when pending transfers exceed this count. Set to 0 to disable.')
    
    clinic_pending_transfer_block_threshold = fields.Integer(
        string='Transfer Block Threshold',
        config_parameter='clinic_staff_portal.pending_transfer_block_threshold',
        default=0,
        help='Block portal access when pending transfers exceed this count. '
             'Set to 0 to disable blocking (warnings only).')
    
    # Purchase Order Thresholds (by age in days)
    clinic_pending_po_warn_days = fields.Integer(
        string='PO Warning Days',
        config_parameter='clinic_staff_portal.pending_po_warn_days',
        default=7,
        help='Show warning for purchase orders older than this many days. Set to 0 to disable.')
    
    clinic_pending_po_block_days = fields.Integer(
        string='PO Block Days',
        config_parameter='clinic_staff_portal.pending_po_block_days',
        default=0,
        help='Block portal access for purchase orders older than this many days. '
             'Set to 0 to disable blocking (warnings only).')
    
    # --- Accountability & Financial Dashboard ---
    
    accountability_start_date = fields.Datetime(
        string='Date de Responsabilité',
        config_parameter='clinic_staff_portal.accountability_start_date',
        help='"Day Zero" for the portal. Enforcement only counts data from this date forward.')

    clinic_accountability_cron_enabled = fields.Boolean(
        string='Accountability Warnings',
        config_parameter='clinic_staff_portal.accountability_cron_enabled',
        default=True,
        help='Enable daily cron that sends validation delay warnings and DRH escalations.')
    
    drh_user_id = fields.Many2one(
        'res.users',
        string='Liaison RH',
        domain="[('share', '=', False)]",
        help='Human Resources liaison who receives escalation notifications.')
    
    executive_user_ids = fields.Many2many(
        'res.users',
        'clinic_staff_portal_executive_users_rel',
        'config_id',
        'user_id',
        string='Directeurs Exécutifs',
        domain="[('share', '=', False)]",
        help='Users who can see the financial dashboard (gains/losses).')
    
    admin_user_ids = fields.Many2many(
        'res.users',
        'clinic_staff_portal_admin_users_rel',
        'config_id',
        'user_id',
        string='Portal Administrators',
        domain="[('share', '=', False)]",
        help='Users with full portal access - can see all pending work across all users.')
    
    # --- Director Stamp & Signature (for compliance report PDFs) ---

    director_signature = fields.Binary(
        'Director Signature',
        help='PNG image of the director signature (transparent background recommended).')
    director_stamp = fields.Binary(
        'Director Stamp',
        help='PNG image of the official stamp (transparent background recommended).')
    director_name = fields.Char(
        'Director Name',
        help='Full name of the director, printed below signature on reports.')
    director_title = fields.Char(
        'Director Title', default='Directeur',
        help='Title/function of the director on compliance reports.')

    # --- Cashier Module Settings ---
    
    cashier_cash_journal_id = fields.Many2one(
        'account.journal',
        string='Cash Journal',
        config_parameter='clinic_staff_portal.cashier_cash_journal_id',
        domain="[('type', '=', 'cash')]",
        help='Journal for cash payments at the cashier.')
    
    cashier_card_journal_id = fields.Many2one(
        'account.journal',
        string='Card Journal',
        config_parameter='clinic_staff_portal.cashier_card_journal_id',
        domain="[('type', '=', 'bank')]",
        help='Journal for card payments at the cashier.')
    
    cashier_cheque_journal_id = fields.Many2one(
        'account.journal',
        string='Cheque Journal',
        config_parameter='clinic_staff_portal.cashier_cheque_journal_id',
        domain="[('type', '=', 'bank')]",
        help='Journal for cheque payments at the cashier.')
    
    cashier_convention_journal_id = fields.Many2one(
        'account.journal',
        string='Convention Journal',
        config_parameter='clinic_staff_portal.cashier_convention_journal_id',
        domain="[('type', 'in', ['sale', 'general'])]",
        help='Journal for convention/insurance receivables (e.g., CNAS, CASNOS).')
    
    cashier_loss_account_id = fields.Many2one(
        'account.account',
        string='Refund Loss Account',
        config_parameter='clinic_staff_portal.cashier_loss_account_id',
        domain="[('account_type', 'in', ['expense', 'expense_direct_cost'])]",
        help='Account for writing off refund differences (partial close mode).')
    
    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        
        # DRH user
        drh_id_str = ICP.get_param('clinic_staff_portal.drh_user_id', '')
        if drh_id_str and drh_id_str.isdigit():
            res['drh_user_id'] = int(drh_id_str)
        
        # Executive users
        exec_str = ICP.get_param('clinic_staff_portal.executive_user_ids', '')
        exec_ids = [int(i) for i in exec_str.split(',') if i.strip().isdigit()]
        res['executive_user_ids'] = [(6, 0, exec_ids)]
        
        # Admin users (portal full access)
        admin_str = ICP.get_param('clinic_staff_portal.admin_user_ids', '')
        admin_ids = [int(i) for i in admin_str.split(',') if i.strip().isdigit()]
        res['admin_user_ids'] = [(6, 0, admin_ids)]

        # Director stamp & signature (stored as ir.config_parameter base64 strings)
        res['director_signature'] = ICP.get_param('clinic_staff_portal.director_signature', '')
        res['director_stamp'] = ICP.get_param('clinic_staff_portal.director_stamp', '')
        res['director_name'] = ICP.get_param('clinic_staff_portal.director_name', '')
        res['director_title'] = ICP.get_param('clinic_staff_portal.director_title', 'Directeur')
        return res
    
    def set_values(self):
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        
        # DRH user
        drh_id = self.drh_user_id.id if self.drh_user_id else ''
        ICP.set_param('clinic_staff_portal.drh_user_id', str(drh_id) if drh_id else '')
        
        # Executive users
        exec_str = ','.join(str(u.id) for u in self.executive_user_ids)
        ICP.set_param('clinic_staff_portal.executive_user_ids', exec_str)
        
        # Admin users (portal full access)
        admin_str = ','.join(str(u.id) for u in self.admin_user_ids)
        ICP.set_param('clinic_staff_portal.admin_user_ids', admin_str)

        # Director stamp & signature
        ICP.set_param('clinic_staff_portal.director_signature', self.director_signature or '')
        ICP.set_param('clinic_staff_portal.director_stamp', self.director_stamp or '')
        ICP.set_param('clinic_staff_portal.director_name', self.director_name or '')
        ICP.set_param('clinic_staff_portal.director_title', self.director_title or 'Directeur')

    def action_sync_convention_products(self):
        """
        Create and fix CONV_* products for all convention pricelists.
        - Creates products for pricelists that don't have them yet
        - Sets invoice_policy='order' so discount lines are included in invoices
        """
        Product = self.env['product.product'].sudo()
        Pricelist = self.env['product.pricelist'].sudo()

        created_count = 0
        updated_count = 0

        # Get all pricelists with convention coverage set (excluding default ID 1)
        pricelists = Pricelist.search([
            ('id', '!=', 1),
            ('convention_coverage_pct', '>', 0),
        ])

        for pl in pricelists:
            product_code = f"CONV_{pl.id}"
            product_name = f"Convention {pl.name}"

            # Check if product exists
            existing = Product.search([('default_code', '=', product_code)], limit=1)

            if not existing:
                # Create the convention discount product
                Product.create({
                    'name': product_name,
                    'default_code': product_code,
                    'type': 'service',
                    'categ_id': self.env.ref('product.product_category_all').id,
                    'sale_ok': True,
                    'purchase_ok': False,
                    'list_price': 0,
                    'taxes_id': [(5, 0, 0)],
                    'invoice_policy': 'order',
                })
                created_count += 1
            else:
                # Fix invoice_policy and update name if needed
                tmpl = existing.product_tmpl_id
                updates = {}
                if tmpl.invoice_policy != 'order':
                    updates['invoice_policy'] = 'order'
                if tmpl.name != product_name:
                    updates['name'] = product_name
                if updates:
                    tmpl.write(updates)
                    updated_count += 1

        # Also fix any existing CONV_* products not covered above
        other_conv = Product.search([
            ('default_code', '=like', 'CONV_%'),
        ])
        for product in other_conv:
            tmpl = product.product_tmpl_id
            if tmpl.invoice_policy != 'order':
                tmpl.write({'invoice_policy': 'order'})
                updated_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Convention Products Synced',
                'message': f'{created_count} created, {updated_count} updated.',
                'sticky': False,
                'type': 'success',
            }
        }

    def action_sync_convention_partners(self):
        """
        Sync convention partners for all pricelists except the default (ID 1).
        Creates a partner for each pricelist and links it as payer_partner_id.
        """
        Pricelist = self.env['product.pricelist'].sudo()
        Partner = self.env['res.partner'].sudo()
        
        # Get all pricelists except ID 1 (default public pricelist)
        pricelists = Pricelist.search([('id', '!=', 1)])
        synced_count = 0
        
        for pl in pricelists:
            # Auto-detect discount from pricelist rules (percent_price field)
            discount_pct = 0
            if pl.item_ids:
                for item in pl.item_ids:
                    # percent_price is the discount field in Odoo 16
                    if hasattr(item, 'percent_price') and item.percent_price > discount_pct:
                        discount_pct = item.percent_price
            
            # Set convention_coverage_pct from detected discount
            if hasattr(pl, 'convention_coverage_pct') and discount_pct > 0:
                if not pl.convention_coverage_pct:
                    pl.convention_coverage_pct = discount_pct
            
            # Find or create partner for this pricelist
            partner_name = f"{pl.name} (Convention)"
            existing = Partner.search([('name', '=', partner_name)], limit=1)
            if existing:
                partner = existing
            else:
                partner = Partner.create({
                    'name': partner_name,
                    'is_company': True,
                    'company_type': 'company',
                    'comment': f"Auto-created for pricelist: {pl.name} ({discount_pct}%)",
                })
            
            # Always link (even if already linked to same partner)
            if pl.payer_partner_id.id != partner.id:
                pl.write({'payer_partner_id': partner.id})
                synced_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Convention Partners Synced',
                'message': f'{synced_count} convention partner(s) created/linked.',
                'sticky': False,
                'type': 'success',
            }
        }
