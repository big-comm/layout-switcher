// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
import {EventEmitter} from 'resource:///org/gnome/shell/misc/signals.js';
import {InjectionManager} from 'resource:///org/gnome/shell/extensions/extension.js';
import {SearchController} from 'resource:///org/gnome/shell/ui/searchController.js';

/**
 * Override SearchController addProvider() and removeProvider() methods to emit signals
 * when called. Allows Community Menu to use custom search providers registered by extensions.
 */

export class SearchProviderEmitter extends EventEmitter {
    constructor() {
        super();

        this._injectionManager = new InjectionManager();

        this._injectionManager.overrideMethod(SearchController.prototype, 'addProvider', originalMethod => {
            const searchProviderEmitter = this;
            return function (provider) {
                /* eslint-disable-next-line no-invalid-this */
                originalMethod.call(this, provider);
                searchProviderEmitter.emit('search-provider-added', provider);
            };
        });

        this._injectionManager.overrideMethod(SearchController.prototype, 'removeProvider', originalMethod => {
            const searchProviderEmitter = this;
            return function (provider) {
                /* eslint-disable-next-line no-invalid-this */
                originalMethod.call(this, provider);
                searchProviderEmitter.emit('search-provider-removed', provider);
            };
        });
    }

    destroy() {
        this._injectionManager.clear();
        this._injectionManager = null;
    }
}
