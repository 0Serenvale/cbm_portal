# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta

import logging
_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    """
    CBM Portal PO blocking rules.

    Uses replenishment_policy (Soft/Hard) and consumption_start_date from
    stock.location to enforce anti-hoarding rules on Purchase Orders.

    This mirrors the transfer blocking logic in stock_picking.py.
    """
    _inherit = 'purchase.order'

    @api.model
    def default_get(self, fields_list):
        """
        Override to enforce pending reception block at PO creation.

        Blocking Logic:
        1. Find locations where user is responsible
        2. Check each location's replenishment_policy (none/soft/hard)
        3. Count pending receptions older than threshold
        4. Block (hard) or warn (soft) based on policy
        """
        user = self.env.user

        # Check admin exemption
        ICP = self.env['ir.config_parameter'].sudo()
        admin_ids_str = ICP.get_param('clinic_staff_portal.admin_user_ids', '')
        admin_ids = [int(i) for i in admin_ids_str.split(',') if i.strip().isdigit()]
        is_admin = user.id in admin_ids or user.has_group('base.group_system')

        if not is_admin:
            block_days = int(ICP.get_param('clinic_staff_portal.pending_po_block_days', '0') or 0)

            if block_days > 0:
                # Find locations where user is responsible
                responsible_locations = self.env['stock.location'].sudo().search([
                    ('responsible_user_ids', 'in', [user.id])
                ])

                # Filter to locations with hard blocking policy
                hard_block_locations = responsible_locations.filtered(
                    lambda loc: loc.replenishment_policy == 'hard'
                )

                if hard_block_locations:
                    # Find incoming picking types for these locations
                    incoming_types = self.env['stock.picking.type'].sudo().search([
                        ('code', '=', 'incoming'),
                        ('default_location_dest_id', 'in', hard_block_locations.ids)
                    ])

                    if incoming_types:
                        # Calculate date threshold
                        threshold_date = fields.Datetime.now() - timedelta(days=block_days)

                        # Build domain for pending receptions
                        domain = [
                            ('picking_type_id', 'in', incoming_types.ids),
                            ('state', 'not in', ['done', 'cancel']),
                            ('scheduled_date', '<', threshold_date)
                        ]

                        # Check consumption_start_date (Trust Data From) for each location
                        # Only count receptions at locations where we trust the data
                        for loc in hard_block_locations:
                            if loc.consumption_start_date:
                                # Only count receptions after the trust date
                                domain.append(('scheduled_date', '>=', fields.Datetime.to_datetime(loc.consumption_start_date)))

                        pending_receptions = self.env['stock.picking'].sudo().search(domain)

                        if pending_receptions:
                            # Get responsible names for the message
                            responsible_names = set()
                            for loc in hard_block_locations:
                                for resp in loc.responsible_user_ids:
                                    if resp.id != user.id:
                                        responsible_names.add(resp.name)

                            if not responsible_names:
                                responsible_names = {'votre responsable'}

                            _logger.warning(
                                "[CBM PO BLOCK] User %s blocked from creating PO: "
                                "%d pending receptions older than %d days at hard-block locations",
                                user.name, len(pending_receptions), block_days
                            )

                            raise UserError(_(
                                "Réceptions en attente\n\n"
                                "Vous avez %(count)d réception(s) en attente depuis plus de %(days)d jours.\n\n"
                                "La création de nouvelles commandes est temporairement bloquée "
                                "conformément aux règles de gestion des stocks.\n\n"
                                "Merci de contacter %(responsibles)s pour le traitement.\n\n"
                                "Seuil : %(threshold)d jours"
                            ) % {
                                'count': len(pending_receptions),
                                'days': block_days,
                                'responsibles': ', '.join(sorted(responsible_names)),
                                'threshold': block_days,
                            })

        return super().default_get(fields_list)

    @api.model
    def create(self, vals):
        """
        Override create to enforce blocking at model level.

        This ensures users cannot bypass CBM portal blocking by creating
        POs directly in the Odoo backend or via API.
        """
        user = self.env.user

        # Check admin exemption
        ICP = self.env['ir.config_parameter'].sudo()
        admin_ids_str = ICP.get_param('clinic_staff_portal.admin_user_ids', '')
        admin_ids = [int(i) for i in admin_ids_str.split(',') if i.strip().isdigit()]
        is_admin = user.id in admin_ids or user.has_group('base.group_system')

        if not is_admin:
            block_days = int(ICP.get_param('clinic_staff_portal.pending_po_block_days', '0') or 0)

            if block_days > 0:
                # Get destination location from picking_type_id if provided
                picking_type_id = vals.get('picking_type_id')
                if picking_type_id:
                    picking_type = self.env['stock.picking.type'].browse(picking_type_id)
                    dest_location = picking_type.default_location_dest_id

                    # Check if destination location has hard blocking
                    if dest_location and dest_location.replenishment_policy == 'hard':
                        # Check if user is responsible for this location
                        if user.id in dest_location.responsible_user_ids.ids:
                            threshold_date = fields.Datetime.now() - timedelta(days=block_days)

                            # Find incoming picking types for this location
                            incoming_types = self.env['stock.picking.type'].sudo().search([
                                ('code', '=', 'incoming'),
                                ('default_location_dest_id', '=', dest_location.id)
                            ])

                            if incoming_types:
                                domain = [
                                    ('picking_type_id', 'in', incoming_types.ids),
                                    ('state', 'not in', ['done', 'cancel']),
                                    ('scheduled_date', '<', threshold_date)
                                ]

                                # Respect consumption_start_date
                                if dest_location.consumption_start_date:
                                    domain.append(('scheduled_date', '>=', fields.Datetime.to_datetime(dest_location.consumption_start_date)))

                                pending_count = self.env['stock.picking'].sudo().search_count(domain)

                                if pending_count > 0:
                                    _logger.warning(
                                        "[CBM PO BLOCK] User %s blocked from creating PO to %s: "
                                        "%d pending receptions older than %d days",
                                        user.name, dest_location.name, pending_count, block_days
                                    )

                                    raise UserError(_(
                                        "Réceptions en attente\n\n"
                                        "Vous avez %(count)d réception(s) en attente à %(location)s.\n\n"
                                        "La création de nouvelles commandes est temporairement bloquée."
                                    ) % {
                                        'count': pending_count,
                                        'location': dest_location.name,
                                    })

        return super().create(vals)
