/** @odoo-module **/
/**
 * Kiosk Body Class - Early Initialization
 *
 * This module runs BEFORE the main kiosk component loads.
 * It adds the 'cbm-fullscreen-kiosk' class to the body tag AS SOON AS POSSIBLE
 * to prevent navbar flash (FOUC) in Firefox.
 *
 * IMPORTANT: This must load BEFORE cbm_kiosk.js in the manifest.
 */

import { session } from "@web/session";

// Debug: Log session info
console.log('[CBM KIOSK] Session info:', {
    cbm_fullscreen_kiosk: session.cbm_fullscreen_kiosk,
    user_id: session.uid,
    user_name: session.name,
});

// Apply kiosk mode if enabled
if (session.cbm_fullscreen_kiosk) {
    console.log('[CBM KIOSK] User has kiosk mode enabled, applying CSS...');

    // STEP 1: Add inline style to <head> immediately (even before body exists)
    // This hides navbar as soon as it's created
    const injectStyle = () => {
        if (!document.getElementById('cbm-kiosk-inline-style')) {
            const style = document.createElement('style');
            style.id = 'cbm-kiosk-inline-style';
            style.textContent = `
                /* CBM Kiosk Mode - Hide Odoo UI immediately */
                body.cbm-fullscreen-kiosk .o_main_navbar,
                body.cbm-fullscreen-kiosk .o_menu_toggle,
                body.cbm-fullscreen-kiosk .o_menu_apps,
                body.cbm-fullscreen-kiosk .o_control_panel {
                    display: none !important;
                }
                body.cbm-fullscreen-kiosk .o_action_manager {
                    top: 0 !important;
                    height: 100vh !important;
                }
            `;
            (document.head || document.documentElement).appendChild(style);
            console.log('[CBM KIOSK] Injected inline style');
        }
    };

    // STEP 2: Add class to <html> immediately (it always exists)
    if (document.documentElement) {
        document.documentElement.classList.add('cbm-fullscreen-kiosk');
        console.log('[CBM KIOSK] Added class to <html>');
    }

    // STEP 3: Watch for <body> element and add class immediately when it appears
    const addBodyClass = () => {
        if (document.body && !document.body.classList.contains('cbm-fullscreen-kiosk')) {
            document.body.classList.add('cbm-fullscreen-kiosk');
            console.log('[CBM KIOSK] Added class to <body>');
            return true;
        }
        return false;
    };

    // Try to inject style and add body class immediately
    injectStyle();
    if (!addBodyClass()) {
        // Body doesn't exist yet, use MutationObserver to watch for it
        const observer = new MutationObserver(() => {
            if (addBodyClass()) {
                observer.disconnect();
            }
        });
        observer.observe(document.documentElement, { childList: true });
    }

    console.log('[CBM KIOSK] Fullscreen kiosk mode initialized');
} else {
    console.log('[CBM KIOSK] Fullscreen kiosk mode NOT enabled for this user');
}
