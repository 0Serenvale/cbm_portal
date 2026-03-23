# -*- coding: utf-8 -*-
import logging
import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DrugOpenmrsConcept(models.Model):
    _name = 'drug.openmrs.concept'
    _description = 'OpenMRS Drug Concept (local cache)'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True, index=True)
    openmrs_id = fields.Integer(string='OpenMRS ID', index=True)
    openmrs_uuid = fields.Char(string='OpenMRS UUID', required=True, index=True)

    _sql_constraints = [
        ('uuid_unique', 'UNIQUE(openmrs_uuid)', 'Concept UUID must be unique.'),
    ]

    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        """Override to search OpenMRS API when local results are insufficient."""
        args = args or []
        if name and len(name) >= 2:
            # Search and cache from API if needed
            try:
                self.sudo().search_and_cache(name)
            except Exception as e:
                _logger.warning("API search for concept '%s' failed: %s", name, e)
        return super()._name_search(
            name=name, args=args, operator=operator,
            limit=limit, name_get_uid=name_get_uid,
        )

    @api.model
    def action_import_from_openmrs(self):
        """Fetch drug concepts from OpenMRS and store locally.

        Uses conceptClass=Drug filter. Paginates through all results.
        """
        get = self.env['ir.config_parameter'].sudo().get_param
        base_url = get('openmrs.base.url', 'http://openmrs:8080/openmrs')
        username = get('openmrs.username', 'admin')
        password = get('openmrs.password', 'Admin123')

        created = 0
        updated = 0
        start_index = 0
        page_size = 100

        while True:
            url = f"{base_url}/ws/rest/v1/concept"
            try:
                resp = requests.get(
                    url,
                    params={
                        'class': 'Drug',
                        'v': 'default',
                        'limit': page_size,
                        'startIndex': start_index,
                    },
                    auth=(username, password),
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                raise UserError("Failed to connect to OpenMRS: %s" % str(e))

            results = data.get('results', [])
            if not results:
                break

            for concept in results:
                concept_uuid = concept.get('uuid')
                concept_name = concept.get('display', '').strip()
                if not concept_uuid or not concept_name:
                    continue

                existing = self.search([('openmrs_uuid', '=', concept_uuid)], limit=1)
                if existing:
                    existing.write({'name': concept_name})
                    updated += 1
                else:
                    self.create({
                        'name': concept_name,
                        'openmrs_uuid': concept_uuid,
                    })
                    created += 1

            # Check for next page
            has_next = False
            for link in data.get('links', []):
                if link.get('rel') == 'next':
                    has_next = True
                    break
            if not has_next:
                break
            start_index += page_size

        _logger.info(
            "Drug concept import: %d created, %d updated", created, updated
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Drug Concepts Imported',
                'message': '%d created, %d updated.' % (created, updated),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def search_and_cache(self, search_term):
        """Search local cache first. If < 3 results, also query OpenMRS API
        and cache any new results. Returns recordset of matches."""
        local = self.search([('name', 'ilike', search_term)], limit=20)

        if len(local) >= 3:
            return local

        # Hit API for more results
        get = self.env['ir.config_parameter'].sudo().get_param
        base_url = get('openmrs.base.url', 'http://openmrs:8080/openmrs')
        username = get('openmrs.username', 'admin')
        password = get('openmrs.password', 'Admin123')

        try:
            resp = requests.get(
                f"{base_url}/ws/rest/v1/concept",
                params={'q': search_term, 'class': 'Drug', 'v': 'default', 'limit': 20},
                auth=(username, password),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return local  # API failed, return what we have locally

        for concept in data.get('results', []):
            concept_uuid = concept.get('uuid')
            concept_name = concept.get('display', '').strip()
            if not concept_uuid or not concept_name:
                continue

            existing = self.search([('openmrs_uuid', '=', concept_uuid)], limit=1)
            if not existing:
                self.create({
                    'name': concept_name,
                    'openmrs_uuid': concept_uuid,
                })

        # Re-search locally with new data
        return self.search([('name', 'ilike', search_term)], limit=20)
