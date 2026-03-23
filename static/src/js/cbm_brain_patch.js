/** @odoo-module **/
/**
 * CBM Kiosk Brain Patch
 * 
 * This file adds Brain integration to the CBM Kiosk.
 * It listens for brain:open-request events and pre-fills the request page.
 * 
 * Placed in clinic_staff_portal to keep CBM Portal owning its own code,
 * while Brain module dispatches events.
 */

import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";

// Storage for pending brain suggestions (session-level)
window.__brainPendingSuggestions = [];

// Listen for brain:open-request events
document.addEventListener('brain:open-request', (event) => {
    const suggestions = event.detail?.suggestions || [];
    window.__brainPendingSuggestions = suggestions;
    console.log('[CBM Brain] Received', suggestions.length, 'suggestions');
    
    // Trigger navigation to request page
    // This is a fallback; the Brain widget should also trigger navigation
    const goRequestBtn = document.querySelector('[data-brain-request-trigger]');
    if (goRequestBtn) {
        goRequestBtn.click();
    }
});

/**
 * Helper to convert brain suggestions to CBM product format
 * and inject them into the kiosk state.
 */
export function injectBrainSuggestionsIntoKiosk(kioskState) {
    const suggestions = window.__brainPendingSuggestions || [];
    if (suggestions.length === 0) return false;
    
    // Convert to CBM product format
    const products = suggestions.map(s => ({
        id: s.product_id,
        name: s.product_name,
        qty: s.suggested_qty || 1,
        uom_name: '',  // Will be populated if needed
        qty_available: s.current_stock || 0,
        lot_id: false,
        lot_name: false,
        hoarding_status: 'ok',
        ward_qty: 0,
        hoarding_message: '',
        // Track brain insight for marking as executed
        _brain_insight_id: s.insight_id,
    }));
    
    // Inject into kiosk state
    kioskState.selectedProducts = products;
    
    // Clear pending
    window.__brainPendingSuggestions = [];
    
    console.log('[CBM Brain] Injected', products.length, 'products into request page');
    return true;
}

/**
 * Export a hook for marking brain insights as executed after successful submit.
 * Call this from submitRequest() after success.
 */
export async function markBrainInsightsExecuted(rpc, products) {
    const insightIds = products
        .filter(p => p._brain_insight_id)
        .map(p => p._brain_insight_id);
    
    if (insightIds.length === 0) return;
    
    try {
        await rpc("/cbm/brain/mark_executed", { insight_ids: insightIds });
        console.log('[CBM Brain] Marked', insightIds.length, 'insights as executed');
    } catch (error) {
        console.error('[CBM Brain] Failed to mark insights as executed', error);
    }
}
