"""
Migration 16.0.3.6.0 — Remove user_id from clinic.inventory.line

user_id was added in Phase 2 but is unnecessary — user identity is already
available via request.env.user on every RPC call. This migration drops
the column cleanly if it still exists.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        ALTER TABLE clinic_inventory_line
        DROP COLUMN IF EXISTS user_id
    """)
    _logger.info("[Migration 3.6.0] Dropped user_id column from clinic_inventory_line")
