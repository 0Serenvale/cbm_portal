"""
Migration 16.0.3.6.0 — Fill NULL user_id on clinic.inventory.line

Phase 2 added user_id (required) to clinic.inventory.line.
Existing lines have user_id = NULL. Fill with the session's responsible_id,
falling back to the first admin user.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Fill user_id from the session's responsible_id where possible
    cr.execute("""
        UPDATE clinic_inventory_line l
        SET user_id = (
            SELECT ci.responsible_id
            FROM clinic_inventory ci
            WHERE ci.id = l.inventory_id
              AND ci.responsible_id IS NOT NULL
            LIMIT 1
        )
        WHERE l.user_id IS NULL
    """)
    updated = cr.rowcount
    _logger.info("[Migration 3.6.0] Set user_id from session responsible on %d lines", updated)

    # Fallback: any remaining NULLs (no responsible set) → use admin (id=1 or lowest active)
    cr.execute("""
        UPDATE clinic_inventory_line
        SET user_id = (
            SELECT id FROM res_users WHERE active = true ORDER BY id LIMIT 1
        )
        WHERE user_id IS NULL
    """)
    fallback = cr.rowcount
    if fallback:
        _logger.warning(
            "[Migration 3.6.0] Fell back to admin for %d lines with no session responsible",
            fallback
        )
