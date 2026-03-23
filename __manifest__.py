{
    'name': 'CBM Portal',
    'version': '16.0.3.5.0',
    'category': 'Inventory/Inventory',
    'summary': 'Kiosk-style interface for clinic staff stock operations',
    'description': """
CBM Portal
==========

A kiosk-style SPA interface for clinic staff (Nurses/Doctors) that provides:

* **Request Medication**: Pull stock from pharmacy to ward
* **Consumption**: Billable dispensing to patient, internal use
* **My History**: View request status

Features:
- OWL-based Single Page App (no page reloads)
- Barcode scanner support
- Touch-friendly design inspired by web_responsive
- Patient billing integration
    """,
    'author': 'Serenvale',
    'website': 'https://serenvale.com',
    'license': 'LGPL-3',
    'depends': [
        'serenvale_stock_access_control',
        'stock',
        'purchase',  # For PO blocking rules
        'sale',
        'account',  # For invoices tile
        'maintenance',  # For maintenance request tile
        'hr_holidays',  # For time off requests
        'mail',
        'web_responsive',
        'bahmni_product',  # For uuid field on product.product
    ],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'security/stock_record_rules.xml',
        'views/res_users_views.xml',
        'views/res_config_settings_views.xml',  # Settings page
        'views/stock_picking_type_views.xml',
        'views/stock_picking_views.xml',
        'views/stock_location_views.xml',
        'views/stock_move_views.xml',
        'views/stock_discrepancy_views.xml',
        'views/product_product_views.xml',
        'views/product_template_drug_views.xml',
        'views/kiosk_view.xml',
        'views/cbm_kiosk_action.xml',
        'views/menu.xml',
        'views/clinic_portal_tile_views.xml',
        'views/clinic_document_views.xml',
        'views/product_pricelist_views.xml',
        'report/cashier_session_report.xml',  # Must load BEFORE views that reference it
        'report/accountability_warning_report.xml',
        'views/cashier_session_views.xml',
        'views/kiosk_access_log_views.xml',
        'views/clinic_workstation_views.xml',
        'data/default_tiles.xml',
        'data/sync_users_action.xml',
        'data/mail_templates.xml',
        'data/cashier_session_sequence.xml',
        'data/cashier_session_cron.xml',
        'data/consumption_ledger_cron.xml',
        'data/document_compliance_cron.xml',
        'data/accountability_cron.xml',
        'views/consumption_ledger_views.xml',
        'wizard/drug_sync_wizard_views.xml',
        'wizard/openmrs_import_wizard_views.xml',
        'wizard/compliance_report_wizard_views.xml',
        'views/drug_dosage_form_views.xml',
        'views/drug_openmrs_concept_views.xml',
        'views/drug_sync_menu.xml',
        'views/clinic_prescription_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # CRITICAL: Load kiosk body class FIRST to prevent navbar flash in Firefox
            'clinic_staff_portal/static/src/js/kiosk_body_class.js',
            # CBM Portal SCSS
            'clinic_staff_portal/static/src/scss/portal_dashboard.scss',
            'clinic_staff_portal/static/src/scss/cbm_kiosk.scss',
            'clinic_staff_portal/static/src/scss/cbm_cashier.scss',
            'clinic_staff_portal/static/src/scss/cbm_timeoff.scss',
            'clinic_staff_portal/static/src/scss/folder_selector.scss',
            # web_responsive overrides (loaded after web_responsive dependency)
            'clinic_staff_portal/static/src/scss/web_responsive_override.scss',
            'clinic_staff_portal/static/src/scss/app_icon_colors.scss',
            # JS/XML
            # TimeOff component (must load BEFORE cbm_kiosk.js which imports it)
            'clinic_staff_portal/static/src/components/timeoff/timeoff.js',
            'clinic_staff_portal/static/src/components/timeoff/timeoff.xml',
            # Documents component (must load BEFORE cbm_kiosk.js which imports it)
            'clinic_staff_portal/static/src/components/documents/documents.js',
            'clinic_staff_portal/static/src/components/documents/documents.xml',
            # Accountability component (must load BEFORE cbm_kiosk.js which imports it)
            'clinic_staff_portal/static/src/components/accountability/accountability.js',
            'clinic_staff_portal/static/src/components/accountability/accountability.xml',
            'clinic_staff_portal/static/src/js/cbm_global_service.js',
            'clinic_staff_portal/static/src/js/cbm_kiosk.js',
            'clinic_staff_portal/static/src/js/cbm_brain_patch.js',
            'clinic_staff_portal/static/src/js/folder_selector.js',
            'clinic_staff_portal/static/src/xml/heroicons.xml',
            'clinic_staff_portal/static/src/xml/cbm_kiosk.xml',
            'clinic_staff_portal/static/src/xml/folder_selector.xml',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'auto_install': False,
}
