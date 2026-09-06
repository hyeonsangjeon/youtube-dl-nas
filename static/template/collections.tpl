<!--
THESIS: A topic is a working library, not another download history.
OWN-WORLD: Existing teal actions, cool neutral panels, system type, and media controls.
STORY: Inspect a collection, preview a bounded set of URLs, approve once, follow the batch.
FIRST VIEWPORT: Purpose and actions above a searchable library; folder and date policy stay visible.
FORM: A task-first extension of the existing dashboard, not a replacement visual identity.
-->
<main id="main-content" class="workspace-main" tabindex="-1">
    <div id="workspace-message" class="workspace-message" role="status" aria-live="polite" hidden></div>
    % if collection_id:
    <a class="workspace-back" href="/youtube-dl/collections">
        <span aria-hidden="true">&larr;</span> {{t('collections.back')}}
    </a>
    % end
    <header class="workspace-heading">
        <div>
            <h2 id="collections-heading">{{t('collections.heading')}}</h2>
            <p id="collections-description">{{t('collections.description')}}</p>
        </div>
        <div class="workspace-actions">
            <button id="workspace-refresh" class="workspace-button" type="button">{{t('history.refresh')}}</button>
            <button id="open-batch-composer" class="workspace-button workspace-primary" type="button" aria-controls="batch-composer" aria-expanded="false">{{t('collections.collect_urls')}}</button>
        </div>
    </header>

    <section id="collection-summary" class="panel collection-summary" hidden>
        <dl class="collection-facts">
            <div><dt>{{t('collections.items')}}</dt><dd id="collection-item-count"></dd></div>
            <div><dt>{{t('collections.stored_size')}}</dt><dd id="collection-stored-size"></dd></div>
            <div><dt>{{t('collections.updated')}}</dt><dd id="collection-updated"></dd></div>
            <div><dt>{{t('collections.date_policy')}}</dt><dd id="collection-date-policy"></dd></div>
        </dl>
        <div class="collection-folder">
            <span>{{t('collections.folder')}}</span>
            <code id="collection-folder"></code>
            <p>{{t('collections.folder_hint')}}</p>
        </div>
        <details id="collection-edit" class="workspace-disclosure">
            <summary>{{t('collections.edit')}}</summary>
            <form id="collection-edit-form" class="workspace-form">
                <label class="form-field" for="collection-edit-name">{{t('collections.name')}}</label>
                <input id="collection-edit-name" class="form-control admin-control" type="text" maxlength="120" required>
                <label class="form-field" for="collection-edit-description">{{t('collections.purpose')}}</label>
                <textarea id="collection-edit-description" class="form-control" rows="3" maxlength="2000"></textarea>
                <div class="workspace-actions">
                    <button type="submit" class="workspace-button workspace-primary">{{t('workspace.save_changes')}}</button>
                    <button id="remove-collection" type="button" class="workspace-button workspace-danger">{{t('collections.remove')}}</button>
                </div>
                <p class="workspace-help">{{t('collections.metadata_only')}}</p>
            </form>
        </details>
    </section>

    <section id="batch-composer" class="panel batch-composer" aria-labelledby="batch-heading" hidden>
        <div class="workspace-section-heading">
            <div>
                <h3 id="batch-heading">{{t('batch.heading')}}</h3>
                <p id="batch-description-copy">{{t('batch.description')}}</p>
            </div>
            <button id="close-batch-composer" class="workspace-button" type="button">{{t('common.close')}}</button>
        </div>
        <form id="batch-form" class="workspace-form">
            <div class="workspace-form-grid">
                <label class="form-field">
                    <span>{{t('collections.name')}}</span>
                    <input id="batch-name" class="form-control admin-control" type="text" maxlength="120" required placeholder="{{t('batch.name_placeholder')}}">
                </label>
                <label class="form-field">
                    <span>{{t('composer.quality')}}</span>
                    <select id="batch-resolution" class="form-control admin-control">
                        <option value="best">{{t('composer.share_best')}}</option>
                        <option value="compatible-mp4">{{t('composer.compatible_mp4_short')}}</option>
                        <option value="1080p">1080p</option>
                        <option value="720p">720p</option>
                        <option value="audio-mp3">MP3</option>
                        <option value="audio-m4a">M4A</option>
                        <option value="audio-opus">Opus</option>
                    </select>
                </label>
            </div>
            <label class="form-field">
                <span>{{t('collections.purpose')}}</span>
                <input id="batch-description" class="form-control admin-control" type="text" maxlength="2000" placeholder="{{t('batch.purpose_placeholder')}}">
            </label>
            <div class="workspace-form-grid">
                <label class="form-field">
                    <span>{{t('batch.date_from')}}</span>
                    <input id="batch-date-from" class="form-control admin-control" type="date">
                </label>
                <label class="form-field">
                    <span>{{t('batch.date_to')}}</span>
                    <input id="batch-date-to" class="form-control admin-control" type="date">
                </label>
            </div>
            <label class="form-field">
                <span>{{t('batch.urls')}}</span>
                <textarea id="batch-urls" class="form-control batch-urls" rows="5" required aria-describedby="batch-limit-hint" placeholder="https://www.youtube.com/watch?v=..."></textarea>
            </label>
            <p id="batch-limit-hint" class="workspace-help">{{t('batch.urls_hint', count=25)}}</p>
            <div class="workspace-actions">
                <button type="submit" id="batch-preview-button" class="workspace-button workspace-primary">{{t('batch.preview')}}</button>
                <span class="workspace-help">{{t('batch.preview_safe')}}</span>
            </div>
        </form>
        <div id="batch-plan" class="batch-plan" hidden>
            <div class="workspace-section-heading">
                <p id="batch-plan-expiry"></p>
                <button id="batch-start-over" type="button" class="workspace-button">{{t('batch.edit_candidates')}}</button>
            </div>
            <p class="workspace-help">{{t('batch.date_warning')}}</p>
            <div id="batch-plan-items" class="batch-plan-items"></div>
            <label class="form-field batch-destination">
                <span>{{t('batch.destination')}}</span>
                <select id="batch-destination" class="form-control admin-control" aria-describedby="batch-destination-caption"></select>
            </label>
            <p id="batch-destination-caption" class="workspace-help batch-destination-caption" role="status"></p>
            <div class="workspace-actions batch-commit-actions">
                <button id="batch-commit" type="button" class="workspace-button workspace-primary">{{t('batch.approve')}}</button>
                <span id="batch-selection-count" class="workspace-help" role="status"></span>
            </div>
        </div>
    </section>

    <section id="collection-batches" class="panel" aria-labelledby="collection-batches-heading" hidden>
        <div class="workspace-section-heading">
            <h3 id="collection-batches-heading">{{t('collections.batch_activity')}}</h3>
            <span class="workspace-help">{{t('collections.live_hint')}}</span>
        </div>
        <div id="collection-batch-list"></div>
    </section>

    <section class="panel collection-library" aria-labelledby="collection-library-heading">
        <div class="workspace-section-heading">
            <h3 id="collection-library-heading">{{t('collections.library')}}</h3>
            <span id="collection-result-count" class="workspace-help" role="status"></span>
        </div>
        <div class="collection-toolbar">
            <label class="workspace-search">
                <span class="sr-only">{{t('collections.search')}}</span>
                <input id="collection-search" class="form-control admin-control" type="search" placeholder="{{t('collections.search')}}">
            </label>
            <div id="collection-view-switch" class="history-view-switch" role="group" aria-label="{{t('history.view_label')}}" hidden>
                <button type="button" class="history-view-btn is-active" data-collection-view="list" aria-pressed="true">{{t('history.list')}}</button>
                <button type="button" class="history-view-btn" data-collection-view="grid" aria-pressed="false">{{t('history.grid')}}</button>
            </div>
        </div>
        <div id="collection-loading" class="workspace-loading" role="status">
            <span class="sr-only">{{t('workspace.loading')}}</span>
            <span></span><span></span><span></span>
        </div>
        <div id="collection-list"></div>
        <div id="collection-items" class="collection-media-list"></div>
        <div id="collection-pager" class="history-pager"></div>
    </section>
    <p class="collection-footnote">{{t('collections.preservation_hint')}}</p>
</main>
