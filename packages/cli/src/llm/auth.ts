/**
 * Authentication for CadForge.
 *
 * Supports three auth methods in priority order:
 * 1. ANTHROPIC_API_KEY environment variable (standard API key)
 * 2. ANTHROPIC_AUTH_TOKEN environment variable (OAuth token)
 * 3. Claude Code OAuth credentials from macOS Keychain (automatic)
 */

import { execSync } from 'node:child_process';

const OAUTH_CLIENT_ID = '9d1c250a-e61b-44d9-88ed-5944d1962f5e';
const OAUTH_TOKEN_URL = 'https://console.anthropic.com/v1/oauth/token';
const OAUTH_BETA_HEADER = 'oauth-2025-04-20';
const TOKEN_REFRESH_BUFFER_MS = 600_000; // 10 minutes

export interface AuthCredentials {
  apiKey: string | null;
  authToken: string | null;
  refreshToken: string | null;
  expiresAt: number | null;
  source: 'api_key' | 'env_token' | 'claude_code' | 'ollama' | 'none';
}

export function createEmptyCredentials(source: AuthCredentials['source'] = 'none'): AuthCredentials {
  return { apiKey: null, authToken: null, refreshToken: null, expiresAt: null, source };
}

export function isValid(creds: AuthCredentials): boolean {
  return creds.apiKey !== null || creds.authToken !== null;
}

export function needsRefresh(creds: AuthCredentials): boolean {
  if (creds.expiresAt === null || creds.refreshToken === null) return false;
  return Date.now() >= creds.expiresAt - TOKEN_REFRESH_BUFFER_MS;
}

/**
 * Resolve authentication credentials.
 * Priority: API key -> env token -> macOS Keychain
 */
export function resolveAuth(): AuthCredentials {
  // 1. API key
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (apiKey) {
    return { ...createEmptyCredentials('api_key'), apiKey };
  }

  // 2. Explicit auth token
  const authToken = process.env.ANTHROPIC_AUTH_TOKEN;
  if (authToken) {
    return { ...createEmptyCredentials('env_token'), authToken };
  }

  // 3. Claude Code OAuth from macOS Keychain
  const keychainCreds = readClaudeCodeKeychain();
  if (keychainCreds) return keychainCreds;

  return createEmptyCredentials('none');
}

function readClaudeCodeKeychain(): AuthCredentials | null {
  try {
    const username = process.env.USER ?? '';
    const result = execSync(
      `security find-generic-password -s "Claude Code-credentials" -a "${username}" -w`,
      { timeout: 5000, encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] },
    );

    const data = JSON.parse(result.trim());
    const oauth = data.claudeAiOauth;
    if (!oauth) return null;

    return {
      apiKey: null,
      authToken: oauth.accessToken ?? null,
      refreshToken: oauth.refreshToken ?? null,
      expiresAt: oauth.expiresAt ?? null,
      source: 'claude_code',
    };
  } catch {
    return null;
  }
}

/**
 * Refresh an expired OAuth access token.
 */
export async function refreshOAuthToken(creds: AuthCredentials): Promise<AuthCredentials> {
  if (!creds.refreshToken) return creds;

  try {
    const body = new URLSearchParams({
      grant_type: 'refresh_token',
      client_id: OAUTH_CLIENT_ID,
      refresh_token: creds.refreshToken,
    });

    const response = await fetch(OAUTH_TOKEN_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
      signal: AbortSignal.timeout(15_000),
    });

    if (!response.ok) return creds;

    const data = (await response.json()) as Record<string, unknown>;
    const newCreds: AuthCredentials = {
      apiKey: null,
      authToken: (data.access_token as string) ?? creds.authToken,
      refreshToken: (data.refresh_token as string) ?? creds.refreshToken,
      expiresAt: Date.now() + ((data.expires_in as number) ?? 28800) * 1000,
      source: creds.source,
    };

    if (creds.source === 'claude_code') {
      updateClaudeCodeKeychain(newCreds);
    }

    return newCreds;
  } catch {
    return creds;
  }
}

function updateClaudeCodeKeychain(creds: AuthCredentials): void {
  try {
    const username = process.env.USER ?? '';
    const existing = execSync(
      `security find-generic-password -s "Claude Code-credentials" -a "${username}" -w`,
      { timeout: 5000, encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] },
    );

    const data = JSON.parse(existing.trim());
    const oauth = data.claudeAiOauth ?? {};
    oauth.accessToken = creds.authToken;
    if (creds.refreshToken) oauth.refreshToken = creds.refreshToken;
    if (creds.expiresAt) oauth.expiresAt = creds.expiresAt;
    data.claudeAiOauth = oauth;

    const newValue = JSON.stringify(data);
    execSync(
      `security delete-generic-password -s "Claude Code-credentials" -a "${username}"`,
      { timeout: 5000, stdio: 'pipe' },
    );
    execSync(
      `security add-generic-password -s "Claude Code-credentials" -a "${username}" -w '${newValue.replace(/'/g, "'\\''")}'`,
      { timeout: 5000, stdio: 'pipe' },
    );
  } catch {
    // Non-critical — token still works in memory
  }
}

/**
 * Build Anthropic client options from resolved credentials.
 */
export function buildClientOptions(creds: AuthCredentials): Record<string, unknown> {
  const opts: Record<string, unknown> = {};
  if (creds.apiKey) {
    opts.apiKey = creds.apiKey;
  } else if (creds.authToken) {
    opts.authToken = creds.authToken;
    opts.defaultHeaders = { 'anthropic-beta': OAUTH_BETA_HEADER };
  }
  return opts;
}

/**
 * Resolve credentials per provider type.
 */
export function resolveAuthForProvider(
  provider: import('@cadforge/shared').ProviderType,
  providerConfig: import('@cadforge/shared').ProviderConfig,
): AuthCredentials {
  switch (provider) {
    case 'anthropic': {
      // Check provider_config.apiKey first, then fall through to standard chain
      if (providerConfig.apiKey) {
        return { ...createEmptyCredentials('api_key'), apiKey: providerConfig.apiKey };
      }
      return resolveAuth();
    }
    case 'openai': {
      const key = providerConfig.apiKey ?? process.env.OPENAI_API_KEY ?? null;
      return { ...createEmptyCredentials(key ? 'api_key' : 'none'), apiKey: key };
    }
    case 'ollama':
      return createEmptyCredentials('ollama');
    case 'bedrock':
      // AWS SDK uses its own credential chain (env vars, profiles, instance roles)
      return createEmptyCredentials('none');
    case 'litellm':
      // LiteLLM reads API keys from environment variables based on model prefix
      return createEmptyCredentials('none');
  }
}

