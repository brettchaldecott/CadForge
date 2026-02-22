/**
 * Task tool — subagent delegation.
 * explore/plan run in Node; cad delegates to Python SSE.
 */

import { EventType, makeEvent, getDefaultSubagentModel } from '@cadforge/shared';
import type { CadForgeSettings, CadSubagentRequest, DesignPipelineRequest, CadSubagentProviderConfig, ExecuteDesignRequest, CompetitivePipelineRequest } from '@cadforge/shared';
import type { LLMProvider, EventCallback } from '../llm/provider.js';
import type { BackendClient } from '../backend/client.js';
import { SubagentExecutor } from '../agent/subagent.js';

export type AgentType = 'explore' | 'plan' | 'cad' | 'design' | 'competitive';

export interface TaskDeps {
  provider: LLMProvider;
  settings: CadForgeSettings;
  projectRoot: string;
  backendClient?: BackendClient;
  onEvent?: EventCallback;
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
  if (!['explore', 'plan', 'cad', 'design', 'competitive'].includes(agentType)) {
    return { success: false, error: `Invalid agent_type: ${agentType}. Must be explore, plan, cad, design, or competitive.` };
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

  // Design pipeline — delegate to Python via SSE
  if (agentType === 'design') {
    if (!deps.backendClient) {
      return { success: false, error: 'Python backend not available for design pipeline.' };
    }

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

    const designId = input.design_id as string | undefined;

    const handleDesignSSE = (sseEvent: import('@cadforge/shared').SSEEvent) => {
      if (sseEvent.event === 'pipeline_step') {
        const step = sseEvent.data.step as string ?? '';
        const msg = sseEvent.data.message as string ?? '';
        emit(makeEvent(EventType.STATUS, { message: `[design:${step}] ${msg}` }));
      } else if (sseEvent.event === 'pipeline_round') {
        const round = sseEvent.data.round as number ?? 0;
        const max = sseEvent.data.max_rounds as number ?? 3;
        emit(makeEvent(EventType.STATUS, { message: `[design] Round ${round}/${max}` }));
      } else if (sseEvent.event === 'tool_use_start') {
        emit(makeEvent(EventType.TOOL_USE_START, sseEvent.data));
      } else if (sseEvent.event === 'tool_result') {
        emit(makeEvent(EventType.TOOL_RESULT, sseEvent.data));
      } else if (sseEvent.event === 'pipeline_image') {
        emit(makeEvent(EventType.STATUS, { message: `[design] Rendered: ${sseEvent.data.path}` }));
      } else if (sseEvent.event === 'pipeline_verdict') {
        const verdict = sseEvent.data.verdict as string ?? '';
        emit(makeEvent(EventType.STATUS, { message: `[design:judge] ${verdict}` }));
      } else if (sseEvent.event === 'design_updated') {
        emit(makeEvent(EventType.DESIGN_UPDATED, sseEvent.data));
      } else if (sseEvent.event === 'iteration_saved') {
        emit(makeEvent(EventType.ITERATION_SAVED, sseEvent.data));
      } else if (sseEvent.event === 'learnings_indexed') {
        emit(makeEvent(EventType.LEARNINGS_INDEXED, sseEvent.data));
      }
    };

    // Tracked design workflow: resume existing or create → approve → execute
    if (designId) {
      emit(makeEvent(EventType.STATUS, { message: `Resuming design ${designId}...` }));
      const execReq: ExecuteDesignRequest = {
        provider_config: providerConfig,
        model: cadModel,
      };
      const result = await deps.backendClient.streamDesignResume(
        designId, execReq, deps.projectRoot, handleDesignSSE,
      );
      return {
        success: result.success,
        agent: 'design',
        design_id: designId,
        output: result.output,
        ...(result.error ? { error: result.error } : {}),
      };
    }

    // New tracked design: create from context (spec), approve, execute
    if (context) {
      emit(makeEvent(EventType.STATUS, { message: 'Creating tracked design...' }));
      const design = await deps.backendClient.createDesign({
        title: prompt,
        prompt,
        specification: context,
        project_root: deps.projectRoot,
      });
      await deps.backendClient.approveDesign(design.id, deps.projectRoot);
      emit(makeEvent(EventType.DESIGN_UPDATED, { id: design.id, status: 'approved' }));

      const execReq: ExecuteDesignRequest = {
        provider_config: providerConfig,
        model: cadModel,
      };
      const result = await deps.backendClient.streamDesignExecution(
        design.id, execReq, deps.projectRoot, handleDesignSSE,
      );
      return {
        success: result.success,
        agent: 'design',
        design_id: design.id,
        output: result.output,
        ...(result.error ? { error: result.error } : {}),
      };
    }

    // Fallback: fire-and-forget pipeline (no spec context)
    const req: DesignPipelineRequest = {
      prompt,
      project_root: deps.projectRoot,
      provider_config: providerConfig,
      model: cadModel,
    };

    emit(makeEvent(EventType.STATUS, { message: 'Starting design pipeline...' }));

    const result = await deps.backendClient.streamDesignPipeline(req, handleDesignSSE);

    return {
      success: result.success,
      agent: 'design',
      output: result.output,
      ...(result.error ? { error: result.error } : {}),
    };
  }

  // Competitive pipeline — delegate to Python via SSE
  if (agentType === 'competitive') {
    if (!deps.backendClient) {
      return { success: false, error: 'Python backend not available for competitive pipeline.' };
    }

    const pipelineConfig = deps.settings.competitivePipeline ?? {};

    const req: CompetitivePipelineRequest = {
      prompt,
      project_root: deps.projectRoot,
      specification: context || undefined,
      pipeline_config: pipelineConfig as unknown as Record<string, unknown>,
    };

    const handleCompetitiveSSE = (sseEvent: import('@cadforge/shared').SSEEvent) => {
      if (sseEvent.event === 'competitive_status') {
        const status = sseEvent.data.status as string ?? '';
        emit(makeEvent(EventType.COMPETITIVE_STATUS, sseEvent.data));
        emit(makeEvent(EventType.STATUS, { message: `[competitive] ${status}` }));
      } else if (sseEvent.event === 'competitive_round') {
        const round = sseEvent.data.round as number ?? 0;
        const max = sseEvent.data.max_rounds as number ?? 3;
        emit(makeEvent(EventType.COMPETITIVE_ROUND, sseEvent.data));
        emit(makeEvent(EventType.STATUS, { message: `[competitive] Round ${round}/${max}` }));
      } else if (sseEvent.event === 'competitive_supervisor') {
        emit(makeEvent(EventType.COMPETITIVE_SUPERVISOR, sseEvent.data));
        emit(makeEvent(EventType.STATUS, { message: `[competitive:supervisor] ${sseEvent.data.status}` }));
      } else if (sseEvent.event === 'competitive_proposal') {
        emit(makeEvent(EventType.COMPETITIVE_PROPOSAL, sseEvent.data));
        const model = sseEvent.data.model as string ?? '';
        const status = sseEvent.data.status as string ?? '';
        emit(makeEvent(EventType.STATUS, { message: `[competitive:proposal] ${model}: ${status}` }));
      } else if (sseEvent.event === 'competitive_debate') {
        emit(makeEvent(EventType.COMPETITIVE_DEBATE, sseEvent.data));
        emit(makeEvent(EventType.STATUS, { message: `[competitive:debate] ${sseEvent.data.status}` }));
      } else if (sseEvent.event === 'competitive_sandbox') {
        emit(makeEvent(EventType.COMPETITIVE_SANDBOX, sseEvent.data));
      } else if (sseEvent.event === 'competitive_fidelity') {
        emit(makeEvent(EventType.COMPETITIVE_FIDELITY, sseEvent.data));
        const score = sseEvent.data.score as number ?? 0;
        emit(makeEvent(EventType.STATUS, { message: `[competitive:fidelity] Score: ${score}` }));
      } else if (sseEvent.event === 'competitive_merger') {
        emit(makeEvent(EventType.COMPETITIVE_MERGER, sseEvent.data));
        emit(makeEvent(EventType.STATUS, { message: `[competitive:merger] ${sseEvent.data.status}` }));
      } else if (sseEvent.event === 'competitive_learning') {
        emit(makeEvent(EventType.COMPETITIVE_LEARNING, sseEvent.data));
      } else if (sseEvent.event === 'competitive_approval_requested') {
        emit(makeEvent(EventType.COMPETITIVE_APPROVAL_REQUESTED, sseEvent.data));
        emit(makeEvent(EventType.STATUS, { message: '[competitive] Awaiting human approval...' }));
      } else if (sseEvent.event === 'completion') {
        // Forward completion
      }
    };

    emit(makeEvent(EventType.STATUS, { message: 'Starting competitive pipeline...' }));

    const result = await deps.backendClient.streamCompetitivePipeline(req, handleCompetitiveSSE);

    return {
      success: result.success,
      agent: 'competitive',
      output: result.output,
      ...(result.error ? { error: result.error } : {}),
    };
  }

  return { success: false, error: `Unhandled agent type: ${agentType}` };
}
