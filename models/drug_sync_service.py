# -*- coding: utf-8 -*-
import logging
import requests

from odoo import models, api

_logger = logging.getLogger(__name__)

# OpenMRS concept class and datatype UUIDs (standard CIEL dictionary)
CONCEPT_CLASS_DRUG_UUID = '8d490dfc-c2cc-11de-8d13-0010c6dffd0f'
CONCEPT_DATATYPE_NA_UUID = '8d4a4c94-c2cc-11de-8d13-0010c6dffd0f'


class DrugSyncService(models.AbstractModel):
    _name = 'drug.sync.service'
    _description = 'OpenMRS Drug Sync Service'

    def _get_openmrs_connection(self):
        """Read OpenMRS connection details from ir.config_parameter."""
        get = self.env['ir.config_parameter'].sudo().get_param
        base_url = get('openmrs.base.url', 'http://openmrs:8080/openmrs')
        username = get('openmrs.username', 'admin')
        password = get('openmrs.password', 'Admin123')
        return base_url, username, password

    def _openmrs_get(self, endpoint, params=None):
        base_url, username, password = self._get_openmrs_connection()
        url = f"{base_url}/ws/rest/v1/{endpoint}"
        resp = requests.get(url, params=params, auth=(username, password), timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _openmrs_post(self, endpoint, payload):
        base_url, username, password = self._get_openmrs_connection()
        url = f"{base_url}/ws/rest/v1/{endpoint}"
        resp = requests.post(url, json=payload, auth=(username, password), timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _create_ir_model_data(self, variant):
        """Create ir.model.data record to prevent the Java connector from duplicating."""
        existing = self.env['ir.model.data'].sudo().search([
            ('model', '=', 'product.product'),
            ('res_id', '=', variant.id),
            ('module', '=', '__export__'),
        ], limit=1)
        if not existing:
            self.env['ir.model.data'].sudo().create({
                'module': '__export__',
                'name': 'product_product_%s' % variant.uuid,
                'model': 'product.product',
                'res_id': variant.id,
                'noupdate': True,
            })
            _logger.info("Created ir.model.data for product %s uuid=%s", variant.id, variant.uuid)
