import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import type {ThumbnailAsset, ThumbnailConceptProps} from './thumbnail/types';

type ThumbnailConceptFile = ThumbnailConceptProps & {
  outputPath?: string;
};

const rendererRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const projectRoot = path.resolve(rendererRoot, '..', '..');
const publicDir = path.join(rendererRoot, 'public');

const argPath = process.argv.find((arg) => arg.endsWith('.json'));
if (!argPath) {
  throw new Error('Usage: npm run render:thumbnail -- /absolute/path/to/concept.json');
}

const readJson = async <T>(filePath: string): Promise<T> => {
  return JSON.parse(await fs.readFile(filePath, 'utf-8')) as T;
};

const writeJson = async (filePath: string, value: unknown) => {
  await fs.writeFile(filePath, JSON.stringify(value, null, 2) + '\n', 'utf-8');
};

const exists = async (filePath: string): Promise<boolean> => {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
};

const sanitize = (value: string): string => value.replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^_+|_+$/g, '') || 'asset';

const isRemote = (value: string): boolean => /^https?:\/\//i.test(value);

const publicPathFor = (absolutePath: string): string | null => {
  const relative = path.relative(publicDir, absolutePath);
  if (!relative.startsWith('..') && !path.isAbsolute(relative)) {
    return relative.split(path.sep).join('/');
  }
  return null;
};

const resolveInput = async (value: string): Promise<string | null> => {
  if (!value || isRemote(value)) {
    return value || null;
  }
  const candidates = [
    path.isAbsolute(value) ? value : path.resolve(projectRoot, value),
    path.resolve(publicDir, value),
  ];
  for (const candidate of candidates) {
    if (await exists(candidate)) {
      return candidate;
    }
  }
  return null;
};

const stageAsset = async (asset: ThumbnailAsset, generatedDir: string): Promise<ThumbnailAsset> => {
  const value = asset.path_or_url || asset.publicPath || '';
  if (!value) {
    return asset;
  }
  if (isRemote(value)) {
    return {...asset, publicPath: value};
  }
  const resolved = await resolveInput(value);
  if (!resolved || isRemote(resolved)) {
    return asset;
  }
  const alreadyPublic = publicPathFor(resolved);
  if (alreadyPublic) {
    return {...asset, publicPath: alreadyPublic};
  }
  await fs.mkdir(generatedDir, {recursive: true});
  const staged = path.join(generatedDir, `${sanitize(asset.id)}_${sanitize(path.basename(resolved))}`);
  if (!(await exists(staged))) {
    await fs.copyFile(resolved, staged);
  }
  return {...asset, publicPath: publicPathFor(staged) ?? asset.publicPath};
};

const defaultOutputPath = (conceptPath: string): string => {
  const dir = path.dirname(conceptPath);
  const concept = path.basename(conceptPath, '.json');
  return path.join(path.dirname(dir), 'renders', `${concept}.png`);
};

const main = async () => {
  const conceptPath = path.resolve(argPath);
  const concept = await readJson<ThumbnailConceptFile>(conceptPath);
  const safeBriefId = sanitize(concept.briefId || 'brief');
  const safeConceptId = sanitize(concept.conceptId || 'concept');
  const generatedDir = path.join(publicDir, 'generated', 'thumbnails', safeBriefId, safeConceptId);
  const stagedAssets = [];
  for (const asset of concept.assets || []) {
    stagedAssets.push(await stageAsset(asset, generatedDir));
  }
  const props: ThumbnailConceptProps = {
    ...concept,
    assets: stagedAssets,
  };
  const outputPath = path.resolve(projectRoot, concept.outputPath || defaultOutputPath(conceptPath));
  await fs.mkdir(path.dirname(outputPath), {recursive: true});

  const serveUrl = await bundle({
    entryPoint: path.join(rendererRoot, 'src', 'Root.tsx'),
  });
  const composition = await selectComposition({
    serveUrl,
    id: 'thumbnail',
    inputProps: props,
  });
  await renderStill({
    serveUrl,
    composition,
    inputProps: props,
    output: outputPath,
    frame: 0,
  });

  const updated = {
    ...concept,
    assets: stagedAssets,
    rendered_png: path.relative(projectRoot, outputPath).split(path.sep).join('/'),
  };
  await writeJson(conceptPath, updated);
  console.log(JSON.stringify({output_path: outputPath}, null, 2));
};

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

