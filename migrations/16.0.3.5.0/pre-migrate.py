# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migration for v16.0.3.5.0:
    - Drop old unique constraint on clinic_document_acknowledgement (document_id, user_id)
      so the new constraint (document_id, user_id, document_version) can be created.
    - Add document_version column with default=1 for existing records.
    """
    _logger.info("[clinic_staff_portal] Pre-migration: updating acknowledgement constraints")

    # Drop old unique constraint if it exists
    cr.execute("""
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'clinic_document_acknowledgement'::regclass
        AND contype = 'u'
        AND conname = 'clinic_document_acknowledgement_unique_user_document'
    """)
    if cr.fetchone():
        cr.execute("""
            ALTER TABLE clinic_document_acknowledgement
            DROP CONSTRAINT clinic_document_acknowledgement_unique_user_document
        """)
        _logger.info("[clinic_staff_portal] Dropped old unique constraint unique_user_document")

    # Add document_version column if not exists, default 1 for existing acks
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'clinic_document_acknowledgement'
        AND column_name = 'document_version'
    """)
    if not cr.fetchone():
        cr.execute("""
            ALTER TABLE clinic_document_acknowledgement
            ADD COLUMN document_version INTEGER NOT NULL DEFAULT 1
        """)
        _logger.info("[clinic_staff_portal] Added document_version column with default=1")

    # Add version column to clinic_document if not exists
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'clinic_document'
        AND column_name = 'version'
    """)
    if not cr.fetchone():
        cr.execute("""
            ALTER TABLE clinic_document
            ADD COLUMN version INTEGER NOT NULL DEFAULT 1
        """)
        _logger.info("[clinic_staff_portal] Added version column to clinic_document")
