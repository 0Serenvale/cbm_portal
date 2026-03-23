# -*- coding: utf-8 -*-
import logging
import requests

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OpenmrsImportWizard(models.TransientModel):
    _name = 'openmrs.import.wizard'
    _description = 'Search and Import from OpenMRS'

    search_term = fields.Char(string='Search', required=True)
    target_model = fields.Selection([
        ('drug.dosage.form', 'Dosage Forms'),
        ('drug.openmrs.concept', 'Drug Concepts'),
    ], string='Import Into', required=True)

    result_ids = fields.One2many(
        'openmrs.import.wizard.line', 'wizard_id', string='Results'
    )

    def _get_openmrs_connection(self):
        get = self.env['ir.config_parameter'].sudo().get_param
        base_url = get('openmrs.base.url', 'http://openmrs:8080/openmrs')
        username = get('openmrs.username', 'admin')
        password = get('openmrs.password', 'Admin123')
        return base_url, username, password

    def action_search(self):
        """Search OpenMRS API and display results."""
        self.ensure_one()
        if len(self.search_term) < 2:
            raise UserError("Enter at least 2 characters.")

        base_url, username, password = self._get_openmrs_connection()

        # Build API query based on target
        params = {'q': self.search_term, 'v': 'default', 'limit': 30}
        if self.target_model == 'drug.openmrs.concept':
            params['class'] = 'Drug'

        try:
            resp = requests.get(
                f"{base_url}/ws/rest/v1/concept",
                params=params,
                auth=(username, password),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise UserError("Failed to connect to OpenMRS: %s" % str(e))

        results = data.get('results', [])
        if not results:
            raise UserError("No results found for '%s'" % self.search_term)

        # Clear previous results
        self.result_ids.unlink()

        # Check which UUIDs already exist locally
        target = self.env[self.target_model].sudo()
        existing_uuids = set(
            target.search([]).mapped('openmrs_uuid')
        )

        lines = []
        for concept in results:
            concept_uuid = concept.get('uuid', '')
            concept_name = concept.get('display', '').strip()
            if not concept_uuid or not concept_name:
                continue
            lines.append((0, 0, {
                'name': concept_name,
                'openmrs_uuid': concept_uuid,
                'already_imported': concept_uuid in existing_uuids,
                'selected': False,
            }))

        self.write({'result_ids': lines})

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'openmrs.import.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_import_selected(self):
        """Import selected results into the target model."""
        self.ensure_one()
        target = self.env[self.target_model].sudo()

        selected = self.result_ids.filtered(
            lambda l: l.selected and not l.already_imported
        )
        if not selected:
            raise UserError("No new items selected for import.")

        created = 0
        for line in selected:
            existing = target.search([('openmrs_uuid', '=', line.openmrs_uuid)], limit=1)
            if not existing:
                target.create({
                    'name': line.name,
                    'openmrs_uuid': line.openmrs_uuid,
                })
                created += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Import Complete',
                'message': '%d items imported.' % created,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class OpenmrsImportWizardLine(models.TransientModel):
    _name = 'openmrs.import.wizard.line'
    _description = 'OpenMRS Import Wizard Result Line'

    wizard_id = fields.Many2one('openmrs.import.wizard', ondelete='cascade')
    name = fields.Char(string='Name', readonly=True)
    openmrs_uuid = fields.Char(string='UUID', readonly=True)
    already_imported = fields.Boolean(string='Already Imported', readonly=True)
    selected = fields.Boolean(string='Select', default=False)
