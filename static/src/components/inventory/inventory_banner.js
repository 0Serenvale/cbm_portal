/** @odoo-module */

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

/**
 * Inventory Warning Banner Component
 *
 * Displays a warning banner on the CBM Portal dashboard when inventory is
 * scheduled within 7 days OR currently in progress.
 *
 * Visibility rules:
 * - Shows 7 days before inventory_start_date
 * - Stays visible until inventory_end_date has passed
 * - Dismissible per browser session (close button hides it, comes back on reload)
 * - Available to ALL authenticated users (not just managers)
 *
 * Color-coded urgency:
 * - Red (critical): starts today/tomorrow or already in progress
 * - Orange (high): starts in 2-3 days
 * - Yellow (normal): starts in 4-7 days
 */
export class InventoryBanner extends Component {
    static template = "clinic_staff_portal.InventoryBanner";
    static props = {
        onDismiss: { type: Function, optional: true },
    };

    setup() {
        this.rpc = useService("rpc");

        this.state = useState({
            show: false,
            config: null,
            daysUntilStart: null,
            daysUntilEnd: null,
            announcement: null,
            loading: true,
        });

        onWillStart(async () => {
            await this.fetchConfiguration();
        });
    }

    async fetchConfiguration() {
        try {
            const config = await this.rpc("/cbm/inventory/config");

            if (!config || !config.id) {
                this.state.loading = false;
                return;
            }

            const daysUntilStart = this.calculateDaysUntil(config.inventory_start_date);
            const daysUntilEnd = this.calculateDaysUntil(config.inventory_end_date);

            // Show banner if:
            // - Within 7 days before start (daysUntilStart <= 7 && daysUntilStart >= 0)
            // - OR inventory is in progress (daysUntilStart < 0 && daysUntilEnd >= 0)
            if (daysUntilStart <= 7 && daysUntilEnd >= 0) {
                this.state.show = true;
                this.state.config = config;
                this.state.daysUntilStart = daysUntilStart;
                this.state.daysUntilEnd = daysUntilEnd;
                this.state.announcement = config.generated_announcement;
            }
        } catch (error) {
            console.error("[InventoryBanner] Error fetching config:", error);
        } finally {
            this.state.loading = false;
        }
    }

    /**
     * Calculate days between today and target date
     * @param {string} dateStr - YYYY-MM-DD
     * @returns {number} positive = future, 0 = today, negative = past
     */
    calculateDaysUntil(dateStr) {
        const [year, month, day] = dateStr.split('-').map(Number);
        const target = new Date(year, month - 1, day);
        target.setHours(0, 0, 0, 0);

        const now = new Date();
        now.setHours(0, 0, 0, 0);

        return Math.ceil((target - now) / (1000 * 60 * 60 * 24));
    }

    getUrgencyLabel() {
        if (this.state.daysUntilStart === null) return "";
        if (this.state.daysUntilStart < 0)  return _t("EN COURS");
        if (this.state.daysUntilStart === 0) return _t("AUJOURD'HUI");
        if (this.state.daysUntilStart === 1) return _t("DEMAIN");
        return _t("Dans %s jours", this.state.daysUntilStart);
    }

    getAnnouncementText() {
        return this.state.announcement || "";
    }

    // Keep for backwards compatibility
    getAnnouncementWithCountdown() {
        const label = this.getUrgencyLabel();
        const text = this.getAnnouncementText();
        return label ? `[${label}] ${text}` : text;
    }

    onDismissBanner() {
        this.state.show = false;
        if (this.props.onDismiss) {
            this.props.onDismiss();
        }
    }

    getBannerClass() {
        let classes = "inventory-warning-banner";

        if (this.state.daysUntilStart !== null) {
            if (this.state.daysUntilStart <= 1) {
                classes += " urgency-critical";
            } else if (this.state.daysUntilStart <= 3) {
                classes += " urgency-high";
            } else {
                classes += " urgency-normal";
            }
        }

        return classes;
    }
}
