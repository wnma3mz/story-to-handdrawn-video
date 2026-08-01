import {isAbsolute, resolve} from 'node:path';

export const resolveWorkspace = (args, projectRoot) => {
  const selected =
    args.workspace || process.env.STORY_VIDEO_WORKSPACE || projectRoot;
  if (typeof selected !== 'string') {
    throw new Error('--workspace requires a directory path');
  }
  return resolve(selected);
};

export const resolveWorkspacePath = (workspace, value, fallback) => {
  const selected = value === undefined || value === null || value === ''
    ? fallback
    : String(value);
  return isAbsolute(selected) ? resolve(selected) : resolve(workspace, selected);
};

export const workspaceArgs = (workspace, extra = []) => [
  '--workspace',
  workspace,
  ...extra,
];
