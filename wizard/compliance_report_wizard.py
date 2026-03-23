# -*- coding: utf-8 -*-
import base64
import io
import logging
from datetime import datetime

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
    _logger.warning("reportlab not installed. Compliance PDF export will not work.")


class ComplianceReportWizard(models.TransientModel):
    _name = 'compliance.report.wizard'
    _description = 'Document Compliance Report Export'

    document_ids = fields.Many2many(
        'clinic.document',
        string='Documents',
        domain="[('requires_acknowledgement', '=', True), ('active', '=', True)]",
        help='Leave empty to include all documents requiring acknowledgement.'
    )
    include_stamp = fields.Boolean('Include Director Stamp', default=True)
    include_signature = fields.Boolean('Include Director Signature', default=True)
    report_file = fields.Binary('Report', readonly=True)
    report_filename = fields.Char('Filename', readonly=True)
    state = fields.Selection([
        ('config', 'Configuration'),
        ('done', 'Done'),
    ], default='config')

    def action_generate_report(self):
        """Generate PDF compliance report with stamp and signature."""
        self.ensure_one()

        if not HAS_REPORTLAB:
            raise models.ValidationError(
                _("reportlab library is not installed. Cannot generate PDF report.")
            )

        ICP = self.env['ir.config_parameter'].sudo()
        Document = self.env['clinic.document'].sudo()
        Ack = self.env['clinic.document.acknowledgement'].sudo()

        # Get documents
        if self.document_ids:
            docs = self.document_ids
        else:
            docs = Document.search([
                ('active', '=', True),
                ('requires_acknowledgement', '=', True),
            ])

        if not docs:
            raise models.ValidationError(_("No documents found for the report."))

        # Build PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=2 * cm, rightMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2.5 * cm,
        )

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            'ReportTitle', parent=styles['Title'],
            fontSize=16, spaceAfter=6, alignment=TA_CENTER,
        ))
        styles.add(ParagraphStyle(
            'ReportSubtitle', parent=styles['Normal'],
            fontSize=10, textColor=colors.grey, alignment=TA_CENTER,
            spaceAfter=20,
        ))
        styles.add(ParagraphStyle(
            'SectionHeader', parent=styles['Heading2'],
            fontSize=12, spaceBefore=16, spaceAfter=8,
            textColor=colors.HexColor('#1e3a5f'),
        ))
        styles.add(ParagraphStyle(
            'SignatureName', parent=styles['Normal'],
            fontSize=11, fontName='Helvetica-Bold', alignment=TA_RIGHT,
        ))
        styles.add(ParagraphStyle(
            'SignatureTitle', parent=styles['Normal'],
            fontSize=9, textColor=colors.grey, alignment=TA_RIGHT,
        ))
        styles.add(ParagraphStyle(
            'CellText', parent=styles['Normal'],
            fontSize=8, leading=10,
        ))

        elements = []

        # Title
        elements.append(Paragraph("Rapport de Conformit\u00e9 Documentaire", styles['ReportTitle']))
        today = datetime.now().strftime('%d/%m/%Y %H:%M')
        elements.append(Paragraph(f"G\u00e9n\u00e9r\u00e9 le {today}", styles['ReportSubtitle']))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e0e0e0')))
        elements.append(Spacer(1, 12))

        today_date = fields.Date.today()

        for document in docs:
            # Section header
            category_labels = dict(Document._fields['category'].selection)
            cat_label = category_labels.get(document.category, document.category)
            elements.append(Paragraph(
                f"{document.name} <font size='8' color='grey'>(v{document.version} - {cat_label})</font>",
                styles['SectionHeader']
            ))

            if document.deadline:
                deadline_str = document.deadline.strftime('%d/%m/%Y')
                overdue = today_date > document.deadline
                color = '#dc3545' if overdue else '#333'
                status = ' - EN RETARD' if overdue else ''
                elements.append(Paragraph(
                    f"<font color='{color}'>Date limite: {deadline_str}{status}</font>",
                    styles['CellText']
                ))
                elements.append(Spacer(1, 4))

            # Get target users and acks
            target_users = document._get_target_users()
            current_acks = Ack.search([
                ('document_id', '=', document.id),
                ('document_version', '=', document.version),
            ])
            acked_map = {a.user_id.id: a for a in current_acks}

            # Table data
            table_data = [['Utilisateur', 'Statut', 'Date', 'Confirmation', 'IP']]

            for user in target_users.sorted(key=lambda u: u.name):
                ack = acked_map.get(user.id)
                if ack:
                    status = 'Sign\u00e9'
                    date_str = ack.acknowledged_date.strftime('%d/%m/%Y %H:%M')
                    typed = ack.typed_name or ''
                    ip = ack.ip_address or ''
                else:
                    is_overdue = document.deadline and today_date > document.deadline
                    status = 'EN RETARD' if is_overdue else 'En attente'
                    date_str = ''
                    typed = ''
                    ip = ''

                table_data.append([
                    Paragraph(user.name, styles['CellText']),
                    Paragraph(status, styles['CellText']),
                    Paragraph(date_str, styles['CellText']),
                    Paragraph(typed, styles['CellText']),
                    Paragraph(ip, styles['CellText']),
                ])

            if len(table_data) > 1:
                col_widths = [5.5 * cm, 2.5 * cm, 3.5 * cm, 3 * cm, 2.5 * cm]
                table = Table(table_data, colWidths=col_widths, repeatRows=1)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 8),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('LEFTPADDING', (0, 0), (-1, -1), 4),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ]))
                elements.append(table)
            else:
                elements.append(Paragraph("Aucun utilisateur cibl\u00e9.", styles['CellText']))

            elements.append(Spacer(1, 16))

        # --- Signature & Stamp Section ---
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e0e0e0')))
        elements.append(Spacer(1, 24))

        director_name = ICP.get_param('clinic_staff_portal.director_name', '')
        director_title = ICP.get_param('clinic_staff_portal.director_title', 'Directeur')
        director_signature_b64 = ICP.get_param('clinic_staff_portal.director_signature', '')
        director_stamp_b64 = ICP.get_param('clinic_staff_portal.director_stamp', '')

        sig_elements = []

        if self.include_signature and director_signature_b64:
            try:
                sig_data = base64.b64decode(director_signature_b64)
                sig_img = Image(io.BytesIO(sig_data), width=5 * cm, height=2.5 * cm)
                sig_img.hAlign = 'RIGHT'
                sig_elements.append(sig_img)
            except Exception:
                _logger.warning("Failed to decode director signature image")

        if self.include_stamp and director_stamp_b64:
            try:
                stamp_data = base64.b64decode(director_stamp_b64)
                stamp_img = Image(io.BytesIO(stamp_data), width=4 * cm, height=4 * cm)
                stamp_img.hAlign = 'RIGHT'
                sig_elements.append(stamp_img)
            except Exception:
                _logger.warning("Failed to decode director stamp image")

        if director_name:
            sig_elements.append(Paragraph(director_name, styles['SignatureName']))
        if director_title:
            sig_elements.append(Paragraph(director_title, styles['SignatureTitle']))

        if sig_elements:
            # Right-align the signature block
            sig_table = Table([[sig_elements]], colWidths=[17 * cm])
            sig_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ]))
            elements.append(sig_table)

        # Build PDF
        doc.build(elements)
        pdf_data = buffer.getvalue()
        buffer.close()

        filename = f"compliance_report_{fields.Date.today().strftime('%Y%m%d')}.pdf"
        self.write({
            'report_file': base64.b64encode(pdf_data),
            'report_filename': filename,
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'compliance.report.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
