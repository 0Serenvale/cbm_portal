/** @odoo-module **/
/**
 * AccountabilityDashboard Component - Extracted from CBMKiosk
 * Shows pending internal transfers by department with escalation to DRH.
 */

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class AccountabilityDashboard extends Component {
    static template = "clinic_staff_portal.AccountabilityDashboard";

    setup() {
        this.rpc = useService("rpc");

        this.state = useState({
            loading: true,
            departments: [],
            totalAtRisk: 0,
            pendingCount: 0,
            currencySymbol: 'DA',
            successMessage: '',
        });

        this.loadData();
    }

    async loadData() {
        try {
            this.state.loading = true;
            const result = await this.rpc("/cbm/financial_details", {});
            this.state.departments = result.departments || [];

            // Compute summary from departments
            let total = 0;
            let count = 0;
            for (const dept of this.state.departments) {
                total += dept.loss_amount || 0;
                count += dept.pending_count || 0;
            }
            this.state.totalAtRisk = total;
            this.state.pendingCount = count;
            if (this.state.departments.length > 0) {
                this.state.currencySymbol = this.state.departments[0].currency_symbol || 'DA';
            }
        } catch (error) {
            console.error("[ACCOUNTABILITY] Failed to load data", error);
        }
        this.state.loading = false;
    }

    async notifyDRH(pickingIds) {
        try {
            const result = await this.rpc("/cbm/notify_drh", { picking_ids: pickingIds });
            if (result.success) {
                this.state.successMessage = result.message;
                setTimeout(() => { this.state.successMessage = ""; }, 3000);
            } else {
                if (this.props.showToast) {
                    this.props.showToast(result.message, 'danger');
                }
            }
        } catch (error) {
            console.error("[ACCOUNTABILITY] Failed to notify DRH", error);
            if (this.props.showToast) {
                this.props.showToast(_t("Erreur lors de l'envoi de la notification"), 'danger');
            }
        }
    }

    goHome() {
        this.props.onNavigateHome();
    }
}

AccountabilityDashboard.props = {
    onNavigateHome: Function,
    showToast: { type: Function, optional: true },
};
