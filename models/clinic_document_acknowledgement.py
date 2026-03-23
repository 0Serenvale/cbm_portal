# -*- coding: utf-8 -*-
from odoo import fields, models


class ClinicDocumentAcknowledgement(models.Model):
    _name = 'clinic.document.acknowledgement'
    _description = 'Document Acknowledgement'
    _order = 'acknowledged_date desc'

    document_id = fields.Many2one(
        'clinic.document', string='Document',
        required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one(
        'res.users', string='User',
        required=True, ondelete='cascade', index=True)
    acknowledged_date = fields.Datetime(
        'Acknowledged On', required=True,
        default=fields.Datetime.now)

    # --- Versioning ---
    document_version = fields.Integer(
        'Document Version', required=True, default=1,
        help='Version of the document at the time of acknowledgement.')

    # --- Non-repudiation ---
    typed_name = fields.Char(
        'Typed Confirmation',
        help='User typed their full name to confirm acknowledgement.')
    ip_address = fields.Char(
        'IP Address',
        help='IP address of the user at the time of acknowledgement.')
    user_agent = fields.Char(
        'User Agent',
        help='Browser user agent string at the time of acknowledgement.')

    _sql_constraints = [
        ('unique_user_document_version', 'unique(document_id, user_id, document_version)',
         'A user can only acknowledge a specific document version once.'),
    ]
