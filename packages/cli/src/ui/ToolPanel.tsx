/**
 * Tool panel — shows tool execution status and results.
 * Displays a spinner while running, collapses after completion.
 */

import React from 'react';
import { Box, Text } from 'ink';
import type { ToolPanel as ToolPanelData } from './store.js';

interface ToolPanelProps {
  panel: ToolPanelData;
  onToggle: () => void;
}

const SPINNER_FRAMES = ['|', '/', '-', '\\'];

export function ToolPanel({ panel, onToggle }: ToolPanelProps): React.ReactElement {
  const { name, status, result, collapsed } = panel;

  const statusIcon = status === 'running'
    ? <Spinner />
    : status === 'error'
      ? <Text color="red">x</Text>
      : <Text color="green">+</Text>;

  const statusColor = status === 'error' ? 'red' : status === 'done' ? 'green' : 'yellow';

  return (
    <Box flexDirection="column" marginLeft={2}>
      <Box>
        <Text>{statusIcon}</Text>
        <Text> </Text>
        <Text color={statusColor} bold>{name}</Text>
        {status !== 'running' && result && (
          <Text dimColor> [{collapsed ? 'show' : 'hide'}]</Text>
        )}
      </Box>
      {!collapsed && result && (
        <Box marginLeft={4}>
          <Text color={status === 'error' ? 'red' : undefined} dimColor={status !== 'error'}>
            {truncate(result, 500)}
          </Text>
        </Box>
      )}
    </Box>
  );
}

function Spinner(): React.ReactElement {
  const [frame, setFrame] = React.useState(0);

  React.useEffect(() => {
    const timer = setInterval(() => {
      setFrame((f) => (f + 1) % SPINNER_FRAMES.length);
    }, 100);
    return () => clearInterval(timer);
  }, []);

  return <Text color="yellow">{SPINNER_FRAMES[frame]}</Text>;
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + '...';
}
