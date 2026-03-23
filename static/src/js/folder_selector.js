/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * POS-style Folder Selector Client Action
 * Shows child tiles as large clickable buttons in fullscreen
 */
class FolderSelectorAction extends Component {
    static template = "clinic_staff_portal.FolderSelectorAction";
    
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        
        this.state = useState({
            folderName: "",
            tiles: [],
            loading: true,
        });
        
        onWillStart(async () => {
            await this.loadTiles();
        });
    }
    
    async loadTiles() {
        const folderId = this.props.action.context?.active_id;
        const folderName = this.props.action.context?.folder_name || "Select Option";
        
        if (folderId) {
            const tiles = await this.orm.searchRead(
                "clinic.portal.tile",
                [["parent_id", "=", folderId], ["active", "=", true]],
                ["id", "name", "icon", "type", "stock_behavior"]
            );
            this.state.tiles = tiles;
        }
        
        this.state.folderName = folderName;
        this.state.loading = false;
    }
    
    async onTileClick(tile) {
        // Call the tile's action_open_tile method
        const result = await this.orm.call(
            "clinic.portal.tile",
            "action_open_tile",
            [[tile.id]]
        );
        
        if (result) {
            this.action.doAction(result);
        }
    }
    
    onBackClick() {
        // Return to dashboard
        this.action.doAction("clinic_staff_portal.action_clinic_portal_dashboard", {
            clearBreadcrumbs: true,
        });
    }
}

registry.category("actions").add("folder_selector_action", FolderSelectorAction);
