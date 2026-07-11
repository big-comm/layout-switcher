// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
import GLib from 'gi://GLib';

export const TOOLTIP_TIMEOUT = 500;
export const APP_LIST_ICON_SIZE = 32;
export const APP_GRID_ICON_SIZE = 48;

export const TooltipLocation = {
    TOP_CENTERED: 0,
    BOTTOM_CENTERED: 1,
    BOTTOM: 2,
};

export const MENU_BUTTON_ICON_SIZE = 36;

export const DASH_TO_PANEL_UUID = 'dash-to-panel@jderose9.github.com';

export const SEARCH_PROVIDERS_SCHEMA = 'org.gnome.desktop.search-providers';
export const MAX_LIST_SEARCH_RESULTS_ROWS = 5;
export const SEARCH_SPINNER_SIZE = 32;

export const COLUMN_SPACING = 16;
export const ROW_SPACING = 16;
export const COLUMN_COUNT = 6;

export const SCROLL_ANIMATION_DURATION = 100;

// User Home directories
export const DEFAULT_DIRECTORIES = [
    GLib.UserDirectory.DIRECTORY_DESKTOP,
    GLib.UserDirectory.DIRECTORY_DOCUMENTS,
    GLib.UserDirectory.DIRECTORY_DOWNLOAD,
    GLib.UserDirectory.DIRECTORY_MUSIC,
    GLib.UserDirectory.DIRECTORY_PICTURES,
    GLib.UserDirectory.DIRECTORY_VIDEOS
];

// Menu Layout Enum
export const LAYOUTS = {
    ALL: 0,
    APPS_ONLY: 1,
    SYSTEM_ONLY: 2,
    APP_GRID: 3,
    MINT: 4
};

export const APPS_ONLY_MENU_HEIGHT = 542;
export const GRID_MENU_HEIGHT = 600;
export const AVAIL_HEIGHT_PADDING = 24;
export const INTELLIHIDE_TIMEOUT = 750;

export const MUTTER_SCHEMA = 'org.gnome.mutter';

export const CaretPosition = {
    END: -1,
    START: 0,
    MIDDLE: 2,
};
