# -*- coding: utf-8 -*-
"""
Sale Order extension for consumption ledger management.

When SO is confirmed or cancelled, archive related ledger entries
to prevent phantom returns from the portal.
"""

from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """Archive ledger entries when SO is confirmed (invoiced)."""
        res = super().action_confirm()
        self._archive_ledger_entries('confirmed')
        return res

    def action_cancel(self):
        """Archive ledger entries when SO is cancelled."""
        res = super().action_cancel()
        self._archive_ledger_entries('cancelled')
        return res

    def _archive_ledger_entries(self, reason):
        """Archive all active ledger entries for this SO."""
        Ledger = self.env['clinic.consumption.ledger'].sudo()
        for order in self:
            entries = Ledger.search([
                ('sale_order_id', '=', order.id),
                ('state', '=', 'active'),
            ])
            if entries:
                entries.write({'state': 'archived'})
                _logger.info(
                    "Archived %d ledger entries for SO %s (reason: %s)",
                    len(entries), order.name, reason
                )
