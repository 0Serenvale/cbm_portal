# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class StockDiscrepancyAlert(models.Model):
    """Log stock discrepancy incidents when consumption is blocked due to 0 stock"""
    _name = 'clinic.stock.discrepancy'
    _description = 'Stock Discrepancy Alert'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Reference',
        required=True,
        readonly=True,
        default=lambda self: _('New'))

    state = fields.Selection([
        ('pending', 'Pending Investigation'),
        ('nurse_error', 'Nurse Error'),
        ('inventory_issue', 'Inventory Issue'),
        ('resolved', 'Resolved'),
    ], string='Status', default='pending', tracking=True)

    # Who tried to consume
    user_id = fields.Many2one(
        'res.users',
        string='Nurse/User',
        required=True,
        default=lambda self: self.env.user,
        readonly=True)

    # Patient involved
    patient_id = fields.Many2one(
        'res.partner',
        string='Patient',
        required=False,
        readonly=True)

    # Department or partner involved (for non-patient consumption)
    department_id = fields.Many2one(
        'res.partner',
        string='Department/Partner',
        readonly=True)

    # Product details (optional - not set for duplicate submission alerts)
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=False,
        readonly=True)
    attempted_qty = fields.Float(
        string='Attempted Quantity',
        required=False,
        readonly=True)
    system_qty = fields.Float(
        string='System Stock',
        readonly=True,
        help='Stock level shown in system at time of attempt')

    # Related picking (for duplicate submission alerts)
    picking_id = fields.Many2one(
        'stock.picking',
        string='Related Transfer',
        readonly=True,
        help='The pending transfer that blocked the submission')

    # Additional notes for context
    notes = fields.Text(
        string='Notes',
        readonly=True,
        help='Additional context about the discrepancy')

    # Location
    location_id = fields.Many2one(
        'stock.location',
        string='Location',
        required=True,
        readonly=True)

    # Operation type for context
    picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Operation Type',
        readonly=True)

    # Resolution
    resolution_notes = fields.Text(
        string='Resolution Notes',
        help='Explain what was found during investigation')
    resolved_by = fields.Many2one(
        'res.users',
        string='Resolved By',
        readonly=True)
    resolved_date = fields.Datetime(
        string='Resolved Date',
        readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('clinic.stock.discrepancy') or _('New')
        records = super().create(vals_list)

        # Send notifications for each new discrepancy
        for record in records:
            try:
                record._send_notification()
            except Exception:
                # Don't block creation if notification fails
                # _logger is not available here unless imported, but we can ignore or print
                pass

        return records

    def _send_notification(self):
        """Send notification to responsible users via message_post (triggers ntfy)"""
        self.ensure_one()

        # Only Portal Administrators receive discrepancy notifications
        ICP = self.env['ir.config_parameter'].sudo()
        admin_ids_str = ICP.get_param('clinic_staff_portal.admin_user_ids', '')
        recipients = self.env['res.users']
        if admin_ids_str:
            admin_ids = [int(i) for i in admin_ids_str.split(',') if i.strip().isdigit()]
            recipients = self.env['res.users'].sudo().browse(admin_ids).filtered(lambda u: u.exists())

        if not recipients:
            return

        # Different notification format based on alert type
        if self.picking_id:
            # Duplicate submission / blocked transfer alert
            subject = _("🚫 Transfert bloqué | %(picking)s | Patient: %(patient)s | Par: %(user)s @ %(location)s") % {
                'picking': self.picking_id.name,
                'patient': self.patient_id.name if self.patient_id else 'N/A',
                'user': self.user_id.name,
                'location': self.location_id.name if self.location_id else 'N/A',
            }

            body = _("""
<div style="padding: 12px; background: #fff3cd; border-left: 4px solid #dc3545; border-radius: 4px;">
    <p><strong>🚫 Transfert Bloqué - %(ref)s</strong></p>
    <table style="margin-top: 10px;">
        <tr><td><strong>Transfert:</strong></td><td>%(picking)s</td></tr>
        <tr><td><strong>État:</strong></td><td>%(state)s</td></tr>
        <tr><td><strong>Emplacement:</strong></td><td>%(location)s</td></tr>
        <tr><td><strong>Utilisateur:</strong></td><td>%(user)s</td></tr>
        %(patient_row)s
        %(notes_row)s
    </table>
    <p style="margin-top: 10px; font-size: 12px; color: #666;">
        Veuillez vérifier et annuler ou valider ce transfert.
    </p>
</div>
""") % {
                'ref': self.name,
                'picking': self.picking_id.name,
                'state': dict(self.picking_id._fields['state'].selection).get(self.picking_id.state, self.picking_id.state),
                'location': self.location_id.complete_name if self.location_id else 'N/A',
                'user': self.user_id.name,
                'patient_row': "<tr><td><strong>Patient:</strong></td><td>%s</td></tr>" % self.patient_id.name if self.patient_id else "",
                'notes_row': "<tr><td><strong>Notes:</strong></td><td>%s</td></tr>" % self.notes if self.notes else "",
            }
        else:
            # Stock discrepancy alert (original)
            subject = _("🚨 Stock épuisé | %(product)s | Demandé: %(attempted)s, Dispo: %(available)s | Par: %(user)s @ %(location)s") % {
                'product': self.product_id.name if self.product_id else 'N/A',
                'attempted': self.attempted_qty,
                'available': self.system_qty,
                'user': self.user_id.name,
                'location': self.location_id.name if self.location_id else 'N/A',
            }

            body = _("""
<div style="padding: 12px; background: #fff3cd; border-left: 4px solid #dc3545; border-radius: 4px;">
    <p><strong>🚨 Alerte Discrépance Stock - %(ref)s</strong></p>
    <table style="margin-top: 10px;">
        <tr><td><strong>Produit:</strong></td><td>%(product)s</td></tr>
        <tr><td><strong>Emplacement:</strong></td><td>%(location)s</td></tr>
        <tr><td><strong>Utilisateur:</strong></td><td>%(user)s</td></tr>
        <tr><td><strong>Quantité demandée:</strong></td><td>%(attempted)s</td></tr>
        <tr><td><strong>Stock système:</strong></td><td style="color: #dc3545;">%(available)s</td></tr>
        %(patient_row)s
        %(op_type_row)s
    </table>
    <p style="margin-top: 10px; font-size: 12px; color: #666;">
        Vérifiez le stock physique et corrigez l'inventaire si nécessaire.
    </p>
</div>
""") % {
                'ref': self.name,
                'product': self.product_id.display_name if self.product_id else 'N/A',
                'location': self.location_id.complete_name if self.location_id else 'N/A',
                'user': self.user_id.name,
                'attempted': self.attempted_qty,
                'available': self.system_qty,
                'patient_row': "<tr><td><strong>Patient:</strong></td><td>%s</td></tr>" % self.patient_id.name if self.patient_id else "",
                'op_type_row': "<tr><td><strong>Opération:</strong></td><td>%s</td></tr>" % self.picking_type_id.name if self.picking_type_id else "",
            }

        # Post message with notification type to trigger ntfy
        # message_type='notification' is caught by cbm_ntfy module
        partner_ids = recipients.mapped('partner_id').ids
        self.message_post(
            body=body,
            subject=subject,
            message_type='notification',
            subtype_xmlid='mail.mt_note',
            partner_ids=partner_ids,
        )

    def action_mark_nurse_error(self):
        """Mark as nurse error - they made a mistake in product/location"""
        self.write({
            'state': 'nurse_error',
            'resolved_by': self.env.user.id,
            'resolved_date': fields.Datetime.now(),
        })
        self.message_post(body=_('Marked as nurse error by %s') % self.env.user.name)

    def action_mark_inventory_issue(self):
        """Mark as inventory issue - system stock was wrong"""
        self.write({
            'state': 'inventory_issue',
            'resolved_by': self.env.user.id,
            'resolved_date': fields.Datetime.now(),
        })
        self.message_post(body=_('Marked as inventory issue by %s') % self.env.user.name)

    def action_resolve(self):
        """Mark as resolved"""
        self.write({
            'state': 'resolved',
            'resolved_by': self.env.user.id,
            'resolved_date': fields.Datetime.now(),
        })
        self.message_post(body=_('Resolved by %s') % self.env.user.name)

    @api.model
    def get_pending_count(self):
        """Return count of pending alerts for dashboard"""
        return self.search_count([('state', '=', 'pending')])
