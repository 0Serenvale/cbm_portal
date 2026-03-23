# -*- coding: utf-8 -*-
from odoo import fields, models


class DrugDosageForm(models.Model):
    _name = 'drug.dosage.form'
    _description = 'OpenMRS Dosage Form'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True, index=True)
    openmrs_id = fields.Integer(string='OpenMRS ID', index=True)
    openmrs_uuid = fields.Char(string='OpenMRS UUID', required=True, index=True)

    _sql_constraints = [
        ('uuid_unique', 'UNIQUE(openmrs_uuid)', 'Dosage form UUID must be unique.'),
    ]
