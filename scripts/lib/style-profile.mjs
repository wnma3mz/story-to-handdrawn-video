import {existsSync, readFileSync} from 'node:fs';
import {isAbsolute, relative, resolve, sep} from 'node:path';

const TOP_LEVEL_KEYS = new Set([
  'schema_version',
  'id',
  'display_name',
  'description',
  'base_mode',
  'recommended_for',
  'style_overrides',
  'episode_defaults',
  'editorial',
]);

const EPISODE_DEFAULT_KEYS = new Set(['accent', 'color_grade', 'cover']);
const REQUIRED_EPISODE_DEFAULT_KEYS = new Set(['accent', 'cover']);
const COVER_KEYS = new Set([
  'series_title',
  'episode_label',
  'episode_number',
  'title',
  'background',
  'accent',
  'dark_accent',
  'badge',
  'card',
  'foreground',
]);
const COVER_COLOR_KEYS = new Set([
  'background',
  'accent',
  'dark_accent',
  'badge',
  'card',
  'foreground',
]);
const PROFILE_ID = /^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$/;
const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/;

const isPlainObject = (value) =>
  value !== null &&
  typeof value === 'object' &&
  !Array.isArray(value) &&
  (Object.getPrototypeOf(value) === Object.prototype ||
    Object.getPrototypeOf(value) === null);

const assertPlainObject = (value, label) => {
  if (!isPlainObject(value)) {
    throw new Error(`${label} must be a JSON object`);
  }
};

const assertNonEmptyString = (value, label) => {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`${label} must be a non-empty string`);
  }
};

const assertKnownKeys = (value, allowed, label) => {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) {
      throw new Error(`${label} contains unknown key ${JSON.stringify(key)}`);
    }
  }
};

export const validateStyleProfile = (profile, styles) => {
  assertPlainObject(profile, 'style profile');
  assertKnownKeys(profile, TOP_LEVEL_KEYS, 'style profile');

  for (const field of TOP_LEVEL_KEYS) {
    if (!Object.hasOwn(profile, field)) {
      throw new Error(`style profile is missing required field ${JSON.stringify(field)}`);
    }
  }

  if (profile.schema_version !== 1) {
    throw new Error('style profile schema_version must be 1');
  }
  assertNonEmptyString(profile.id, 'style profile id');
  if (!PROFILE_ID.test(profile.id)) {
    throw new Error(
      'style profile id must use lowercase letters, numbers, dots, underscores, or hyphens',
    );
  }
  assertNonEmptyString(profile.display_name, 'style profile display_name');
  assertNonEmptyString(profile.description, 'style profile description');
  assertNonEmptyString(profile.base_mode, 'style profile base_mode');
  const availableModes = Object.entries(styles)
    .filter(([, value]) => isPlainObject(value))
    .map(([key]) => key);
  if (
    !Object.hasOwn(styles, profile.base_mode) ||
    !isPlainObject(styles[profile.base_mode])
  ) {
    throw new Error(
      `style profile base_mode must be one of ${availableModes.join(', ')}`,
    );
  }

  if (
    !Array.isArray(profile.recommended_for) ||
    profile.recommended_for.length === 0 ||
    profile.recommended_for.some((value) => typeof value !== 'string' || !value.trim())
  ) {
    throw new Error('style profile recommended_for must be a non-empty string array');
  }
  assertPlainObject(profile.style_overrides, 'style profile style_overrides');
  assertPlainObject(profile.episode_defaults, 'style profile episode_defaults');
  assertPlainObject(profile.editorial, 'style profile editorial');
  assertKnownKeys(
    profile.episode_defaults,
    EPISODE_DEFAULT_KEYS,
    'style profile episode_defaults',
  );

  for (const field of REQUIRED_EPISODE_DEFAULT_KEYS) {
    if (!Object.hasOwn(profile.episode_defaults, field)) {
      throw new Error(
        `style profile episode_defaults is missing required field ${JSON.stringify(field)}`,
      );
    }
  }
  if (
    typeof profile.episode_defaults.accent !== 'string' ||
    !HEX_COLOR.test(profile.episode_defaults.accent)
  ) {
    throw new Error('style profile episode_defaults.accent must be #RRGGBB');
  }
  if (
    profile.episode_defaults.color_grade !== undefined &&
    !['monochrome', 'warm_bronze', 'snow_cinnabar'].includes(
      profile.episode_defaults.color_grade,
    )
  ) {
    throw new Error(
      'style profile episode_defaults.color_grade must be monochrome, warm_bronze, or snow_cinnabar',
    );
  }

  const cover = profile.episode_defaults.cover;
  assertPlainObject(cover, 'style profile episode_defaults.cover');
  assertKnownKeys(cover, COVER_KEYS, 'style profile episode_defaults.cover');
  for (const [key, value] of Object.entries(cover)) {
    if (typeof value !== 'string' || !value.trim()) {
      throw new Error(
        `style profile episode_defaults.cover.${key} must be a non-empty string`,
      );
    }
    if (COVER_COLOR_KEYS.has(key) && !HEX_COLOR.test(value)) {
      throw new Error(
        `style profile episode_defaults.cover.${key} must be #RRGGBB`,
      );
    }
  }
  return profile;
};

export const deepMerge = (base, overrides) => {
  if (!isPlainObject(base) || !isPlainObject(overrides)) {
    return structuredClone(overrides);
  }
  const merged = structuredClone(base);
  for (const [key, value] of Object.entries(overrides)) {
    if (key === '__proto__' || key === 'prototype' || key === 'constructor') {
      throw new Error(`style_overrides contains forbidden key ${JSON.stringify(key)}`);
    }
    merged[key] =
      isPlainObject(value) && isPlainObject(merged[key])
        ? deepMerge(merged[key], value)
        : structuredClone(value);
  }
  return merged;
};

const looksLikePath = (reference) =>
  isAbsolute(reference) ||
  reference.endsWith('.json') ||
  reference.includes('/') ||
  reference.includes('\\');

const tracePath = (root, absolutePath) => {
  const rel = relative(root, absolutePath);
  if (rel && rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel)) {
    return rel.split(sep).join('/');
  }
  return absolutePath;
};

export const loadStyleProfile = (reference, {root, styles}) => {
  if (typeof reference !== 'string' || !reference.trim()) {
    throw new Error('--style-profile requires a profile id or JSON path');
  }
  const normalized = reference.trim();
  const absolutePath = looksLikePath(normalized)
    ? resolve(root, normalized)
    : resolve(root, 'config/style-profiles', `${normalized}.json`);
  if (!existsSync(absolutePath)) {
    throw new Error(`Style profile not found: ${absolutePath}`);
  }

  let profile;
  try {
    profile = JSON.parse(readFileSync(absolutePath, 'utf8'));
  } catch (error) {
    throw new Error(`Invalid style profile JSON at ${absolutePath}: ${error.message}`);
  }
  validateStyleProfile(profile, styles);
  if (!looksLikePath(normalized) && profile.id !== normalized) {
    throw new Error(
      `Style profile id ${JSON.stringify(profile.id)} does not match requested id ${JSON.stringify(normalized)}`,
    );
  }

  return {
    profile,
    absolutePath,
    trace: {
      id: profile.id,
      path: tracePath(root, absolutePath),
      schema_version: profile.schema_version,
    },
  };
};
