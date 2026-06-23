import {bundle} from '@remotion/bundler';
import {renderMedia, renderStill, selectComposition} from '@remotion/renderer';
import fs from 'node:fs/promises';
import fsSync from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {
  EndscreenProps,
  endscreenSafeZoneMetadata,
  normalizeEndscreenProps,
  requireEndscreenFields,
} from './endscreen.schema';

type EndscreenInputFile = Partial<EndscreenProps>;

const rendererRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const projectRoot = path.resolve(rendererRoot, '..', '..');
const publicDir = path.join(rendererRoot, 'public');
const compositionId = 'SynthPostEndscreen';

const videoExtensions = new Set(['.mp4', '.mov', '.webm', '.mkv']);
const assetFields = [
  'nextVideoThumbnail',
  'recommendedVideoThumbnail',
  'channelLogo',
  'backgroundVisual',
  'anchorVideo',
] as const;

const argPath = process.argv.find((arg) => arg.endsWith('.json'));
if (!argPath) {
  throw new Error('Usage: npm run render:endscreen -- /absolute/or/repo-relative/path/to/endscreen.json');
}

const sanitize = (value: string): string => value.replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^_+|_+$/g, '') || 'asset';

const isRemote = (value: string): boolean => /^https?:\/\//i.test(value);

const readJson = async <T>(filePath: string): Promise<T> => JSON.parse(await fs.readFile(filePath, 'utf-8')) as T;

const writeJson = async (filePath: string, value: unknown): Promise<void> => {
  await fs.mkdir(path.dirname(filePath), {recursive: true});
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

const resolveJsonPath = async (value: string): Promise<string> => {
  const candidates = path.isAbsolute(value)
    ? [value]
    : [path.resolve(projectRoot, value), path.resolve(rendererRoot, value), path.resolve(process.cwd(), value)];
  for (const candidate of candidates) {
    if (await exists(candidate)) {
      return candidate;
    }
  }
  throw new Error(`Endscreen JSON was not found. Tried: ${candidates.join(', ')}`);
};

const publicPathFor = (absolutePath: string): string | null => {
  const relative = path.relative(publicDir, absolutePath);
  if (!relative.startsWith('..') && !path.isAbsolute(relative)) {
    return relative.split(path.sep).join('/');
  }
  return null;
};

const resolveInputAsset = async (value: string): Promise<string | null> => {
  if (!value) {
    return null;
  }
  if (isRemote(value)) {
    return value;
  }
  const candidates = [
    path.isAbsolute(value) ? value : path.resolve(projectRoot, value),
    path.resolve(publicDir, value),
    path.resolve(rendererRoot, value),
  ];
  for (const candidate of candidates) {
    if (await exists(candidate)) {
      return candidate;
    }
  }
  return null;
};

const stageAsset = async (value: string | undefined, generatedDir: string, label: string): Promise<string | undefined> => {
  if (!value) {
    return undefined;
  }
  if (isRemote(value)) {
    return value;
  }
  const resolved = await resolveInputAsset(value);
  if (!resolved || isRemote(resolved)) {
    return undefined;
  }
  const alreadyPublic = publicPathFor(resolved);
  if (alreadyPublic) {
    return alreadyPublic;
  }
  await fs.mkdir(generatedDir, {recursive: true});
  const staged = path.join(generatedDir, `${sanitize(label)}_${sanitize(path.basename(resolved))}`);
  if (!(await exists(staged))) {
    await fs.copyFile(resolved, staged);
  }
  return publicPathFor(staged) ?? undefined;
};

const stageProps = async (input: EndscreenInputFile, generatedDir: string): Promise<EndscreenProps> => {
  const staged: EndscreenInputFile = {...input};
  for (const field of assetFields) {
    staged[field] = await stageAsset(input[field], generatedDir, field);
  }
  return normalizeEndscreenProps(staged);
};

const hasAudio = (filePath: string): boolean => {
  const result = spawnSync(
    process.env.SYNTHPOST_FFPROBE || 'ffprobe',
    ['-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', filePath],
    {encoding: 'utf-8'},
  );
  return result.status === 0 && result.stdout.trim().length > 0;
};

const runChecked = (command: string[]): void => {
  const result = spawnSync(command[0], command.slice(1), {stdio: 'inherit'});
  if (result.status !== 0) {
    throw new Error(`Command failed (${result.status}): ${command.join(' ')}`);
  }
};

const ensureCompatibleMp4 = (inputPath: string, outputPath: string, durationSeconds: number, fps: number): void => {
  const ffmpeg = process.env.SYNTHPOST_FFMPEG || 'ffmpeg';
  const common = [
    ffmpeg,
    '-hide_banner',
    '-loglevel',
    'warning',
    '-y',
    '-i',
    inputPath,
  ];
  if (hasAudio(inputPath)) {
    runChecked([
      ...common,
      '-map',
      '0:v:0',
      '-map',
      '0:a:0',
      '-r',
      String(fps),
      '-vf',
      'format=yuv420p',
      '-c:v',
      'libx264',
      '-pix_fmt',
      'yuv420p',
      '-color_range',
      'tv',
      '-c:a',
      'aac',
      '-ar',
      '48000',
      '-ac',
      '2',
      '-movflags',
      '+faststart',
      outputPath,
    ]);
    return;
  }

  runChecked([
    ...common,
    '-f',
    'lavfi',
    '-t',
    durationSeconds.toFixed(3),
    '-i',
    'anullsrc=r=48000:cl=stereo',
    '-map',
    '0:v:0',
    '-map',
    '1:a:0',
    '-r',
    String(fps),
    '-vf',
    'format=yuv420p',
    '-c:v',
    'libx264',
    '-pix_fmt',
    'yuv420p',
    '-color_range',
    'tv',
    '-c:a',
    'aac',
    '-ar',
    '48000',
    '-ac',
    '2',
    '-shortest',
    '-movflags',
    '+faststart',
    outputPath,
  ]);
};

const main = async () => {
  const jsonPath = await resolveJsonPath(argPath);
  const input = await readJson<EndscreenInputFile>(jsonPath);
  requireEndscreenFields(input);
  const normalizedInput = normalizeEndscreenProps(input);
  const episodeDir = path.join(projectRoot, 'episodes', sanitize(normalizedInput.episodeId), 'endscreen');
  const generatedDir = path.join(publicDir, 'generated', 'endscreen', sanitize(normalizedInput.episodeId));
  const props = await stageProps(input, generatedDir);

  const outputPath = path.join(episodeDir, 'endscreen.mp4');
  const rawOutputPath = path.join(episodeDir, 'endscreen_raw.mp4');
  const previewPath = path.join(episodeDir, 'endscreen_preview.png');
  const safeZonesPath = path.join(episodeDir, 'endscreen_safe_zones.json');
  await fs.mkdir(episodeDir, {recursive: true});

  const serveUrl = await bundle({
    entryPoint: path.join(rendererRoot, 'src', 'Root.tsx'),
  });
  const composition = await selectComposition({
    serveUrl,
    id: compositionId,
    inputProps: props,
  });

  const previewFrame = Math.min(composition.durationInFrames - 1, composition.fps * 12);
  await renderStill({
    serveUrl,
    composition,
    inputProps: props,
    output: previewPath,
    frame: previewFrame,
  });

  await renderMedia({
    serveUrl,
    composition,
    inputProps: props,
    codec: 'h264',
    outputLocation: rawOutputPath,
  });

  ensureCompatibleMp4(rawOutputPath, outputPath, composition.durationInFrames / composition.fps, composition.fps);
  if (fsSync.existsSync(rawOutputPath)) {
    await fs.unlink(rawOutputPath);
  }

  const safeZones = endscreenSafeZoneMetadata(props);
  await writeJson(safeZonesPath, safeZones);

  console.log(
    JSON.stringify(
      {
        output_path: outputPath,
        preview_path: previewPath,
        safe_zones_path: safeZonesPath,
        duration_seconds: safeZones.durationSeconds,
        fps: safeZones.fps,
      },
      null,
      2,
    ),
  );
};

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
