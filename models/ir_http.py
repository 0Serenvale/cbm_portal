# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    """Extend session_info to pass fullscreen kiosk mode to frontend"""
    _inherit = 'ir.http'

    def session_info(self):
        """
        Add cbm_fullscreen_kiosk flag to session info.

        This allows the frontend JavaScript to know if the current user
        has fullscreen kiosk mode enabled BEFORE the page renders,
        preventing navbar flash in Firefox.
        """
        result = super(IrHttp, self).session_info()

        try:
            user = request.env.user
            # Add kiosk mode flag if user has it enabled
            if hasattr(user, 'fullscreen_kiosk_mode'):
                kiosk_enabled = user.fullscreen_kiosk_mode
                result['cbm_fullscreen_kiosk'] = kiosk_enabled
                _logger.info(f"[CBM KIOSK] User {user.name} (ID={user.id}): fullscreen_kiosk_mode = {kiosk_enabled}")
            else:
                result['cbm_fullscreen_kiosk'] = False
                _logger.warning(f"[CBM KIOSK] User {user.name} has no fullscreen_kiosk_mode field")
        except Exception as e:
            _logger.error(f"[CBM KIOSK] Error in session_info: {e}")
            result['cbm_fullscreen_kiosk'] = False

        return result
