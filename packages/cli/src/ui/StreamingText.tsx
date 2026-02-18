/**
 * Streaming text display — renders LLM output as it arrives.
 */

import React from 'react';
import { Box, Text } from 'ink';

interface StreamingTextProps {
  text: string;
}

export function StreamingText({ text }: StreamingTextProps): React.ReactElement | null {
  if (!text) return null;

  return (
    <Box marginLeft={2}>
      <Text>{text}</Text>
      <Text color="cyan">{'_'}</Text>
    </Box>
  );
}
