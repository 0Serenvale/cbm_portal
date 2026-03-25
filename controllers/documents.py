# -*- coding: utf-8 -*-
from odoo import http, _, fields as odoo_fields
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class CBMDocumentsController(http.Controller):

    @http.route('/cbm/documents/list', type='json', auth='user')
    def get_documents(self):
        """Get documents filtered by user's allowed locations and target users"""
        user = request.env.user
        Document = request.env['clinic.document'].sudo()
        Ack = request.env['clinic.document.acknowledgement'].sudo()

        # Check if user is a Portal Administrator (CBM setting, not Odoo group)
        ICP = request.env['ir.config_parameter'].sudo()
        admin_ids_str = ICP.get_param('clinic_staff_portal.admin_user_ids', '')
        admin_ids = [int(i) for i in admin_ids_str.split(',') if i.strip().isdigit()]
        is_admin = user.id in admin_ids

        # Get user's allowed locations (aligned with tile visibility logic)
        user_location_ids = []
        if hasattr(user, 'allowed_location_ids') and user.allowed_location_ids:
            user_location_ids = user.allowed_location_ids.ids

        if is_admin:
            documents = Document.search([('active', '=', True)])
        elif not user_location_ids:
            documents = Document.search([
                ('active', '=', True),
                '|',
                ('target_user_ids', '=', False),
                ('target_user_ids', 'in', [user.id]),
            ])
        else:
            documents = Document.search([
                ('active', '=', True),
                '|',
                ('target_user_ids', 'in', [user.id]),
                '&',
                ('target_user_ids', '=', False),
                '|',
                ('location_ids', '=', False),
                ('location_ids', 'in', user_location_ids),
            ])

        # Pre-fetch user's acknowledgements for these documents
        # Only count acks matching the current document version
        user_acks = Ack.search([
            ('user_id', '=', user.id),
            ('document_id', 'in', documents.ids),
        ])
        # Build a dict: {doc_id: set of acked versions}
        acked_versions = {}
        for ack in user_acks:
            acked_versions.setdefault(ack.document_id.id, set()).add(ack.document_version)

        # Group by category
        category_labels = dict(Document._fields['category'].selection)
        result = {}

        for doc in documents:
            cat_key = doc.category
            if cat_key not in result:
                result[cat_key] = {
                    'label': category_labels.get(cat_key, cat_key),
                    'documents': []
                }

            # Check if user has acknowledged the CURRENT version
            doc_acked_versions = acked_versions.get(doc.id, set())
            is_current_version_acked = doc.version in doc_acked_versions

            # Check if this user is an actual target (for auto-open logic)
            # True if: no target users set (all users) OR user is explicitly listed
            is_targeted = not doc.target_user_ids or user.id in doc.target_user_ids.ids

            result[cat_key]['documents'].append({
                'id': doc.id,
                'name': doc.name,
                'description': doc.description or '',
                'resource_type': doc.resource_type,
                'url': doc.get_document_url(),
                'file_name': doc.file_name or '',
                'locations': [{'id': l.id, 'name': l.name} for l in doc.location_ids] if doc.location_ids else [],
                'write_date': doc.write_date.strftime('%d/%m/%Y') if doc.write_date else '',
                'requires_acknowledgement': doc.requires_acknowledgement,
                'is_acknowledged': is_current_version_acked,
                'is_targeted': is_targeted,
                'version': doc.version,
                'deadline': doc.deadline.strftime('%d/%m/%Y') if doc.deadline else '',
                'has_stamp': bool(doc.stamp_image),
                'stamp_url': '/web/image/clinic.document/%d/stamp_image' % doc.id if doc.stamp_image else '',
                'has_signature': bool(doc.signature_image),
                'signature_url': '/web/image/clinic.document/%d/signature_image' % doc.id if doc.signature_image else '',
                'signatory_name': doc.signatory_name or '',
                'signatory_title': doc.signatory_title or '',
            })

        # Convert to list sorted by category order
        category_order = ['procedure', 'formation', 'guide', 'policy', 'other']
        sorted_result = []
        for cat in category_order:
            if cat in result:
                sorted_result.append({
                    'key': cat,
                    'label': result[cat]['label'],
                    'documents': result[cat]['documents']
                })

        return {
            'categories': sorted_result,
            'is_admin': is_admin,
            'total_count': len(documents),
        }

    @http.route('/cbm/documents/acknowledge', type='json', auth='user')
    def acknowledge_document(self, document_id, typed_name='', user_agent=''):
        """Record that the current user has read and agreed to a document.
        Requires typed_name matching the user's display name.
        """
        user = request.env.user
        Ack = request.env['clinic.document.acknowledgement'].sudo()
        Document = request.env['clinic.document'].sudo()

        doc = Document.browse(document_id)
        if not doc.exists() or not doc.active:
            return {'success': False, 'error': 'Document not found'}

        if not doc.requires_acknowledgement:
            return {'success': False, 'error': 'Document does not require acknowledgement'}

        # Validate typed name matches user's display name (case-insensitive)
        if not typed_name or typed_name.strip().lower() != user.name.strip().lower():
            return {
                'success': False,
                'error': 'Le nom saisi ne correspond pas à votre nom.',
                'expected_name': user.name,
            }

        # Check if already acknowledged for this version
        existing = Ack.search([
            ('document_id', '=', document_id),
            ('user_id', '=', user.id),
            ('document_version', '=', doc.version),
        ], limit=1)

        if existing:
            return {'success': True, 'already': True, 'ack_id': existing.id}

        # Get IP address from request
        ip_address = request.httprequest.environ.get(
            'HTTP_X_FORWARDED_FOR',
            request.httprequest.environ.get('REMOTE_ADDR', '')
        )
        # Take first IP if comma-separated (proxy chain)
        if ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()

        new_ack = Ack.create({
            'document_id': document_id,
            'user_id': user.id,
            'document_version': doc.version,
            'typed_name': typed_name.strip(),
            'ip_address': ip_address,
            'user_agent': (user_agent or '')[:500],
        })

        return {'success': True, 'already': False, 'ack_id': new_ack.id}

    @http.route('/cbm/session/config', type='json', auth='user')
    def get_session_config(self):
        """Return session config for global JS services (pending acks, compliance lock)"""
        user = request.env.user

        # Check for pending acknowledgement documents (current version only)
        has_pending_ack = False
        is_compliance_locked = False
        Document = request.env['clinic.document'].sudo()
        Ack = request.env['clinic.document.acknowledgement'].sudo()

        ack_docs = Document.search([
            ('active', '=', True),
            ('requires_acknowledgement', '=', True),
            ('resource_type', '=', 'pdf'),
            '|',
            ('target_user_ids', '=', False),
            ('target_user_ids', 'in', [user.id]),
        ])

        if ack_docs:
            # Get all user's acks for these documents
            user_acks = Ack.search([
                ('user_id', '=', user.id),
                ('document_id', 'in', ack_docs.ids),
            ])
            acked_doc_versions = {}
            for ack in user_acks:
                acked_doc_versions.setdefault(ack.document_id.id, set()).add(ack.document_version)

            today = odoo_fields.Date.today()
            for doc in ack_docs:
                doc_acked = acked_doc_versions.get(doc.id, set())
                if doc.version not in doc_acked:
                    has_pending_ack = True
                    # Check if this doc is overdue and lock_on_overdue is enabled
                    if doc.lock_on_overdue and doc.deadline and today > doc.deadline:
                        is_compliance_locked = True
                        break

        return {
            'has_pending_acknowledgements': has_pending_ack,
            'is_compliance_locked': is_compliance_locked,
            'user_display_name': user.name,
        }

    @http.route('/cbm/documents/compliance_report', type='json', auth='user')
    def get_compliance_report(self):
        """Return compliance data for all acknowledgement-required documents.
        Used by the compliance dashboard in the kiosk/tile manager.
        """
        user = request.env.user
        is_admin = user.has_group('stock.group_stock_manager')
        is_manager = user.has_group('clinic_staff_portal.group_clinic_portal_manager')

        if not is_admin and not is_manager:
            return {'error': 'Access denied', 'documents': []}

        Document = request.env['clinic.document'].sudo()
        Ack = request.env['clinic.document.acknowledgement'].sudo()

        docs = Document.search([
            ('active', '=', True),
            ('requires_acknowledgement', '=', True),
        ])

        today = odoo_fields.Date.today()
        report = []

        for doc in docs:
            target_users = doc._get_target_users()
            current_acks = Ack.search([
                ('document_id', '=', doc.id),
                ('document_version', '=', doc.version),
            ])
            acked_user_ids = set(current_acks.mapped('user_id').ids)

            users_data = []
            for u in target_users:
                ack = current_acks.filtered(lambda a: a.user_id.id == u.id)
                status = 'acknowledged'
                if u.id not in acked_user_ids:
                    if doc.deadline and today > doc.deadline:
                        status = 'overdue'
                    else:
                        status = 'pending'
                users_data.append({
                    'user_id': u.id,
                    'user_name': u.name,
                    'status': status,
                    'acknowledged_date': ack[0].acknowledged_date.strftime('%d/%m/%Y %H:%M') if ack else '',
                    'typed_name': ack[0].typed_name if ack else '',
                    'ip_address': ack[0].ip_address if ack else '',
                })

            report.append({
                'id': doc.id,
                'name': doc.name,
                'category': doc.category,
                'version': doc.version,
                'deadline': doc.deadline.strftime('%d/%m/%Y') if doc.deadline else '',
                'total_users': len(target_users),
                'acknowledged_count': len(acked_user_ids),
                'pending_count': len(target_users) - len(acked_user_ids),
                'overdue': bool(doc.deadline and today > doc.deadline),
                'users': users_data,
            })

        return {'documents': report}

    @http.route('/cbm/documents/ack_receipt/<int:ack_id>', type='http', auth='user')
    def get_ack_receipt_pdf(self, ack_id, **kwargs):
        """Génère et retourne le PDF du reçu d'accusé de réception.

        Seul l'utilisateur qui a signé peut télécharger son propre reçu.
        """
        try:
            user = request.env.user
            Ack = request.env['clinic.document.acknowledgement'].sudo()
            ack = Ack.browse(ack_id)

            if not ack.exists():
                return request.make_response(
                    "Accusé de réception introuvable.",
                    headers=[('Content-Type', 'text/plain; charset=utf-8')]
                )

            if ack.user_id.id != user.id:
                return request.make_response(
                    "Accès refusé.",
                    headers=[('Content-Type', 'text/plain; charset=utf-8')],
                    status=403
                )

            report = request.env.ref(
                'clinic_staff_portal.action_report_document_ack_receipt'
            ).sudo()
            pdf_content, _ = report._render_qweb_pdf(
                report.report_name, [ack_id]
            )

            doc_name = (ack.document_id.name or str(ack_id)).replace('/', '_').replace(' ', '_')
            filename = 'Recu_Signature_%s.pdf' % doc_name
            return request.make_response(
                pdf_content,
                headers=[
                    ('Content-Type', 'application/pdf'),
                    ('Content-Disposition', 'attachment; filename="%s"' % filename),
                    ('Content-Length', len(pdf_content)),
                ]
            )

        except Exception as e:
            _logger.error("CBM Documents: Erreur génération reçu ack %s: %s",
                          ack_id, str(e), exc_info=True)
            return request.make_response(
                "Erreur lors de la génération du PDF.",
                headers=[('Content-Type', 'text/plain; charset=utf-8')]
            )
