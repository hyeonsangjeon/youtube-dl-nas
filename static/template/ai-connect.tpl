<!--
THESIS: Connect a client without turning NAS setup into infrastructure work.
OWN-WORLD: The dashboard's restrained teal, bordered controls, and compact library rows.
STORY: Name a connection, copy its one-time token, configure a client, revoke it when finished.
FIRST VIEWPORT: Connection setup on the left; the approval workflow and access boundary on the right.
FORM: An inline settings workspace within the existing application shell.
-->
<main id="main-content" class="workspace-main" tabindex="-1">
    <div id="workspace-message" class="workspace-message" role="status" aria-live="polite" hidden></div>
    <header class="workspace-heading">
        <div>
            <h2>{{t('connect.heading')}}</h2>
            <p>{{t('connect.description')}}</p>
        </div>
        <span id="mcp-service-status" class="connection-chip status-pending" role="status">{{t('connect.checking')}}</span>
    </header>

    <div class="connect-layout">
        <div class="connect-main">
            <section class="panel" aria-labelledby="connect-new-heading">
                <div class="workspace-section-heading">
                    <div>
                        <h3 id="connect-new-heading">{{t('connect.new_connection')}}</h3>
                        <p>{{t('connect.new_hint')}}</p>
                    </div>
                </div>
                <form id="connection-form" class="connection-form">
                    <label class="form-field">
                        <span>{{t('connect.connection_name')}}</span>
                        <input id="connection-name" class="form-control admin-control" type="text" maxlength="120" required autocomplete="off" placeholder="{{t('connect.name_placeholder')}}">
                    </label>
                    <button type="submit" class="workspace-button workspace-primary">{{t('connect.create')}}</button>
                </form>
                <section id="connection-secret" class="connection-secret" aria-labelledby="connection-secret-heading" hidden>
                    <h4 id="connection-secret-heading">{{t('connect.token_once')}}</h4>
                    <p>{{t('connect.token_once_hint')}}</p>
                    <div class="copy-field">
                        <label class="sr-only" for="connection-token">{{t('connect.token')}}</label>
                        <input id="connection-token" type="password" readonly autocomplete="off" spellcheck="false">
                        <button id="toggle-token" class="workspace-button" type="button" aria-pressed="false">{{t('connect.reveal')}}</button>
                        <button id="copy-token" class="workspace-button" type="button">{{t('workspace.copy')}}</button>
                    </div>
                    <button id="dismiss-token" class="workspace-button" type="button">{{t('connect.saved_token')}}</button>
                </section>
            </section>

            <section class="panel" aria-labelledby="connect-setup-heading">
                <div class="workspace-section-heading">
                    <div>
                        <h3 id="connect-setup-heading">{{t('connect.setup')}}</h3>
                        <p>{{t('connect.setup_hint')}}</p>
                    </div>
                </div>
                <label class="form-field" for="mcp-endpoint">{{t('connect.endpoint')}}</label>
                <div class="copy-field">
                    <input id="mcp-endpoint" type="text" readonly spellcheck="false">
                    <button id="copy-endpoint" class="workspace-button" type="button">{{t('workspace.copy')}}</button>
                </div>
                <div id="connect-http-warning" class="workspace-notice" hidden>{{t('connect.http_warning')}}</div>
                <label class="form-field client-select-label" for="mcp-client">{{t('connect.client')}}</label>
                <select id="mcp-client" class="form-control admin-control">
                    <option value="codex">Codex</option>
                    <option value="claude-code">Claude Code</option>
                    <option value="vscode">GitHub Copilot / VS Code</option>
                    <option value="cursor">Cursor</option>
                    <option value="gemini">Gemini CLI</option>
                    <option value="opencode">OpenCode</option>
                </select>
                <div class="client-config-heading">
                    <span id="client-config-location" class="workspace-help"></span>
                    <button id="copy-client-config" class="workspace-button" type="button">{{t('connect.copy_setup')}}</button>
                </div>
                <pre class="client-config"><code id="client-config"></code></pre>
                <p id="client-config-hint" class="workspace-help"></p>
                <a id="client-docs" class="workspace-text-link" target="_blank" rel="noopener noreferrer">{{t('connect.official_docs')}} <span aria-hidden="true">&nearr;</span></a>
            </section>

            <section class="panel" aria-labelledby="connections-heading">
                <div class="workspace-section-heading">
                    <h3 id="connections-heading">{{t('connect.connections')}}</h3>
                    <button id="workspace-refresh" class="workspace-button" type="button">{{t('history.refresh')}}</button>
                </div>
                <div id="connections-loading" class="workspace-loading" role="status">
                    <span class="sr-only">{{t('workspace.loading')}}</span>
                    <span></span><span></span>
                </div>
                <div id="connection-list"></div>
            </section>
        </div>

        <aside class="connect-guide" aria-labelledby="connect-workflow-heading">
            <h3 id="connect-workflow-heading">{{t('connect.workflow')}}</h3>
            <ol class="connect-workflow">
                <li><strong>{{t('connect.research')}}</strong><p>{{t('connect.research_hint')}}</p></li>
                <li><strong>{{t('connect.review')}}</strong><p>{{t('connect.review_hint')}}</p></li>
                <li><strong>{{t('connect.approve')}}</strong><p>{{t('connect.approve_hint')}}</p></li>
            </ol>
            <div class="connect-prompt">
                <h4>{{t('connect.try_prompt')}}</h4>
                <p id="research-prompt">{{t('connect.example_prompt')}}</p>
                <button id="copy-prompt" class="workspace-button" type="button">{{t('workspace.copy')}}</button>
            </div>
            <div class="connect-boundary">
                <h4>{{t('connect.access_heading')}}</h4>
                <p>{{t('connect.access_hint')}}</p>
                <p>{{t('connect.no_delete')}}</p>
                <a href="/youtube-dl/collections">{{t('connect.open_collections')}} <span aria-hidden="true">&rarr;</span></a>
            </div>
        </aside>
    </div>
</main>
