/** @odoo-module **/
/**
 * CBM Global Service
 *
 * Runs on EVERY Odoo page (not just kiosk). Handles:
 * 1. Redirect to kiosk when pending acknowledgement documents exist
 */

import { registry } from "@web/core/registry";
import { session } from "@web/session";

const cbmGlobalService = {
    dependencies: ["rpc", "action"],

    start(env, { rpc, action }) {
        if (session.is_public || !session.uid) {
            return;
        }

        function isOnKiosk() {
            return window.location.hash.includes("action=clinic_staff_portal")
                || window.location.hash.includes("cbm_kiosk")
                || document.querySelector(".cbm_kiosk_container") !== null;
        }

        async function init() {
            try {
                const config = await rpc("/cbm/session/config", {});
                if (!config) return;

                if (config.has_pending_acknowledgements && !isOnKiosk()) {
                    action.doAction({
                        type: "ir.actions.client",
                        tag: "cbm_kiosk_action",
                        target: "main",
                    }, { clearBreadcrumbs: true });
                }
            } catch (e) {
                console.warn("[CBM Global] Failed to load session config", e);
            }
        }

        setTimeout(init, 1500);
    },
};

registry.category("services").add("cbm_global_service", cbmGlobalService);
