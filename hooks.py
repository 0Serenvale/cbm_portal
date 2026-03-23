# -*- coding: utf-8 -*-
"""
Post-init hook for CBM Portal.
Does NOT auto-assign users to kiosk mode - this should be done manually after testing.
"""
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(cr, registry):
    """
    On install/upgrade:
    1. Update default tiles with correct icon/color values
    2. Create and link convention partners for pricelists
    
    NOTE: User assignment to kiosk mode has been REMOVED.
    To enable kiosk mode for specific users, manually:
    - Set user's Home Action to "CBM Kiosk"
    - Check "Fullscreen Kiosk Mode" on their profile
    - Add them to group "Clinic Portal User"
    """
    from odoo import api, SUPERUSER_ID
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    _logger.info("CBM Portal: Running post-init hook...")
    
    # ------------------------------------------
    # Update tiles
    # ------------------------------------------
    _update_default_tiles(env)
    
    # ------------------------------------------
    # Create convention partners
    # ------------------------------------------
    _create_convention_partners(env)
    
    _logger.info("✓ CBM Portal post-init complete. Users must be manually configured for kiosk mode.")


def _update_default_tiles(env):
    """
    Force-update the default tiles to have correct Heroicon values and colors.
    This ensures the demo data is always valid after upgrade.
    """
    tile_updates = {
        'clinic_staff_portal.tile_quotations': {
            'icon': 'document-text',
            'color': '#3B82F6',
            'icon_color': '#ffffff',
        },
        'clinic_staff_portal.tile_invoices': {
            'icon': 'banknotes',
            'color': '#10B981',
            'icon_color': '#ffffff',
        },
        'clinic_staff_portal.tile_maintenance_request': {
            'icon': 'wrench-screwdriver',
            'color': '#6B7280',
            'icon_color': '#ffffff',
        },
    }
    
    updated_count = 0
    for xml_id, values in tile_updates.items():
        tile = env.ref(xml_id, raise_if_not_found=False)
        if tile:
            tile.write(values)
            updated_count += 1
            _logger.info(f"Updated tile: {xml_id}")
    
    _logger.info(f"✓ Updated {updated_count} default tiles with correct icon/color values")


def _create_convention_partners(env):
    """
    For each pricelist with convention_coverage_pct > 0 and no payer_partner_id:
    1. Create a partner with the pricelist name + " (Convention)"
    2. Link it as the payer_partner_id
    """
    Pricelist = env['product.pricelist']
    Partner = env['res.partner']
    
    # Find pricelists with convention but no payer partner
    convention_pricelists = Pricelist.search([])
    created_count = 0
    
    for pl in convention_pricelists:
        # Check if has convention field and value > 0
        if not hasattr(pl, 'convention_coverage_pct'):
            continue
        if not pl.convention_coverage_pct or pl.convention_coverage_pct <= 0:
            continue
        if pl.payer_partner_id:
            # Already has a partner linked
            continue
        
        # Create partner for this convention
        partner_name = f"{pl.name} (Convention)"
        
        # Check if partner already exists
        existing = Partner.search([('name', '=', partner_name)], limit=1)
        if existing:
            partner = existing
        else:
            partner = Partner.create({
                'name': partner_name,
                'is_company': True,
                'company_type': 'company',
                'comment': f"Auto-created convention partner for pricelist: {pl.name}",
            })
            _logger.info(f"Created convention partner: {partner_name}")
        
        # Link to pricelist
        pl.payer_partner_id = partner.id
        created_count += 1
        _logger.info(f"Linked partner '{partner_name}' to pricelist '{pl.name}'")
    
    _logger.info(f"✓ Created/linked {created_count} convention partners")

