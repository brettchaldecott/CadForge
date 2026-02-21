/**
 * Task tool — subagent delegation.
 * explore/plan run in Node; cad delegates to Python SSE.
 */

import { EventType, getDefaultSubagentModel } from '@cadforge/shared';
import type { CadForgeSettings, AgentEvent, CadSubagentRequest, CadSubagentProviderConfig } from '@cadforge/shared';
import type { LLMProvider, EventCallback } from '../llm/provider.js';
import type { BackendClient } from '../backend/client.js';
import { SubagentExecutor } from '../agent/subagent.js';

export type AgentType = 'explore' | 'plan' | 'cad';

export interface TaskDeps {
  provider: LLMProvider;
  settings: CadForgeSettings;
  projectRoot: string;
  backendClient?: BackendClient;
  onEvent?: EventCallback;
}

function makeEvent(type: EventType, data: Record<string, unknown>): AgentEvent {
  return { type, data, timestamp: new Date().toISOString() };
}

/**
 * Handle a Task tool call — dispatches to local or SSE subagents.
 */
export async function handleTask(
  input: Record<string, unknown>,
  deps: TaskDeps,
): Promise<Record<string, unknown>> {
  const agentType = input.agent_type as string;
  const prompt = input.prompt as string;
  const context = (input.context as string) ?? '';

  // Validate
  if (!['explore', 'plan', 'cad'].includes(agentType)) {
    return { success: false, error: `Invalid agent_type: ${agentType}. Must be explore, plan, or cad.` };
  }
  if (!prompt || prompt.trim() === '') {
    return { success: false, error: 'Task prompt cannot be empty.' };
  }

  const emit = deps.onEvent ?? (() => {});

  // Local subagents (explore, plan)
  if (agentType === 'explore' || agentType === 'plan') {
    emit(makeEvent(EventType.STATUS, { message: `Starting ${agentType} subagent...` }));

    const result = await SubagentExecutor.runLocal(
      agentType,
      prompt,
      context,
      deps.provider,
      deps.settings,
      deps.projectRoot,
      deps.backendClient,
    );

    return {
      success: result.success,
      agent: result.agentName,
      output: result.output,
      ...(result.error ? { error: result.error } : {}),
    };
  }

  // CAD subagent — delegate to Python via SSE
  if (agentType === 'cad') {
    if (!deps.backendClient) {
      return { success: false, error: 'Python backend not available for CAD subagent.' };
    }

    // Build provider_config from generic credential info
    const credInfo = deps.provider.getCredentialInfo();
    const providerConfig: CadSubagentProviderConfig = {
      provider: credInfo.provider,
      api_key: credInfo.apiKey,
      auth_token: credInfo.authToken,
      base_url: credInfo.baseUrl,
      aws_region: credInfo.awsRegion,
      aws_profile: credInfo.awsProfile,
    };

    const cadModel = deps.settings.subagentModels.cad
      ?? getDefaultSubagentModel(deps.settings.provider, 'cad');

    const req: CadSubagentRequest = {
      prompt,
      context,
      project_root: deps.projectRoot,
      provider_config: providerConfig,
      model: cadModel,
    };

    emit(makeEvent(EventType.STATUS, { message: 'Starting CAD subagent...' }));

    const result = await deps.backendClient.streamCadSubagent(req, (sseEvent) => {
      // Forward CAD tool events to the UI so the user can see them
      if (sseEvent.event === 'tool_use_start') {
        emit(makeEvent(EventType.TOOL_USE_START, sseEvent.data));
      } else if (sseEvent.event === 'tool_result') {
        emit(makeEvent(EventType.TOOL_RESULT, sseEvent.data));
      } else if (sseEvent.event === 'status') {
        const msg = sseEvent.data.message as string ?? '';
        emit(makeEvent(EventType.STATUS, { message: `[cad] ${msg}` }));
      }
    });

    return {
      success: result.success,
      agent: 'cad',
      output: result.output,
      ...(result.error ? { error: result.error } : {}),
    };
  }

  return { success: false, error: `Unhandled agent type: ${agentType}` };
}
