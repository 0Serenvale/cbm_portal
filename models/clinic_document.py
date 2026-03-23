# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ClinicDocument(models.Model):
    _name = 'clinic.document'
    _description = 'Clinic Document'
    _order = 'category, name'

    name = fields.Char('Document Name', required=True, translate=True)
    category = fields.Selection([
        ('procedure', 'Procedure'),
        ('formation', 'Training'),
        ('guide', 'Guide'),
        ('policy', 'Policy'),
        ('other', 'Other'),
    ], string='Category', required=True, default='procedure')
    description = fields.Char('Description', translate=True)
    resource_type = fields.Selection([
        ('pdf', 'PDF'),
        ('video', 'Video'),
        ('link', 'Link'),
    ], string='Type', required=True, default='pdf')
    file_data = fields.Binary('File', attachment=True)
    file_name = fields.Char('File Name')
    url = fields.Char('URL', help='External URL for video or link types')
    location_ids = fields.Many2many(
        'stock.location',
        'clinic_document_location_rel',
        'document_id',
        'location_id',
        string='Locations',
        domain="[('usage', '=', 'internal')]",
        help='Leave empty for all locations'
    )
    active = fields.Boolean('Active', default=True)
    write_date = fields.Datetime('Last Updated', readonly=True)
    notify_users = fields.Boolean(
        'Notify Users',
        default=True,
        help='Send notification to users when this document is created'
    )
    requires_acknowledgement = fields.Boolean(
        'Requires Acknowledgement',
        default=False,
        help='Users must read and agree to this document. '
             'Their acknowledgement is logged.'
    )
    target_user_ids = fields.Many2many(
        'res.users',
        'clinic_document_target_user_rel',
        'document_id',
        'user_id',
        string='Target Users',
        help='Specific users who must see this document. '
             'Leave empty to use location-based or global visibility.'
    )
    acknowledgement_ids = fields.One2many(
        'clinic.document.acknowledgement',
        'document_id',
        string='Acknowledgements'
    )

    # --- Versioning ---
    version = fields.Integer(
        'Version', default=1, readonly=True,
        help='Auto-incremented when document content changes. '
             'Previous acknowledgements are invalidated on version change.'
    )

    # --- Deadline & Compliance ---
    deadline = fields.Date(
        'Acknowledgement Deadline',
        help='Users must acknowledge before this date. '
             'After deadline, non-compliant users get kiosk access blocked.'
    )
    lock_on_overdue = fields.Boolean(
        'Lock Kiosk on Overdue', default=True,
        help='Block all kiosk operations for users who miss the deadline. '
             'Access restores automatically once they sign.'
    )

    # --- Stamp & Signature (optional, shown in kiosk PDF viewer) ---
    stamp_image = fields.Binary(
        'Stamp', attachment=True,
        help='Official stamp image (PNG with transparent background recommended). '
             'Shown alongside the document in the kiosk viewer.')
    signature_image = fields.Binary(
        'Signature', attachment=True,
        help='Authorized signature image (PNG with transparent background recommended). '
             'Shown alongside the document in the kiosk viewer.')
    signatory_name = fields.Char(
        'Signatory Name',
        help='Name of the person who signed/stamped (e.g. Director, DRH).'
    )
    signatory_title = fields.Char(
        'Signatory Title',
        help='Title/function of the signatory (e.g. Directeur Général, DRH).'
    )

    # --- Computed: Compliance stats ---
    pending_count = fields.Integer(
        'Pending', compute='_compute_compliance_stats', store=False)
    acknowledged_count = fields.Integer(
        'Acknowledged', compute='_compute_compliance_stats', store=False)
    overdue_count = fields.Integer(
        'Overdue', compute='_compute_compliance_stats', store=False)

    @api.depends('acknowledgement_ids', 'target_user_ids', 'location_ids', 'deadline', 'version')
    def _compute_compliance_stats(self):
        for doc in self:
            if not doc.requires_acknowledgement:
                doc.pending_count = 0
                doc.acknowledged_count = 0
                doc.overdue_count = 0
                continue
            target_users = doc._get_target_users()
            current_acks = doc.acknowledgement_ids.filtered(
                lambda a: a.document_version == doc.version
            )
            acked_user_ids = set(current_acks.mapped('user_id').ids)
            doc.acknowledged_count = len(acked_user_ids)
            doc.pending_count = len(target_users) - len(acked_user_ids)
            if doc.deadline and fields.Date.today() > doc.deadline:
                doc.overdue_count = doc.pending_count
            else:
                doc.overdue_count = 0

    @api.onchange('resource_type')
    def _onchange_resource_type(self):
        if self.resource_type == 'pdf':
            self.url = False
        else:
            self.file_data = False
            self.file_name = False

    def get_document_url(self):
        """Return the URL to access this document"""
        self.ensure_one()
        if self.resource_type == 'pdf' and self.file_data:
            return f'/web/content/clinic.document/{self.id}/file_data/{self.file_name}'
        return self.url or ''

    def write(self, vals):
        """Auto-increment version when content is REPLACED (not first upload)"""
        content_fields = {'file_data', 'url'}
        if content_fields & set(vals.keys()):
            for record in self:
                # Only bump version if file/url already existed (replacement)
                has_existing = record.file_data or record.url
                if has_existing:
                    vals['version'] = record.version + 1
        res = super().write(vals)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.notify_users and record.active:
                record._send_notification()
        return records

    def _get_target_users(self):
        """Get users to notify based on document target users / locations"""
        self.ensure_one()
        User = self.env['res.users'].sudo()

        if self.target_user_ids:
            users = self.target_user_ids.filtered(lambda u: u.active and not u.share)
            _logger.info("[clinic.document] Found %d targeted users", len(users))
        elif self.location_ids:
            _logger.info("[clinic.document] Finding users for locations: %s", self.location_ids.ids)
            doc_loc_ids = set(self.location_ids.ids)
            all_users = User.search([
                ('active', '=', True),
                ('share', '=', False),
            ])
            users = all_users.filtered(
                lambda u: hasattr(u, 'allowed_location_ids')
                and u.allowed_location_ids
                and bool(set(u.allowed_location_ids.ids) & doc_loc_ids)
            )
            _logger.info("[clinic.document] Found %d users for location-based document", len(users))
        else:
            portal_group = self.env.ref(
                'clinic_staff_portal.group_clinic_portal_user',
                raise_if_not_found=False
            )
            if portal_group:
                users = portal_group.users.filtered(lambda u: u.active and not u.share)
            else:
                _logger.warning("[clinic.document] Portal group not found!")
                users = User.browse()

        return users

    def _send_notification(self):
        """Send internal mail notification to target users"""
        self.ensure_one()
        _logger.info("[clinic.document] _send_notification called for document: %s (id=%s)", self.name, self.id)
        users = self._get_target_users()
        if not users:
            _logger.warning("[clinic.document] No users found to notify for document: %s", self.name)
            return
        _logger.info("[clinic.document] Will notify %d users for document: %s", len(users), self.name)

        category_labels = dict(self._fields['category'].selection)
        category_label = category_labels.get(self.category, self.category)

        subject = f"Nouveau Document : {self.name}"
        body = f"""
        <p>Un nouveau document a été ajouté au portail CBM :</p>
        <ul>
            <li><strong>Nom :</strong> {self.name}</li>
            <li><strong>Catégorie :</strong> {category_label}</li>
            <li><strong>Type :</strong> {self.resource_type.upper()}</li>
        </ul>
        <p>Consultez-le depuis la tuile <strong>Documents</strong> du portail CBM.</p>
        """

        if self.description:
            body = body.replace('</ul>', f'<li><strong>Description :</strong> {self.description}</li></ul>')

        for user in users:
            self.env['mail.message'].sudo().create({
                'subject': subject,
                'body': body,
                'message_type': 'notification',
                'model': 'res.partner',
                'res_id': user.partner_id.id,
                'partner_ids': [(4, user.partner_id.id)],
                'author_id': self.env.user.partner_id.id,
            })

    @api.model
    def _cron_check_compliance_deadlines(self):
        """Cron job: send reminder/escalation for overdue documents to DRH"""
        ICP = self.env['ir.config_parameter'].sudo()
        drh_id_str = ICP.get_param('clinic_staff_portal.drh_user_id', '')
        if not drh_id_str or not drh_id_str.isdigit():
            _logger.info("[clinic.document] No DRH configured, skipping compliance check")
            return

        drh_user = self.env['res.users'].sudo().browse(int(drh_id_str))
        if not drh_user.exists() or not drh_user.partner_id.email:
            _logger.warning("[clinic.document] DRH user not found or has no email")
            return

        today = fields.Date.today()
        overdue_docs = self.sudo().search([
            ('active', '=', True),
            ('requires_acknowledgement', '=', True),
            ('deadline', '<', today),
        ])

        if not overdue_docs:
            return

        # Build compliance summary
        overdue_lines = []
        for doc in overdue_docs:
            target_users = doc._get_target_users()
            current_acks = doc.acknowledgement_ids.filtered(
                lambda a: a.document_version == doc.version
            )
            acked_user_ids = set(current_acks.mapped('user_id').ids)
            pending_users = target_users.filtered(lambda u: u.id not in acked_user_ids)
            if pending_users:
                days_overdue = (today - doc.deadline).days
                overdue_lines.append({
                    'doc_name': doc.name,
                    'doc_category': dict(doc._fields['category'].selection).get(doc.category, doc.category),
                    'deadline': doc.deadline.strftime('%d/%m/%Y'),
                    'days_overdue': days_overdue,
                    'pending_users': ', '.join(pending_users.mapped('name')),
                    'pending_count': len(pending_users),
                })

        if not overdue_lines:
            return

        # Build HTML table for the email
        rows_html = ''
        for line in overdue_lines:
            rows_html += f"""
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{line['doc_name']}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{line['doc_category']}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{line['deadline']}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; color: #dc3545; font-weight: 600;">
                    {line['days_overdue']} jour(s)
                </td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{line['pending_count']} utilisateur(s)</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; font-size: 12px;">{line['pending_users']}</td>
            </tr>
            """

        body = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 750px; margin: 0 auto; color: #333;">
            <div style="background: linear-gradient(135deg, #1e3a5f, #2d5a87); padding: 25px 30px; border-radius: 8px 8px 0 0;">
                <h2 style="color: white; margin: 0;">Rapport de Conformit&eacute; Documentaire</h2>
                <p style="color: rgba(255,255,255,0.8); margin: 5px 0 0 0; font-size: 13px;">
                    Documents en retard d'acquittement
                </p>
            </div>
            <div style="background: #fff; padding: 30px; border: 1px solid #e0e0e0;">
                <p>Madame, Monsieur,</p>
                <p>Les documents suivants ont d&eacute;pass&eacute; leur date limite d'acquittement :</p>
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <thead>
                        <tr style="background: #f5f5f5;">
                            <th style="padding: 10px 8px; text-align: left;">Document</th>
                            <th style="padding: 10px 8px; text-align: left;">Cat&eacute;gorie</th>
                            <th style="padding: 10px 8px; text-align: left;">Date limite</th>
                            <th style="padding: 10px 8px; text-align: left;">Retard</th>
                            <th style="padding: 10px 8px; text-align: left;">En attente</th>
                            <th style="padding: 10px 8px; text-align: left;">Utilisateurs</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
                <p>Merci de prendre les mesures n&eacute;cessaires.</p>
                <p>Cordialement,<br/><strong>CBM Portal</strong></p>
            </div>
            <div style="background: #f5f5f5; padding: 15px 30px; border-radius: 0 0 8px 8px; border: 1px solid #e0e0e0; border-top: none;">
                <p style="margin: 0; font-size: 11px; color: #888; text-align: center;">
                    G&eacute;n&eacute;r&eacute; automatiquement par CBM Portal &bull; {today.strftime('%d/%m/%Y')}
                </p>
            </div>
        </div>
        """

        self.env['mail.message'].sudo().create({
            'subject': f'[CBM Portal] Rapport conformit\u00e9 documentaire - {len(overdue_lines)} document(s) en retard',
            'body': body,
            'message_type': 'notification',
            'model': 'res.partner',
            'res_id': drh_user.partner_id.id,
            'partner_ids': [(4, drh_user.partner_id.id)],
            'author_id': self.env.user.partner_id.id,
        })
        _logger.info(
            "[clinic.document] Sent compliance report to DRH for %d overdue documents",
            len(overdue_lines)
        )
