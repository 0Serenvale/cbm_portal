/** @odoo-module */

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

/**
 * Inventory Warning Banner Component
 *
 * Displays a warning banner when inventory is scheduled to start within 7 days.
 * Shown on the CBM Portal dashboard above the tile grid.
 *
 * Features:
 * - Fetches active inventory configuration via RPC
 * - Calculates days until inventory start
 * - Displays banner only if start_date is within 7 days
 * - Shows announcement text and countdown
 * - Color-coded urgency (red/orange/yellow)
 * - Dismissible banner
 * - Dark mode support
 */
export class InventoryBanner extends Component {
    static template = "clinic_staff_portal.InventoryBanner";
    static props = {
        // Optional: callback when banner is dismissed
        onDismiss: { type: Function, optional: true },
    };

    setup() {
        this.rpc = useService("rpc");

        this.state = useState({
            show: false,
            config: null,
            daysUntilStart: null,
            announcement: null,
            loading: true,
        });

        onWillStart(async () => {
            await this.fetchConfiguration();
        });
    }

    /**
     * Fetch active inventory configuration from server
     */
    async fetchConfiguration() {
        try {
            const config = await this.rpc("/cbm/inventory/config");

            if (!config || !config.id) {
                // No active config found (expected if not yet scheduled)
                this.state.loading = false;
                return;
            }

            const daysUntil = this.calculateDaysUntil(config.inventory_start_date);

            // Show banner only if within 7 days
            if (daysUntil <= 7 && daysUntil >= 0) {
                this.state.show = true;
                this.state.config = config;
                this.state.daysUntilStart = daysUntil;
                // Use generated announcement, fall back to custom text if empty
                this.state.announcement = config.generated_announcement || config.announcement_text;
            }
        } catch (error) {
            console.error("[InventoryBanner] RPC error fetching configuration:", error);
            // Log unexpected errors but don't break page (banner just won't show)
        } finally {
            this.state.loading = false;
        }
    }

    /**
     * Calculate days between today and target date
     * @param {string} dateStr - ISO date string (YYYY-MM-DD)
     * @returns {number} Days until date (negative if in past)
     */
    calculateDaysUntil(dateStr) {
        // Parse date string in local timezone (not UTC)
        const [year, month, day] = dateStr.split('-').map(Number);
        const target = new Date(year, month - 1, day);
        target.setHours(0, 0, 0, 0);

        const now = new Date();
        now.setHours(0, 0, 0, 0);

        const diffTime = target - now;
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

        return diffDays;
    }

    /**
     * Format announcement with countdown
     */
    getAnnouncementWithCountdown() {
        let text = this.state.announcement || "";

        if (this.state.daysUntilStart !== null) {
            const daysText = this.state.daysUntilStart === 1
                ? _t("1 day")
                : _t("%s days", this.state.daysUntilStart);

            text = `[${daysText}] ${text}`;
        }

        return text;
    }

    /**
     * Dismiss banner
     */
    onDismissBanner() {
        this.state.show = false;
        if (this.props.onDismiss) {
            this.props.onDismiss();
        }
    }

    /**
     * CSS class based on urgency level
     */
    getBannerClass() {
        let classes = "inventory-warning-banner";

        if (this.state.daysUntilStart !== null) {
            if (this.state.daysUntilStart <= 1) {
                classes += " urgency-critical";  // Red: starts today/tomorrow
            } else if (this.state.daysUntilStart <= 3) {
                classes += " urgency-high";      // Orange: starts in 2-3 days
            } else {
                classes += " urgency-normal";    // Yellow: starts in 4-7 days
            }
        }

        return classes;
    }
}
