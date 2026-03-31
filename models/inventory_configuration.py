# -*- coding: utf-8 -*-
"""
Inventory Configuration Model - Schedule and settings for quarterly inventories.

Manages:
- Inventory scheduling (dates, duration, locations)
- Auto-announcement generation
- Cron job triggering (quarterly: Jan 1, Apr 1, Jul 1, Oct 1)
"""

from datetime import datetime, timedelta
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class InventoryConfiguration(models.Model):
    """Configuration for automatic inventory scheduling."""

    _name = 'clinic.inventory.config'
    _description = 'Inventory Configuration'
    _rec_name = 'name'

    # ============================================================
    # FIELDS
    # ============================================================

    name = fields.Char(
        string='Configuration Name',
        required=True,
        default='Current Inventory',
        help='E.g., "Q2 2026 Inventory"'
    )

    inventory_start_date = fields.Date(
        string='Inventory Start Date',
        required=True,
        help='Date when inventory counting begins'
    )

    duration_days = fields.Integer(
        string='Duration (Days)',
        required=True,
        default=2,
        help='How many days the inventory will take (2-3 typical)'
    )

    location_ids = fields.Many2many(
        'stock.location',
        string='Target Locations',
        help='Locations where this inventory will be conducted. Leave empty for all.'
    )

    announcement_text = fields.Text(
        string='Announcement Text',
        help='Text shown in banner. Auto-generated from config if empty.'
    )

    cron_schedule = fields.Selection(
        [
            ('quarterly', 'Quarterly (Jan 1, Apr 1, Jul 1, Oct 1)'),
            ('manual', 'Manual Only'),
        ],
        string='Cron Schedule',
        default='quarterly',
        help='How often to automatically trigger inventory'
    )

    last_triggered = fields.Datetime(
        string='Last Triggered',
        readonly=True,
        help='Timestamp of last cron execution'
    )

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('active', 'Active'),
            ('completed', 'Completed'),
        ],
        string='State',
        default='draft',
        help='Configuration status'
    )

    # ============================================================
    # COMPUTED FIELDS
    # ============================================================

    @api.depends('inventory_start_date')
    def _compute_end_date(self):
        """Calculate inventory end date from start + duration."""
        for rec in self:
            if rec.inventory_start_date and rec.duration_days:
                start = fields.Date.from_string(rec.inventory_start_date)
                rec.inventory_end_date = start + timedelta(days=rec.duration_days - 1)
            else:
                rec.inventory_end_date = False

    inventory_end_date = fields.Date(
        string='Inventory End Date',
        compute='_compute_end_date',
        store=True,
        help='Auto-calculated: start_date + duration_days - 1'
    )

    @api.depends('announcement_text', 'inventory_start_date', 'duration_days')
    def _compute_announcement(self):
        """Auto-generate announcement text if not manually set."""
        for rec in self:
            if rec.announcement_text:
                # Custom text takes precedence
                rec.generated_announcement = rec.announcement_text
            elif rec.inventory_start_date and rec.duration_days:
                # Auto-generate only if custom is empty
                date_str = rec.inventory_start_date.strftime('%d/%m/%Y')
                duration_str = f"{rec.duration_days} jour" if rec.duration_days == 1 else f"{rec.duration_days} jours"
                rec.generated_announcement = (
                    f"La pharmacie sera fermée le {date_str} pour inventaire pendant {duration_str}."
                )
            else:
                rec.generated_announcement = ''

    generated_announcement = fields.Text(
        string='Generated Announcement',
        compute='_compute_announcement',
        store=True,
        help='Auto-generated announcement (or custom if provided)'
    )

    # ============================================================
    # CONSTRAINTS & METHODS
    # ============================================================

    @api.constrains('duration_days')
    def _check_duration(self):
        """Validate duration is reasonable."""
        for rec in self:
            if rec.duration_days < 1 or rec.duration_days > 10:
                raise ValueError(_('Duration must be between 1 and 10 days'))

    @api.constrains('inventory_start_date')
    def _check_start_date(self):
        """Validate start date is not in past."""
        for rec in self:
            if rec.inventory_start_date and rec.inventory_start_date < fields.Date.today():
                raise ValueError(_('Start date cannot be in the past'))

    # ============================================================
    # CRON JOB LOGIC
    # ============================================================

    @api.model
    def action_trigger_quarterly_inventory(self):
        """
        Cron job: Check if today is a trigger date and create inventory session.

        Trigger dates: January 1, April 1, July 1, October 1
        Logic:
        - Check if today matches quarterly schedule
        - Fetch active configuration
        - Create clinic.inventory session with config values
        - Set session state to 'active'
        - Update last_triggered timestamp
        """
        try:
            today = fields.Date.today()
            month = today.month
            day = today.day

            # Check if today is a trigger date
            trigger_dates = [1, 4, 7, 10]  # Jan, Apr, Jul, Oct
            is_trigger_date = month in trigger_dates and day == 1

            _logger.info(
                "[INVENTORY CRON] Checking trigger date. Today: %s, Is trigger: %s",
                today, is_trigger_date
            )

            if not is_trigger_date:
                return False

            # Get active configuration
            config = self.search(
                [('state', '=', 'active')],
                limit=1
            )

            if not config:
                _logger.warning(
                    "[INVENTORY CRON] No active inventory configuration found on %s",
                    today
                )
                return False

            # Check if session already exists for this trigger date (prevent duplicates)
            ClinicInventory = self.env['clinic.inventory']
            existing = ClinicInventory.search([
                ('start_date', '=', today),
                ('state', 'in', ['draft', 'active', 'pending_approval', 'approved']),
            ], limit=1)

            if existing:
                _logger.info(
                    "[INVENTORY CRON] Session already exists for %s (id=%s), skipping creation",
                    today, existing.id
                )
                config.write({'last_triggered': fields.Datetime.now()})
                return True

            # Create inventory session
            inventory = ClinicInventory.create({
                'name': config.name or 'Quarterly Inventory',
                'location_id': config.location_ids[0].id if config.location_ids else False,
                'state': 'active',  # Skip draft, go straight to active
                'start_date': today,
                'end_date': config.inventory_end_date,
            })

            # Optionally create teams (can be done manually via UI)
            _logger.info(
                "[INVENTORY CRON] Created inventory session %s on %s",
                inventory.name, today
            )

            # Update last_triggered
            config.write({
                'last_triggered': fields.Datetime.now(),
                'state': 'active',
            })

            return True

        except Exception as e:
            _logger.error("[INVENTORY CRON] Error: %s", str(e))
            return False

    def action_trigger_now(self):
        """Manual trigger for testing/on-demand inventory creation."""
        return self.action_trigger_quarterly_inventory()

    def action_preview_announcement(self):
        """Show what announcement banner will look like."""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Announcement Preview'),
                'message': self.generated_announcement,
                'type': 'info',
                'sticky': False,
            }
        }
