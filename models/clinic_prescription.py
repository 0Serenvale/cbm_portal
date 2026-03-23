# -*- coding: utf-8 -*-
"""
Clinic Prescription — Global prescription tracking from Bahmni/OpenMRS.

Stores drug prescriptions from providers (doctors). Location-agnostic —
the location only enters the picture when the nurse applies the prescription
via the CBM Portal kiosk.

Created automatically by the API feed intercept when a drug order comes in
with is_drug=True on the product.
"""

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ClinicPrescription(models.Model):
    _name = 'clinic.prescription'
    _description = 'Patient Prescription'
    _order = 'create_date desc, id desc'
    _rec_name = 'display_name'

    partner_id = fields.Many2one(
        'res.partner',
        string='Patient',
        required=True,
        index=True,
        ondelete='restrict',
    )
    visit_uuid = fields.Char(
        string='Visit UUID',
        index=True,
        help='OpenMRS visit UUID — links all prescriptions from the same visit',
    )
    encounter_uuid = fields.Char(
        string='Encounter UUID',
        index=True,
        help='OpenMRS encounter UUID',
    )
    provider_name = fields.Char(
        string='Provider',
        help='Prescribing doctor name from Bahmni',
    )
    state = fields.Selection([
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='State', default='active', index=True)

    line_ids = fields.One2many(
        'clinic.prescription.line',
        'prescription_id',
        string='Prescription Lines',
    )

    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('partner_id', 'provider_name', 'create_date')
    def _compute_display_name(self):
        for rec in self:
            patient = rec.partner_id.name or ''
            provider = rec.provider_name or ''
            rec.display_name = f"{patient} — {provider}"

    def init(self):
        """Create indexes for common query patterns."""
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS clinic_prescription_patient_state_idx
            ON clinic_prescription (partner_id, state)
            WHERE state = 'active';
        """)
        _logger.info("Clinic prescription indexes created/verified")


class ClinicPrescriptionLine(models.Model):
    _name = 'clinic.prescription.line'
    _description = 'Prescription Line'
    _order = 'provider_name, product_id'
    _rec_name = 'display_name'

    prescription_id = fields.Many2one(
        'clinic.prescription',
        string='Prescription',
        required=True,
        index=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Drug',
        required=True,
        index=True,
        ondelete='restrict',
    )
    qty_prescribed = fields.Float(
        string='Qty Prescribed',
        digits='Product Unit of Measure',
        required=True,
        help='Quantity prescribed by the doctor (source of truth)',
    )
    qty_applied = fields.Float(
        string='Qty Applied',
        digits='Product Unit of Measure',
        default=0.0,
        help='Quantity actually administered by the nurse',
    )
    provider_name = fields.Char(
        string='Provider',
        help='Prescribing doctor name',
    )
    external_order_id = fields.Char(
        string='Bahmni Order ID',
        index=True,
        help='OpenMRS order UUID — used for idempotency and revision matching',
    )
    state = fields.Selection([
        ('pending', 'Pending'),
        ('partial', 'Partially Applied'),
        ('done', 'Fully Applied'),
        ('cancelled', 'Cancelled'),
    ], string='State', default='pending', index=True)
    stop_reason = fields.Char(
        string='Stop Reason',
        help='Reason for cancellation/discontinuation from Bahmni',
    )

    # Audit
    partner_id = fields.Many2one(
        related='prescription_id.partner_id',
        store=True,
        index=True,
    )

    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('product_id', 'qty_prescribed', 'provider_name')
    def _compute_display_name(self):
        for rec in self:
            product = rec.product_id.name or ''
            rec.display_name = f"{product} x {rec.qty_prescribed} ({rec.provider_name or ''})"

    @api.constrains('qty_applied', 'qty_prescribed')
    def _check_qty_applied(self):
        for rec in self:
            if rec.qty_applied > rec.qty_prescribed:
                from odoo.exceptions import ValidationError
                raise ValidationError(
                    'Applied quantity (%.2f) cannot exceed prescribed quantity (%.2f) for %s.'
                    % (rec.qty_applied, rec.qty_prescribed, rec.product_id.name)
                )

    def mark_applied(self, qty):
        """Mark quantity as applied by the nurse."""
        self.ensure_one()
        new_applied = self.qty_applied + qty
        vals = {'qty_applied': min(new_applied, self.qty_prescribed)}

        if vals['qty_applied'] >= self.qty_prescribed:
            vals['state'] = 'done'
        elif vals['qty_applied'] > 0:
            vals['state'] = 'partial'

        self.write(vals)
        _logger.info(
            "Prescription line %s: applied %.2f (total: %.2f/%.2f)",
            self.id, qty, vals['qty_applied'], self.qty_prescribed
        )
