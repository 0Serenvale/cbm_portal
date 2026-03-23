# -*- coding: utf-8 -*-
import logging
import requests

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DrugSyncWizard(models.TransientModel):
    _name = 'drug.sync.wizard'
    _description = 'Drug Registration Wizard'

    product_tmpl_id = fields.Many2one(
        'product.template', string='Product', required=True, readonly=True
    )
    drug_name = fields.Char(
        string='Prescribing Name',
        required=True,
        help='The name doctors will see when prescribing this drug'
    )

    concept_id = fields.Many2one(
        'drug.openmrs.concept',
        string='Active Ingredient (DCI)',
        help='International Common Denomination — type to search'
    )

    dosage_form_id = fields.Many2one(
        'drug.dosage.form',
        string='Dosage Form',
        help='Pharmaceutical form (tablet, injection, syrup, etc.)'
    )

    strength = fields.Char(
        string='Strength',
        help='e.g. 500 mg, 10 mg/ml, 1%'
    )

    def _get_openmrs_connection(self):
        get = self.env['ir.config_parameter'].sudo().get_param
        base_url = get('openmrs.base.url', 'http://openmrs:8080/openmrs')
        username = get('openmrs.username', 'admin')
        password = get('openmrs.password', 'Admin123')
        return base_url, username, password

    def action_confirm_sync(self):
        """Create drug in OpenMRS and write back to product."""
        self.ensure_one()
        missing = []
        if not self.concept_id:
            missing.append('Concept (DCI)')
        if not self.dosage_form_id:
            missing.append('Dosage Form')
        if not self.strength:
            missing.append('Strength')
        if missing:
            raise UserError("Please fill in: %s" % ', '.join(missing))

        sync_service = self.env['drug.sync.service'].sudo()
        template = self.product_tmpl_id
        variant = template.product_variant_ids[:1]

        if not variant:
            raise UserError("Product has no variant. Save the product first.")

        base_url, username, password = self._get_openmrs_connection()

        # Build drug payload using UUIDs from local cache tables
        drug_payload = {
            'name': self.drug_name,
            'concept': self.concept_id.openmrs_uuid,
            'dosageForm': self.dosage_form_id.openmrs_uuid,
            'strength': self.strength,
            'combination': False,
        }
        url = f"{base_url}/ws/rest/v1/drug"
        try:
            resp = requests.post(
                url, json=drug_payload,
                auth=(username, password), timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()
        except requests.exceptions.HTTPError as e:
            error_body = e.response.text if e.response else str(e)
            raise UserError("OpenMRS rejected the drug creation:\n%s" % error_body)
        except Exception as e:
            raise UserError("Failed to create drug in OpenMRS: %s" % str(e))

        drug_uuid = result.get('uuid')
        if not drug_uuid:
            raise UserError("OpenMRS did not return a UUID.")

        # Write back to product — use SQL to avoid triggering any overrides
        cr = self.env.cr
        cr.execute(
            "UPDATE product_product SET uuid = %s WHERE id = %s",
            (drug_uuid, variant.id)
        )
        cr.execute("""
            UPDATE product_template
            SET uuid = %s,
                openmrs_concept_uuid = %s,
                dosage_form_id = %s,
                strength = %s,
                drug = %s,
                is_synced_to_openmrs = TRUE
            WHERE id = %s
        """, (
            drug_uuid,
            self.concept_id.openmrs_uuid,
            self.dosage_form_id.id,
            self.strength,
            self.concept_id.name,
            template.id,
        ))

        # Invalidate cache
        variant.invalidate_recordset()
        template.invalidate_recordset()

        # Create ir_model_data to prevent connector duplication
        sync_service._create_ir_model_data(variant)

        _logger.info(
            "Drug '%s' synced to OpenMRS via wizard. uuid=%s concept=%s",
            self.drug_name, drug_uuid, self.concept_id.openmrs_uuid
        )

        return {'type': 'ir.actions.act_window_close'}
