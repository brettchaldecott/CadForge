---
name: commit
description: Create a git commit with a descriptive message
allowed-tools: "Bash, ReadFile, ListFiles"
---

When asked to commit changes:
1. Run `git status` to see all changes
2. Run `git diff --staged` to see staged changes
3. If nothing is staged, stage relevant files with `git add`
4. Draft a concise commit message that describes the changes
5. Create the commit with the drafted message
6. Show the commit result
