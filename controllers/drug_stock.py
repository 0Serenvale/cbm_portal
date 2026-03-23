# -*- coding: utf-8 -*-
#
# DRUG STOCK API — Public endpoint for Bahmni clinical frontend
#
# PURPOSE:
#   When a doctor searches and selects a drug in the Bahmni prescription screen,
#   the frontend calls this endpoint with the OpenMRS drug UUID.
#   It returns the current stock quantity from Odoo so the UI can warn
#   the doctor if the drug is out of stock before they finalize the prescription.
#
# CALLED BY:
#   Bahmni clinical frontend (addTreatment.html) via $http POST
#   URL: /api/drug-stock
#   Payload: { "uuid": "<openmrs_drug_uuid>" }
#
# AUTH:
#   auth='public' — no login required. The endpoint is read-only and only
#   exposes stock availability (no prices, no patient data, no sensitive info).
#   sudo() is used internally to bypass record rules since no user session exists.
#
# LINK BETWEEN OPENMRS AND ODOO:
#   product_template.uuid in Odoo stores the OpenMRS drug UUID.
#   This field is populated by the Drug Registration wizard in this module.
#   If a drug has not been registered (uuid not set), the endpoint returns
#   { available: null } meaning "unknown" — the UI should not warn in that case.
#
# STOCK LOGIC:
#   Queries stock.quant (real-time inventory) filtered by:
#   - product uuid match
#   - internal locations only (excludes virtual, transit, scrap locations)
#   Sums all internal location quantities.
#   Returns the location with the highest available stock.

from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class DrugStockController(http.Controller):

    @http.route('/api/drug-stock', type='json', auth='public', methods=['POST'], csrf=False, cors='*')
    def drug_stock(self, uuid=None, **kwargs):
        """
        Returns stock availability for a drug identified by its OpenMRS UUID.

        Request body (JSON):
            { "uuid": "b3c180c0-e903-4939-af7a-0fd79bfc2f91" }

        Response (JSON):
            {
                "available": true,       # true = in stock, false = out of stock, null = not registered in Odoo
                "quantity": 10.0,        # total quantity across all internal locations
                "location": "Pharmacie"  # name of the location with most stock
            }
        """

        # Validate input
        if not uuid:
            return {'available': None, 'quantity': 0, 'location': None}

        # Check if any Odoo product is linked to this OpenMRS drug UUID
        # product_template.uuid is set by the Drug Registration wizard
        product = request.env['product.template'].sudo().search(
            [('uuid', '=', uuid), ('active', '=', True)],
            limit=1
        )

        if not product:
            # Drug exists in OpenMRS but has not been registered/linked in Odoo yet
            # Return null so the UI knows to stay silent (not warn as out of stock)
            _logger.debug("Drug stock check: no Odoo product linked to OpenMRS UUID %s", uuid)
            return {'available': None, 'quantity': 0, 'location': None}

        # Query real-time stock across all internal locations
        quants = request.env['stock.quant'].sudo().search_read(
            [
                ('product_id.product_tmpl_id', '=', product.id),
                ('location_id.usage', '=', 'internal'),
                ('quantity', '>', 0),
            ],
            ['quantity', 'location_id'],
        )

        if not quants:
            # Product is registered but has zero stock everywhere
            _logger.debug(
                "Drug stock check: %s (UUID: %s) has zero stock in all locations",
                product.name, uuid
            )
            return {'available': False, 'quantity': 0, 'location': None}

        # Sum total and find the location with the most stock
        total_quantity = sum(q['quantity'] for q in quants)
        best = max(quants, key=lambda q: q['quantity'])

        _logger.debug(
            "Drug stock check: %s (UUID: %s) — total: %s, best location: %s",
            product.name, uuid, total_quantity, best['location_id'][1]
        )

        return {
            'available': True,
            'quantity': total_quantity,
            'location': best['location_id'][1],
        }
