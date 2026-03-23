# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Fullscreen Kiosk Mode - hides Odoo navbar/sidebar
    # This is SEPARATE from the Home Action redirect (which is handled by ir.default)
    fullscreen_kiosk_mode = fields.Boolean(
        string='Fullscreen Kiosk Mode',
        default=False,
        help='If checked, Odoo navigation (navbar, sidebar) is hidden when using CBM Portal.\n'
             'User sees only the CBM Portal interface.\n'
             'Uncheck for users who need to access other Odoo apps.'
    )

    def _get_cbm_kiosk_action(self):
        """Get the CBM Kiosk client action record"""
        return self.env.ref('clinic_staff_portal.action_cbm_kiosk', raise_if_not_found=False)

    @api.model
    def action_sync_cbm_portal_users(self):
        """
        Configure all internal users for CBM Portal:
        1. Set action_id to CBM Kiosk (redirect on login)
        2. Enable fullscreen_kiosk_mode (hide navbar/sidebar)
        3. Add to group_clinic_portal_user (access rights)
        
        Run this to sync existing users after module is already installed.
        """
        cbm_action = self._get_cbm_kiosk_action()
        if not cbm_action:
            _logger.warning("CBM Kiosk action not found!")
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Error', 'message': 'CBM Kiosk action not found!', 'type': 'danger'}}
        
        # Get portal user group
        portal_group = self.env.ref('clinic_staff_portal.group_clinic_portal_user', raise_if_not_found=False)
        
        # Find all internal users (except superuser)
        users_to_sync = self.search([
            ('share', '=', False),
            ('id', '!=', 1),  # Don't modify superuser
        ])
        
        count = len(users_to_sync)
        _logger.info(f"Syncing CBM Portal for {count} users...")
        
        # Prepare write values
        write_vals = {
            'action_id': cbm_action.id,
            'fullscreen_kiosk_mode': True,
        }
        
        # Add to portal group if found
        if portal_group:
            write_vals['groups_id'] = [(4, portal_group.id)]
        
        # Apply to all users
        users_to_sync.write(write_vals)
        
        _logger.info(f"✓ Synced {count} users")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync Complete',
                'message': f'Configured {count} users: redirect + fullscreen + group access.',
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def action_unsync_cbm_portal_users(self):
        """
        REVERSE: Disable CBM Portal kiosk mode for all users.
        1. Clear action_id (no redirect on login)
        2. Disable fullscreen_kiosk_mode (show navbar/sidebar)
        
        Use this to restore normal Odoo navigation for all users.
        """
        # Find all internal users with kiosk mode enabled
        users_to_unsync = self.search([
            ('share', '=', False),
            ('id', '!=', 1),  # Don't modify superuser
            '|',
            ('fullscreen_kiosk_mode', '=', True),
            ('action_id', '!=', False),
        ])
        
        count = len(users_to_unsync)
        _logger.info(f"Disabling CBM Portal kiosk mode for {count} users...")
        
        # Clear kiosk settings
        users_to_unsync.write({
            'action_id': False,
            'fullscreen_kiosk_mode': False,
        })
        
        _logger.info(f"✓ Disabled kiosk mode for {count} users")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Kiosk Mode Disabled',
                'message': f'Restored normal Odoo navigation for {count} users.',
                'type': 'success',
                'sticky': False,
            }
        }
