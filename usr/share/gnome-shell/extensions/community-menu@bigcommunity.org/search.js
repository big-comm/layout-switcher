// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import Shell from 'gi://Shell';
import St from 'gi://St';

import {Highlighter} from 'resource:///org/gnome/shell/misc/util.js';
import * as IconGrid from 'resource:///org/gnome/shell/ui/iconGrid.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as ParentalControlsManager from 'resource:///org/gnome/shell/misc/parentalControlsManager.js';
import * as RemoteSearch from 'resource:///org/gnome/shell/ui/remoteSearch.js';
// import {Spinner} from 'resource:///org/gnome/shell/ui/animation.js';
import * as SystemActions from 'resource:///org/gnome/shell/misc/systemActions.js';
import {gettext as _, ngettext} from 'resource:///org/gnome/shell/extensions/extension.js';

import * as AppMenuItem from './widgets/appMenuItem.js';
import * as BaseMenuItem from './widgets/baseMenuItem.js';
import * as Constants from './constants.js';
import {OpenWindowSearchProvider} from './openWindowsSearchProvider.js';
import { SEARCH_EMITTER } from './extension.js'
import * as Utils from './utils.js';
import * as Widgets from './widgets/widgets.js';
import {getOrientationProp} from './utils.js';

const ListSearchResult = GObject.registerClass({
    Signals: {
        'activated': {},
    }
}, class ListSearchResult extends BaseMenuItem.BaseMenuItem {
    _init(provider, metaInfo, resultsView, compact = false) {
        super._init();
        this.useTooltip = !compact;

        this._iconSize = compact
            ? Constants.COMPACT_CATEGORY_ICON_SIZE
            : Constants.APP_LIST_ICON_SIZE;
        this.metaInfo = metaInfo;
        this.provider = provider;
        this.resultsView = resultsView;

        this._iconBin = new St.Bin({
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this.add_child(this._iconBin);
        this._updateIcon();

        St.TextureCache.get_default().connectObject(
            'icon-theme-changed', this._updateIcon.bind(this), this);

        this.label = new St.Label({
            text: this.metaInfo['name'],
            x_expand: true,
            y_expand: true,
            x_align: Clutter.ActorAlign.FILL,
            y_align: Clutter.ActorAlign.CENTER,
        });
        if (compact) {
            this.label.clutter_text.set({
                ellipsize: Pango.EllipsizeMode.END,
                single_line_mode: true,
            });
        }
        this.label_actor = this.label;

        if (this.metaInfo['description'] && !compact) {
            this.description = this.metaInfo['description'];
            const labelBox = new St.BoxLayout({
                style_class: 'community-list-search-result-labels',
                ...getOrientationProp(true),
                x_expand: true,
                x_align: Clutter.ActorAlign.FILL,
            });
            const descriptionText = this.metaInfo['description'].split('\n')[0];
            this.descriptionLabel = new St.Label({
                style_class: 'list-search-result-description',
                text: descriptionText,
                y_expand: true,
                y_align: Clutter.ActorAlign.CENTER,
            });
            labelBox.add_child(this.label);
            labelBox.add_child(this.descriptionLabel);
            this.add_child(labelBox);
        } else {
            this.add_child(this.label);
        }

        this.resultsView.connectObject('terms-changed', this._highlightTerms.bind(this), this);
        this._highlightTerms();
    }

    _updateIcon() {
        const icon = this.metaInfo['createIcon'](this._iconSize);
        if (icon) {
            icon.style_class = 'popup-menu-icon';
        }
        this._iconBin.set_child(icon);
    }

    animateLaunch() {
        IconGrid.zoomOutActor(this._iconBin);
    }

    // Activate menu item (Launch Search Result)
    activate(event) {
        if (this.metaInfo.id === 'open-screenshot-ui') {
            this.resultsView.screenshotActivated();
            return;
        }

        this.emit('activated');
        super.activate(event);

        if (this.provider.activateResult) {
            this.provider.activateResult(this.metaInfo.id, this.resultsView.terms);
            if (this.metaInfo.clipboardText)
                St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, this.metaInfo.clipboardText);
        } else if (this.metaInfo.id.endsWith('.desktop')) {
            const app = Shell.AppSystem.get_default().lookup_app(this.metaInfo.id);
            if (!app) {
                return;
            }

            if (app.can_open_new_window()) {
                this.animateLaunch();
                app.open_new_window(-1);
            } else {
                if (app.state == Shell.AppState.STOPPED) {
                    this.animateLaunch();
                }
                app.activate();
            }
        } else {
            const systemActions = SystemActions.getDefault();
            systemActions.activateAction(this.metaInfo.id);
        }
    }

    _highlightTerms() {
        if (this.descriptionLabel) {
            const descriptionMarkup = this.resultsView.highlightTerms(this.metaInfo['description'].split('\n')[0]);
            this.descriptionLabel.clutter_text.set_markup(descriptionMarkup);
        }
        const labelMarkup = this.resultsView.highlightTerms(this.label.text.split('\n')[0]);
        this.label.clutter_text.set_markup(labelMarkup);
    }
});

const AppSearchResult = GObject.registerClass({
}, class AppSearchResult extends AppMenuItem.AppMenuItem {
    _init(provider, metaInfo, resultsView, isGrid, compact = false) {
        this.metaInfo = metaInfo;
        this.provider = provider;
        this.resultsView = resultsView;

        const appSys = Shell.AppSystem.get_default();
        const app = appSys.lookup_app(this.metaInfo['id']) || appSys.lookup_app(this.provider.id);

        super._init(
            app,
            isGrid,
            compact ? Constants.COMPACT_CATEGORY_ICON_SIZE : Constants.APP_LIST_ICON_SIZE);
        if (compact) {
            this.useTooltip = false;
            this.description = null;
            this.label_actor.clutter_text.set({
                ellipsize: Pango.EllipsizeMode.END,
                single_line_mode: true,
            });
        }
        St.TextureCache.get_default().connectObject(
            'icon-theme-changed', this._updateIcon.bind(this), this);

        if (!this.app) {
            this.label_actor.set_text(this.metaInfo['name']);
            this.description = this.metaInfo['description'];
        }

        this.resultsView.connectObject('terms-changed', this._highlightTerms.bind(this), this);
        this._highlightTerms();
    }

    _updateIcon() {
        if (this.app) {
            super._updateIcon();
        } else {
            const icon = this.metaInfo['createIcon'](this._iconSize);
            if (icon) {
                icon.style_class = this._isGrid ? '' : 'popup-menu-icon';
            }
            this._iconBin.set_child(icon);
        }
    }

    _launchApp() {
        //Do nothing
    }

    // Activate menu item (Launch Search Result)
    activate(event) {
        if (this.metaInfo.id === 'open-screenshot-ui') {
            this.resultsView.screenshotActivated();
            return;
        }

        super.activate(event);

        if (this.provider.activateResult) {
            this.provider.activateResult(this.metaInfo.id, this.resultsView.terms);
            if (this.metaInfo.clipboardText)
                St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, this.metaInfo.clipboardText);
        } else if (this.app) {
            super._launchApp();
        } else {
            const systemActions = SystemActions.getDefault();
            systemActions.activateAction(this.metaInfo.id);
        }
    }

    _highlightTerms() {
        const labelMarkup = this.resultsView.highlightTerms(this.label_actor.text.split('\n')[0]);
        this.label_actor.clutter_text.set_markup(labelMarkup);
    }
});

const SearchResultsBase = GObject.registerClass({
    Signals: {
        'activated': {},
        'terms-changed': {},
        'no-results': {},
    }
}, class SearchResultsBase extends St.BoxLayout {
    _init(provider, resultsView) {
        super._init({
            ...getOrientationProp(true),
        });
        this.provider = provider;
        this._resultsView = resultsView;
        this._terms = [];

        this._resultDisplayBin = new St.Bin({
            x_expand: true,
            y_expand: false,
        });

        this.add_child(this._resultDisplayBin);

        this._resultDisplays = {};

        this._cancellable = new Gio.Cancellable();
        this.connect('destroy', () => this._onDestroy());
    }

    _onDestroy() {
        this._cancellable.cancel();
        this._cancellable = null;

        for (const resultId in this._resultDisplays) {
            if (Object.hasOwn(this._resultDisplays, resultId)) {
                this._resultDisplays[resultId].destroy();
                delete this._resultDisplays[resultId];
            }
        }
        this._resultDisplays = null;

        this._terms = [];
    }

    _createResultDisplay(_meta) {
    }

    clear() {
        this._cancellable.cancel();
        for (const resultId in this._resultDisplays) {
            if (Object.hasOwn(this._resultDisplays, resultId)) {
                this._resultDisplays[resultId].destroy();
                delete this._resultDisplays[resultId];
            }
        }
        this._resultDisplays = {};
        this._clearResultDisplay();
        this.hide();
    }

    _setMoreCount(_count) {
    }

    async _ensureResultActors(results) {
        const metasNeeded = results.filter(
            resultId => this._resultDisplays[resultId] === undefined
        );

        if (metasNeeded.length === 0)
            return;

        this._cancellable.cancel();
        const cancellable = new Gio.Cancellable();
        this._cancellable = cancellable;

        const metas = await this.provider.getResultMetas(metasNeeded, cancellable);

        if (cancellable.is_cancelled()) {
            if (metas.length > 0)
                throw new Error(`Search provider ${this.provider.id} returned results after the request was canceled`);
        }

        if (metas.length !== metasNeeded.length)
            throw new Error(`Wrong number of result metas returned by search provider ${this.provider.id}: expected ${metasNeeded.length} but got ${metas.length}`);


        if (metas.some(meta => !meta.name || !meta.id))
            throw new Error(`Invalid result meta returned from search provider ${this.provider.id}`);

        metasNeeded.forEach((resultId, i) => {
            const meta = metas[i];
            const display = this._createResultDisplay(meta);
            display.connect('activated', () => {
                this.emit('activated');
            });
            this._resultDisplays[resultId] = display;
        });
    }

    async updateSearch(providerResults, terms, callback) {
        this._terms = terms;
        if (providerResults.length === 0) {
            this._clearResultDisplay();
            this.hide();
            callback();
        } else {
            const maxResults = this._getMaxDisplayedResults();
            const results = maxResults > -1
                ? this.provider.filterResults(providerResults, maxResults)
                : providerResults;

            const moreCount = Math.max(providerResults.length - results.length, 0);

            try {
                await this._ensureResultActors(results);

                // To avoid CSS transitions causing flickering when
                // the first search result stays the same, we hide the
                // content while filling in the results.
                this.hide();
                this._clearResultDisplay();
                results.forEach(
                    resultId => this._addItem(this._resultDisplays[resultId]));
                this._setMoreCount(this.provider.canLaunchSearch ? moreCount : 0);
                this.show();
                callback();
            } catch (e) {
                this._clearResultDisplay();
                callback();
            }
        }
    }
});

const ListSearchResults = GObject.registerClass({
}, class ListSearchResults extends SearchResultsBase {
    _init(provider, resultsView, compact = false) {
        super._init(provider, resultsView);
        this._compact = compact;

        this._container = new St.BoxLayout({
            ...getOrientationProp(true),
            x_align: Clutter.ActorAlign.FILL,
            y_align: Clutter.ActorAlign.FILL,
            x_expand: true,
            y_expand: true,
            style: 'margin-top: 8px;',
        });

        this.providerInfo = new ProviderInfo(provider, compact);
        this.providerInfo.connect('activated', () => {
            this.emit('activated');
        });

        this._container.add_child(this.providerInfo);

        this._content = new St.BoxLayout({
            ...getOrientationProp(true),
            x_expand: true,
            y_expand: true,
            x_align: Clutter.ActorAlign.FILL,
        });

        this._container.add_child(this._content);
        this._resultDisplayBin.set_child(this._container);
    }

    async updateSearch(providerResults, terms, callback) {
        this.providerInfo.setTerms(terms);
        super.updateSearch(providerResults, terms, callback);
    }

    _setMoreCount(count) {
        this.providerInfo.setMoreCount(count);
    }

    _getMaxDisplayedResults() {
        return Constants.MAX_LIST_SEARCH_RESULTS_ROWS;
    }

    _clearResultDisplay() {
        this._content.remove_all_children();
    }

    _createResultDisplay(meta) {
        return new ListSearchResult(
            this.provider, meta, this._resultsView, this._compact);
    }

    _addItem(display) {
        if (display.get_parent())
            display.get_parent().remove_child(display);
        this._content.add_child(display);
    }

    getFirstResult() {
        if (this._content.get_n_children() > 0)
            return this._content.get_child_at_index(0)._delegate;
        else
            return null;
    }
});

const AppSearchResults = GObject.registerClass({
}, class AppSearchResults extends SearchResultsBase {
    _init(provider, resultsView, isGrid, compact = false) {
        super._init(provider, resultsView);
        this._compact = compact;

        if (isGrid) {
            this._grid = new Widgets.Grid(Constants.COLUMN_COUNT, Constants.COLUMN_SPACING, Constants.ROW_SPACING);
            this._resultDisplayBin.x_align = Clutter.ActorAlign.CENTER;
            this._resultDisplayBin.set_child(this._grid);
        } else {
            this._content = new St.BoxLayout({
                ...getOrientationProp(true),
                x_expand: true,
                y_expand: true,
                x_align: Clutter.ActorAlign.FILL,
            });
            this._resultDisplayBin.set_child(this._content);
        }
    }

    _getMaxDisplayedResults() {
        if (this._grid) {
            return Constants.COLUMN_COUNT;
        } else {
            return Constants.MAX_LIST_SEARCH_RESULTS_ROWS;
        }
    }

    _clearResultDisplay() {
        if (this._grid) {
            this._grid.clear();
        } else {
            this._content.remove_all_children();
        }
    }

    _createResultDisplay(meta) {
        return new AppSearchResult(
            this.provider, meta, this._resultsView, !!this._grid, this._compact);
    }

    _addItem(display) {
        if (display.get_parent())
            display.get_parent().remove_child(display);

        if (this._grid) {
            this._grid.add_item(display);
        } else {
            this._content.add_child(display);
        }
    }

    getFirstResult() {
        let item;
        if (this._grid) {
            item = this._grid.get_first_item();
        } else {
            item = this._content.get_child_at_index(0);
        }

        if (item)
            return item._delegate;
        else
            return null;
    }
});

export const SearchResults = GObject.registerClass({
    Signals: {
        'activated': {},
        'terms-changed': {},
        'have-results': {},
        'no-results': {},
        'screenshot-activated': {},
    }
}, class SearchResults extends St.BoxLayout {
    _init(isGrid, monitorIndex, compact = false) {
        super._init({
            ...getOrientationProp(true),
            y_expand: true,
            x_expand: true,
            x_align: Clutter.ActorAlign.FILL,
        });

        this._isGrid = isGrid;
        this._compact = compact;
        if (compact)
            this.add_style_class_name('compact-search-results');
        this._displayId = `display_community-menu_${monitorIndex}`;

        this._parentalControlsManager = ParentalControlsManager.getDefault();
        this._parentalControlsManager.connectObject('app-filter-changed', this._reloadRemoteProviders.bind(this), this);

        this._content = new St.BoxLayout({
            ...getOrientationProp(true),
            x_align: Clutter.ActorAlign.FILL,
        });

        this.add_child(this._content);

        this._statusContainer = new St.BoxLayout({
            style_class: 'search-statusbox',
            ...getOrientationProp(true),
            x_expand: true,
            y_expand: true,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });

        // TODO: Uncomment spinner code after theming support is re-enabled in GNOME Shell
        // this._statusSpinner = new Spinner(Constants.SEARCH_SPINNER_SIZE);

        this._statusText = new St.Label({style_class: 'search-statustext'});

        //this._statusContainer.add_child(this._statusSpinner);
        this._statusContainer.add_child(this._statusText);

        this.add_child(this._statusContainer);

        this._highlightDefault = false;
        this._defaultResult = null;
        this._startingSearch = false;

        this._terms = [];
        this._results = {};

        this._providers = [];

        this._highlighter = new Highlighter();

        this._searchSettings = new Gio.Settings({schema_id: Constants.SEARCH_PROVIDERS_SCHEMA});
        this._searchSettings.connectObject('changed::disabled', this._reloadRemoteProviders.bind(this), this);
        this._searchSettings.connectObject('changed::enabled', this._reloadRemoteProviders.bind(this), this);
        this._searchSettings.connectObject('changed::disable-external', this._reloadRemoteProviders.bind(this), this);
        this._searchSettings.connectObject('changed::sort-order', this._reloadRemoteProviders.bind(this), this);

        if (SEARCH_EMITTER) {
            SEARCH_EMITTER.connectObject('search-provider-added',
                (_s, provider) => this._registerProvider(provider), this);
            SEARCH_EMITTER.connectObject('search-provider-removed',
                (_s, provider) => this._unregisterProvider(provider), this);
        }

        this._searchTimeoutId = null;
        this._cancellable = new Gio.Cancellable();

        const appSys = Shell.AppSystem.get_default();
        appSys.connectObject('installed-changed', this._reloadRemoteProviders.bind(this), this);

        this._registerGnomeShellProviders();
        this._reloadRemoteProviders();

        this.connect('destroy', this._onDestroy.bind(this));
    }

    get terms() {
        return this._terms;
    }

    setStyle(style) {
        if (this._statusText)
            this._statusText.style_class = style;
    }

    _onDestroy() {
        this._cancellable.cancel();
        this._cancellable = null;

        SEARCH_EMITTER?.disconnectObject(this);

        this._parentalControlsManager.disconnectObject(this);
        this._searchSettings.disconnectObject(this);
        Shell.AppSystem.get_default().disconnectObject(this);

        this._clearSearchTimeout();

        this._terms = [];
        this._results = {};
        this._clearDisplay();
        this._defaultResult = null;
        this._startingSearch = false;

        this._providers.forEach(provider => {
            if (provider[this._displayId]) {
                provider[this._displayId].destroy();
                delete provider[this._displayId];
            }
        });
        this._providers = null;

        this._highlighter = null;
        this._searchSettings = null;
        this._parentalControlsManager = null;
    }

    _registerGnomeShellProviders() {
        const searchResults = Main.overview.searchController._searchResults;
        const providers = searchResults._providers.filter(p => !p.isRemoteProvider);
        providers.forEach(this._registerProvider.bind(this));

        this._registerProvider(new OpenWindowSearchProvider());
    }

    _reloadRemoteProviders() {
        const currentTerms = this._terms;
        // cancel any active search
        if (this._terms.length !== 0)
            this._reset();

        const remoteProviders = this._providers.filter(p => p.isRemoteProvider);
        remoteProviders.forEach(provider => {
            this._unregisterProvider(provider);
        });

        const providers = RemoteSearch.loadRemoteSearchProviders(this._searchSettings);
        providers.forEach(this._registerProvider.bind(this));

        // restart any active search
        if (currentTerms.length > 0)
            this.setTerms(currentTerms);
    }

    _registerProvider(provider) {
        provider.searchInProgress = false;

        // Filter out unwanted providers.
        if (provider.id !== 'community-menu.open-windows' && provider.appInfo && !this._parentalControlsManager.shouldShowApp(provider.appInfo))
            return;

        this._providers.push(provider);
        this._ensureProviderDisplay(provider);
    }

    _unregisterProvider(provider) {
        const index = this._providers.indexOf(provider);
        if (index === -1)
            return;
        this._providers.splice(index, 1);

        if (provider[this._displayId]) {
            provider[this._displayId].destroy();
            delete provider[this._displayId];
        }
    }

    _clearSearchTimeout() {
        if (this._searchTimeoutId !== null) {
            GLib.source_remove(this._searchTimeoutId);
            this._searchTimeoutId = null;
        }
    }

    async _doProviderSearch(provider, previousResults) {
        provider.searchInProgress = true;

        const terms = this._terms;

        let results;
        try {
            if (this._isSubSearch && previousResults) {
                results = await provider.getSubsearchResultSet(
                    previousResults,
                    terms,
                    this._cancellable);
            } else {
                results = await provider.getInitialResultSet(
                    terms,
                    this._cancellable);
            }
        } catch (e) {
            logError(e);
        }

        // Discard results if search is stale
        if (this._cancellable?.is_cancelled() || terms !== this._terms)
            return;

        if (results === undefined)
            results = [];

        this._results[provider.id] = results;
        this._updateResults(provider, results);
    }

    _reset() {
        this._terms = [];
        this._results = {};
        this._clearDisplay();
        this._clearSearchTimeout();
        this._defaultResult = null;
        this._startingSearch = false;

        this._updateSearchProgress();
    }

    _doSearch() {
        this._startingSearch = false;

        const previousResults = this._results;
        this._results = {};

        this._providers.forEach(provider => {
            const previousProviderResults = previousResults[provider.id];
            this._doProviderSearch(provider, previousProviderResults)
                .catch(logError);
        });

        this._updateSearchProgress();

        this._clearSearchTimeout();
    }

    _onSearchTimeout() {
        this._searchTimeoutId = null;
        this._doSearch();
        return GLib.SOURCE_REMOVE;
    }

    setTerms(terms) {
        // Check for the case of making a duplicate previous search before
        // setting state of the current search or cancelling the search.
        // This will prevent incorrect state being as a result of a duplicate
        // search while the previous search is still active.
        const searchString = terms.join(' ');
        const previousSearchString = this._terms.join(' ');
        if (searchString === previousSearchString)
            return;

        this._startingSearch = true;

        this._cancellable.cancel();
        this._cancellable = new Gio.Cancellable();

        if (terms.length === 0) {
            this._reset();
            return;
        }

        let isSubSearch = false;
        if (this._terms.length > 0)
            isSubSearch = searchString.indexOf(previousSearchString) === 0;

        this._terms = terms;
        this._isSubSearch = isSubSearch;
        this._updateSearchProgress();

        if (this._searchTimeoutId === null)
            this._searchTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 150, this._onSearchTimeout.bind(this));

        this._highlighter = new Highlighter(this._terms);

        this.emit('terms-changed');
    }

    _ensureProviderDisplay(provider) {
        if (provider[this._displayId])
            return;

        let providerDisplay;
        if (provider.appInfo)
            providerDisplay = new ListSearchResults(provider, this, this._compact);
        else
            providerDisplay = new AppSearchResults(
                provider, this, this._isGrid, this._compact);

        providerDisplay.connect('activated', () => {
            this.emit('activated');
        });
        providerDisplay.hide();
        this._content.add_child(providerDisplay);
        provider[this._displayId] = providerDisplay;
    }

    _clearDisplay() {
        this._providers.forEach(provider => {
            provider[this._displayId]?.clear();
        });
    }

    _maybeSetInitialSelection() {
        let newDefaultResult = null;

        const providers = this._providers;
        for (let i = 0; i < providers.length; i++) {
            const provider = providers[i];
            const display = provider[this._displayId];

            if (!display.visible)
                continue;

            const firstResult = display.getFirstResult();
            if (firstResult) {
                newDefaultResult = firstResult;
                break; // select this one!
            }
        }

        if (newDefaultResult !== this._defaultResult) {
            this._setSelected(this._defaultResult, false);
            this._setSelected(newDefaultResult, this._highlightDefault);

            this._defaultResult = newDefaultResult;
        }
    }

    get searchInProgress() {
        if (this._startingSearch)
            return true;

        return this._providers.some(p => p.searchInProgress);
    }

    _updateSearchProgress() {
        const haveResults = this._providers.some(provider => {
            const display = provider[this._displayId];
            return display.getFirstResult() !== null;
        });

        this._statusContainer.visible = !haveResults;
        if (haveResults) {
            this.emit('have-results');
        } else if (!haveResults) {
            if (this.searchInProgress) {
                // this._statusSpinner.play();
                this._statusText.set_text(_('Searching…'));
            } else {
                // this._statusSpinner.stop();
                this._statusText.set_text(_('No results.'));
            }

            this.emit('no-results');
        }
    }

    _updateResults(provider, results) {
        const terms = this._terms;
        const display = provider[this._displayId];
        display.updateSearch(results, terms, () => {
            provider.searchInProgress = false;

            this._maybeSetInitialSelection();
            this._updateSearchProgress();
        });
    }

    activateDefault() {
        // If we have a search queued up, force the search now.
        if (this._searchTimeoutId !== null)
            this._doSearch();

        if (this._defaultResult)
            this._defaultResult.activate(null);
    }

    highlightDefault(highlight) {
        this._highlightDefault = highlight;
        this._setSelected(this._defaultResult, highlight);
    }

    popupMenuDefault() {
        // If we have a search queued up, force the search now.
        if (this._searchTimeoutId !== null)
            this._doSearch();

        if (this._defaultResult)
            this._defaultResult.popup_menu();
    }

    getTopResult() {
        return this._defaultResult;
    }

    _setSelected(result, selected) {
        if (!result)
            return;

        if (selected && !result.has_style_pseudo_class('focus')) {
            result.add_style_pseudo_class('focus');
            Utils.ensureActorVisibleInScrollView(this);
        } else if (!selected) {
            result.remove_style_pseudo_class('focus');
        }
    }

    hasActiveResult() {
        return !!this._defaultResult && this._highlightDefault;
    }

    highlightTerms(description) {
        if (!description)
            return '';

        return this._highlighter.highlight(description);
    }

    screenshotActivated() {
        this.emit('screenshot-activated');
    }
});

const ProviderInfo = GObject.registerClass({
    Signals: {
        'activated': {},
    }
}, class ProviderInfo extends BaseMenuItem.BaseMenuItem {
    _init(provider, compact = false) {
        this.provider = provider;
        this._terms = [];
        super._init();
        this.useTooltip = !compact;
        this._appInfo = provider.appInfo;
        this.x_expand = false;
        this.x_align = Clutter.ActorAlign.START;

        this.description = compact
            ? null
            : this._appInfo.get_description?.() ?? null;

        this.label = new St.Label({
            text: this._appInfo.get_name(),
            x_align: Clutter.ActorAlign.START,
            y_align: Clutter.ActorAlign.CENTER,
            style: 'font-weight: bold;',
        });
        if (compact) {
            this.label.clutter_text.set({
                ellipsize: Pango.EllipsizeMode.END,
                single_line_mode: true,
            });
        }
        this.label_actor = this.label;

        this._moreLabel = new St.Label({
            x_align: Clutter.ActorAlign.END,
            y_align: Clutter.ActorAlign.CENTER,
        });

        this.add_child(this.label);
        this.add_child(this._moreLabel);
    }

    setTerms(terms) {
        this._terms = terms;
    }

    animateLaunch() {
        let appSys = Shell.AppSystem.get_default();
        let app = appSys.lookup_app(this.provider.appInfo.get_id());
        if (app.state == Shell.AppState.STOPPED)
            IconGrid.zoomOutActor(this);
    }

    activate(event) {
        if (this.provider.canLaunchSearch) {
            this.animateLaunch();
            this.provider.launchSearch(this._terms);
            this.emit('activated');
            super.activate(event);
        }
    }

    setMoreCount(count) {
        this._moreLabel.text = ngettext('+ %d more', '+ %d more', count).format(count);
        this._moreLabel.visible = count > 0;
    }
});
