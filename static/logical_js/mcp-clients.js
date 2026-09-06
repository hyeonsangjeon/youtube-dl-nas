(function(root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.YDLNAS_MCP_CLIENTS = api;
    }
})(typeof window !== 'undefined' ? window : globalThis, function() {
    const clients = {
        codex: {
            location: '~/.codex/config.toml',
            docs: 'https://developers.openai.com/codex/mcp/',
            hintKey: 'connect.config_env_hint'
        },
        'claude-code': {
            location: '.mcp.json',
            docs: 'https://code.claude.com/docs/en/mcp',
            hintKey: 'connect.config_env_hint'
        },
        vscode: {
            location: '.vscode/mcp.json',
            docs: 'https://code.visualstudio.com/docs/agents/reference/mcp-configuration',
            hintKey: 'connect.config_vscode_hint'
        },
        cursor: {
            location: '~/.cursor/mcp.json',
            docs: 'https://cursor.com/docs/mcp',
            hintKey: 'connect.config_env_hint'
        },
        gemini: {
            location: '~/.gemini/settings.json',
            docs: 'https://geminicli.com/docs/tools/mcp-server/',
            hintKey: 'connect.config_env_hint'
        },
        opencode: {
            location: '~/.config/opencode/opencode.json',
            docs: 'https://opencode.ai/docs/mcp-servers/',
            hintKey: 'connect.config_env_hint'
        }
    };

    function setup(client, endpoint, tokenPromptLabel) {
        if (!Object.hasOwn(clients, client)) {
            throw new TypeError('Unknown MCP client');
        }
        const parsed = new URL(endpoint);
        if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password ||
            parsed.pathname !== '/youtube-dl/mcp' || parsed.search || parsed.hash) {
            throw new TypeError('Expected an HTTP(S) MCP endpoint without credentials or query parameters');
        }
        const url = parsed.href;
        let configuration;
        let config;
        if (client === 'codex') {
            config = '[mcp_servers.youtube-dl-nas]\nurl = ' + JSON.stringify(url) +
                '\nbearer_token_env_var = "YDLNAS_MCP_TOKEN"';
        } else if (client === 'vscode') {
            configuration = {
                servers: {
                    'youtube-dl-nas': {
                        type: 'http', url,
                        headers: { Authorization: 'Bearer ${input:ydlnasToken}' }
                    }
                },
                inputs: [{
                    id: 'ydlnasToken', type: 'promptString',
                    description: tokenPromptLabel || 'youtube-dl-nas MCP token', password: true
                }]
            };
        } else if (client === 'opencode') {
            configuration = {
                $schema: 'https://opencode.ai/config.json',
                mcp: {
                    'youtube-dl-nas': {
                        type: 'remote', url, enabled: true, oauth: false,
                        headers: { Authorization: 'Bearer {env:YDLNAS_MCP_TOKEN}' }
                    }
                }
            };
        } else {
            const server = client === 'gemini' ? { httpUrl: url } : { url };
            if (client === 'claude-code') { server.type = 'http'; }
            server.headers = {
                Authorization: client === 'cursor' ? 'Bearer ${env:YDLNAS_MCP_TOKEN}' : 'Bearer ${YDLNAS_MCP_TOKEN}'
            };
            configuration = { mcpServers: { 'youtube-dl-nas': server } };
        }
        return Object.assign({}, clients[client], { config: config || JSON.stringify(configuration, null, 2) });
    }

    return { setup, clientIds: Object.keys(clients) };
});
