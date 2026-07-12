import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { BrowserJob } from "./avatarJob.js";
import { normalizeVisemeArrays } from "./visemes.js";

declare global {
  interface Window {
    __canvasRecordingBase64?: string;
    __canvasRecordingMimeType?: string;
    __canvasFrameCaptureCount?: number;
    __pushCanvasFrame?: (dataUrl: string, frameIndex: number) => Promise<void>;
  }
}

const CHROMA_GREEN = 0x00ff00;
const VISEME_PREFIX = "viseme_";
const FADE_MS = 45;
const BLINK_PERIOD_MS = 4200;
const BLINK_DURATION_MS = 150;
const BLINK_OFFSET_MS = 900;

const OCULUS_VISEMES = [
  "sil",
  "PP",
  "FF",
  "TH",
  "DD",
  "kk",
  "CH",
  "SS",
  "nn",
  "RR",
  "aa",
  "E",
  "I",
  "O",
  "U",
] as const;

const OCULUS_TO_REALLUSION: Record<string, Record<string, number>> = {
  sil: {},
  PP: { V_Explosive: 0.34 },
  FF: { V_Dental_Lip: 0.4, V_Lip_Open: 0.16 },
  TH: {
    V_Dental_Lip: 0.24,
    V_Lip_Open: 0.52,
    Mouth_Drop_Lower: 0.28,
    Jaw_Open: 0.035,
  },
  DD: {
    V_Affricate: 0.3,
    V_Lip_Open: 0.58,
    Mouth_Drop_Lower: 0.34,
    Jaw_Open: 0.04,
  },
  kk: {
    V_Affricate: 0.28,
    V_Lip_Open: 0.52,
    Mouth_Drop_Lower: 0.28,
    Jaw_Open: 0.035,
  },
  CH: {
    V_Affricate: 0.42,
    V_Lip_Open: 0.34,
    Mouth_Drop_Lower: 0.16,
    Jaw_Open: 0.025,
  },
  SS: { V_Tight: 0.2, V_Lip_Open: 0.18, Jaw_Open: 0.015 },
  nn: {
    V_Tight: 0.16,
    V_Lip_Open: 0.26,
    Mouth_Drop_Lower: 0.12,
    Jaw_Open: 0.02,
  },
  RR: {
    V_Tight_O: 0.22,
    V_Lip_Open: 0.42,
    Mouth_Drop_Lower: 0.2,
    Jaw_Open: 0.03,
  },
  aa: {
    V_Lip_Open: 1.0,
    V_Open: 0.12,
    Mouth_Drop_Lower: 0.72,
    Mouth_Drop_Upper: 0.08,
    Jaw_Open: 0.08,
  },
  E: {
    V_Wide: 0.22,
    V_Lip_Open: 0.82,
    Mouth_Drop_Lower: 0.42,
    Jaw_Open: 0.045,
  },
  I: {
    V_Wide: 0.34,
    V_Lip_Open: 0.42,
    Mouth_Drop_Lower: 0.18,
    Jaw_Open: 0.02,
  },
  O: {
    V_Tight_O: 0.58,
    V_Lip_Open: 0.5,
    Mouth_Drop_Lower: 0.28,
    Jaw_Open: 0.04,
  },
  U: { V_Tight_O: 0.46, V_Tight: 0.04, V_Lip_Open: 0.36, Jaw_Open: 0.02 },
};

const REALLUSION_BLINK_SHAPES = ["Eye_Blink_L", "Eye_Blink_R"];
const REALLUSION_NEUTRAL_FACE_MORPHS = [
  "Mouth_Frown_L",
  "Mouth_Frown_R",
  "Mouth_Press_L",
  "Mouth_Press_R",
  "Mouth_Tighten_L",
  "Mouth_Tighten_R",
  "Mouth_Close",
  "Mouth_Down",
  "Mouth_Contract",
  "Mouth_Roll_In_Lower_L",
  "Mouth_Roll_In_Lower_R",
  "Mouth_Roll_In_Upper_L",
  "Mouth_Roll_In_Upper_R",
  "Mouth_Shrug_Lower",
  "Mouth_Shrug_Upper",
  "Jaw_Up",
  "Jaw_Backward",
  "Nose_Crease_L",
  "Nose_Crease_R",
  "Nose_Nostril_Dilate_L",
  "Nose_Nostril_Dilate_R",
  "Nose_Nostril_Down_L",
  "Nose_Nostril_Down_R",
  "Nose_Nostril_Raise_L",
  "Nose_Nostril_Raise_R",
  "Nose_Sneer_L",
  "Nose_Sneer_R",
  "Brow_Compress_L",
  "Brow_Compress_R",
  "Brow_Drop_L",
  "Brow_Drop_R",
  "Eye_Wide_L",
  "Eye_Wide_R",
];

const REALLUSION_SOFT_NEUTRAL_FACE_MORPHS: Record<string, number> = {
  Eye_Blink_L: 0.065,
  Eye_Blink_R: 0.065,
  Eye_Squint_L: 0.045,
  Eye_Squint_R: 0.045,
  Brow_Raise_Inner_L: 0.018,
  Brow_Raise_Inner_R: 0.018,
  Mouth_Smile_L: 0.026,
  Mouth_Smile_R: 0.026,
};

type MorphMesh = THREE.Mesh & {
  morphTargetDictionary: Record<string, number>;
  morphTargetInfluences: number[];
};

type VisemeProfile = {
  id: "oculus_viseme" | "reallusion_viseme";
  controlledMorphs: string[];
  missingMorphs: string[];
};

type CameraPreset = {
  distanceFactor: number;
  heightFactor: number;
  targetHeightFactor: number;
  xFactor?: number;
};

const CAMERA_PRESETS: Record<string, CameraPreset> = {
  front_close: {
    distanceFactor: 0.58,
    heightFactor: 0.72,
    targetHeightFactor: 0.72,
  },
  front_medium: {
    distanceFactor: 0.95,
    heightFactor: 0.62,
    targetHeightFactor: 0.62,
  },
  portrait_main: {
    distanceFactor: 1.15,
    heightFactor: 0.58,
    targetHeightFactor: 0.58,
  },
  waist_up: {
    distanceFactor: 1.45,
    heightFactor: 0.55,
    targetHeightFactor: 0.55,
  },
  landscape_intro: {
    distanceFactor: 2.0,
    heightFactor: 0.48,
    targetHeightFactor: 0.48,
  },
  landscape_conclusion: {
    distanceFactor: 2.0,
    heightFactor: 0.48,
    targetHeightFactor: 0.48,
  },
  side_three_quarter: {
    distanceFactor: 1.1,
    heightFactor: 0.62,
    targetHeightFactor: 0.62,
    xFactor: 0.65,
  },
};

function setStatus(msg: string): void {
  const el = document.getElementById("status");
  if (el) el.textContent = msg;
  console.info("[rocketbox-runtime]", msg);
}

function fatal(err: unknown): never {
  const message = err instanceof Error ? err.message : String(err);
  window.__renderStatus = "error";
  window.__renderError = message;
  setStatus(`ERROR: ${message}`);
  console.error("[rocketbox-runtime] FATAL:", err);
  throw err instanceof Error ? err : new Error(message);
}

function isMorphMesh(obj: THREE.Object3D): obj is MorphMesh {
  const mesh = obj as Partial<MorphMesh>;
  return (
    (obj as THREE.Object3D & { isMesh?: boolean }).isMesh === true &&
    !!mesh.morphTargetDictionary &&
    !!mesh.morphTargetInfluences &&
    Array.isArray(mesh.morphTargetInfluences)
  );
}

function findMorphMeshes(root: THREE.Object3D): MorphMesh[] {
  const meshes: MorphMesh[] = [];
  root.traverse((obj) => {
    obj.frustumCulled = false;
    if (isMorphMesh(obj)) meshes.push(obj);
  });
  return meshes;
}

function collectMorphTargetNames(meshes: MorphMesh[]): string[] {
  const names = new Set<string>();
  for (const mesh of meshes) {
    for (const name of Object.keys(mesh.morphTargetDictionary)) names.add(name);
  }
  return [...names].sort();
}

function hasMorph(meshes: MorphMesh[], morphName: string): boolean {
  return meshes.some(
    (mesh) => mesh.morphTargetDictionary[morphName] !== undefined,
  );
}

function resolveVisemeProfile(
  meshes: MorphMesh[],
  requestedProfile?: string,
): VisemeProfile {
  const allMorphs = collectMorphTargetNames(meshes);
  const allMorphSet = new Set(allMorphs);
  const oculusMorphs = OCULUS_VISEMES.map((name) => `${VISEME_PREFIX}${name}`);
  const reallusionMorphs = [
    ...new Set(
      Object.values(OCULUS_TO_REALLUSION).flatMap((mapping) =>
        Object.keys(mapping),
      ),
    ),
  ];
  const hasReallusionFace =
    allMorphSet.has("V_Open") ||
    allMorphSet.has("V_Explosive") ||
    allMorphSet.has("V_Dental_Lip");
  const useReallusion =
    requestedProfile === "reallusion_viseme" ||
    (requestedProfile !== "oculus_viseme" && hasReallusionFace);

  if (useReallusion) {
    return {
      id: "reallusion_viseme",
      controlledMorphs: reallusionMorphs.filter((name) =>
        allMorphSet.has(name),
      ),
      missingMorphs: reallusionMorphs.filter((name) => !allMorphSet.has(name)),
    };
  }

  return {
    id: "oculus_viseme",
    controlledMorphs: oculusMorphs.filter((name) => allMorphSet.has(name)),
    missingMorphs: oculusMorphs.filter((name) => !allMorphSet.has(name)),
  };
}

function resetMorphs(meshes: MorphMesh[], morphNames: string[]): void {
  for (const mesh of meshes) {
    for (const name of morphNames) {
      const index = mesh.morphTargetDictionary[name];
      if (index !== undefined) mesh.morphTargetInfluences[index] = 0;
    }
  }
}

function applyMorph(
  meshes: MorphMesh[],
  morphName: string,
  value: number,
): void {
  const clamped = Math.min(1, Math.max(0, value));
  for (const mesh of meshes) {
    const index = mesh.morphTargetDictionary[morphName];
    if (index !== undefined) {
      mesh.morphTargetInfluences[index] = Math.max(
        mesh.morphTargetInfluences[index] ?? 0,
        clamped,
      );
    }
  }
}

function applyVisemeCue(
  meshes: MorphMesh[],
  profile: VisemeProfile,
  cueName: string,
  value: number,
): void {
  if (cueName === "sil") return;

  if (profile.id === "reallusion_viseme") {
    const mapping = OCULUS_TO_REALLUSION[cueName] ?? {};
    for (const [morphName, weight] of Object.entries(mapping)) {
      applyMorph(meshes, morphName, value * weight);
    }
    return;
  }

  applyMorph(meshes, `${VISEME_PREFIX}${cueName}`, value);
}

function mouthOpenStrengthForCue(cueName: string, value: number): number {
  if (cueName === "sil") return 0;
  const mapping = OCULUS_TO_REALLUSION[cueName] ?? {};
  const rawOpen =
    (mapping.Jaw_Open ?? 0) * 1.35 +
    (mapping.Jaw_Down ?? 0) * 1.1 +
    (mapping.Mouth_Drop_Lower ?? 0) * 0.45 +
    (mapping.V_Lip_Open ?? 0) * 0.22 +
    (mapping.V_Open ?? 0) * 0.18;
  return Math.min(1, Math.max(0, value * rawOpen));
}

type TongueMotion = { x: number; y: number; z: number };

const ZERO_TONGUE_MOTION: TongueMotion = { x: 0, y: 0, z: 0 };
const TONGUE_REST_INSET_Z = -0.001;

function tongueMotionForCue(
  cueName: string,
  value: number,
  openStrength: number,
): TongueMotion {
  const v = cueName === "sil" ? 0 : Math.min(1, Math.max(0, value));
  const open = Math.min(1, Math.max(0, openStrength));

  let x = 0;
  let y = -open * 0.005;
  let z = open * 0.0012;

  switch (cueName) {
    case "TH":
      y += v * 0.0012;
      z += v * 0.01;
      break;
    case "DD":
    case "nn":
      y += v * 0.0028;
      z += v * 0.0045;
      break;
    case "CH":
    case "SS":
      y += v * 0.0015;
      z += v * 0.0035;
      break;
    case "kk":
      y += v * 0.001;
      z -= v * 0.0022;
      break;
    case "RR":
      x += v * 0.0008;
      y += v * 0.0015;
      z -= v * 0.0008;
      break;
    case "aa":
      y -= v * 0.0025;
      z += v * 0.001;
      break;
    case "E":
    case "I":
      y += v * 0.0006;
      z += v * 0.002;
      break;
    case "O":
    case "U":
      y -= v * 0.0015;
      z -= v * 0.0018;
      break;
  }

  return { x, y, z };
}

function applyCc4JawMotion(
  rig: ProceduralRig | null,
  openStrength: number,
  tongueMotion: TongueMotion = ZERO_TONGUE_MOTION,
): void {
  if (!rig) return;

  const open = Math.min(1, Math.max(0, openStrength));

  // CC4 teeth are bone-driven: upper teeth hang from CC_Base_UpperJaw, while
  // lower teeth + tongue hang from CC_Base_JawRoot. Rotating JawRoot on this
  // export twists the mouth asymmetrically, so use world-space translations.
  // Always apply even at 0 openness so bones reset cleanly between visemes.
  applyBoneWorldTranslation(rig, "CC_Base_JawRoot", 0, -open * 0.005, 0);
  applyBoneWorldTranslation(rig, "CC_Base_Teeth02", 0, -open * 0.016, 0);
  applyBoneWorldTranslation(
    rig,
    "CC_Base_Tongue01",
    tongueMotion.x,
    tongueMotion.y,
    tongueMotion.z + TONGUE_REST_INSET_Z,
  );

  // Keep the upper row visible while reducing the original downward drift.
  // Avoid a constant upward bias; that tucks the teeth behind the upper lip at rest.
  applyBoneWorldTranslation(rig, "CC_Base_UpperJaw", 0, -open * 0.00015, 0);
  applyBoneWorldTranslation(rig, "CC_Base_Teeth01", 0, -open * 0.00035, 0);
}

function currentVisemeAt(
  tMs: number,
  visemes: string[],
  vtimes: number[],
  vdurations: number[],
): { cue: string; value: number } | null {
  for (let i = 0; i < visemes.length; i++) {
    const start = vtimes[i];
    const end = start + vdurations[i];
    if (tMs >= start && tMs <= end) {
      const fadeIn = Math.min(1, Math.max(0, (tMs - start) / FADE_MS));
      const fadeOut = Math.min(1, Math.max(0, (end - tMs) / FADE_MS));
      const value = Math.min(fadeIn, fadeOut, 1);
      return { cue: visemes[i], value };
    }
  }
  return null;
}

function collectBlinkMorphs(meshes: MorphMesh[]): string[] {
  return REALLUSION_BLINK_SHAPES.filter((name) => hasMorph(meshes, name));
}

function collectNeutralFaceMorphs(meshes: MorphMesh[]): string[] {
  return REALLUSION_NEUTRAL_FACE_MORPHS.filter((name) =>
    hasMorph(meshes, name),
  );
}

function collectSoftNeutralFaceMorphs(
  meshes: MorphMesh[],
): Array<[string, number]> {
  return Object.entries(REALLUSION_SOFT_NEUTRAL_FACE_MORPHS).filter(([name]) =>
    hasMorph(meshes, name),
  );
}

function applySoftNeutralFace(
  meshes: MorphMesh[],
  softNeutralMorphs: Array<[string, number]>,
): void {
  for (const [morphName, value] of softNeutralMorphs) {
    applyMorph(meshes, morphName, value);
  }
}

function blinkStrengthAt(tMs: number): number {
  const phase = (tMs + BLINK_OFFSET_MS) % BLINK_PERIOD_MS;
  if (phase > BLINK_DURATION_MS) return 0;
  return Math.sin((phase / BLINK_DURATION_MS) * Math.PI);
}

function applyBlink(
  meshes: MorphMesh[],
  blinkMorphs: string[],
  tMs: number,
): void {
  if (blinkMorphs.length === 0) return;
  const strength = blinkStrengthAt(tMs);
  if (strength <= 0) return;
  for (const morphName of blinkMorphs) applyMorph(meshes, morphName, strength);
}

function backgroundColorForJob(job: BrowserJob): number {
  switch ((job.render?.background ?? "chroma_green").toLowerCase()) {
    case "neutral_studio":
    case "studio_neutral":
      return 0x202733;
    case "newsroom_blue":
    case "studio_blue":
      return 0x16243a;
    case "charcoal":
    case "dark_gray":
      return 0x1c1c1f;
    case "chroma_green":
    default:
      return CHROMA_GREEN;
  }
}

function configureRenderer(
  container: HTMLElement,
  width: number,
  height: number,
  clearColor: number,
): THREE.WebGLRenderer {
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: false,
    preserveDrawingBuffer: true,
  });
  renderer.setSize(width, height, true);
  renderer.setPixelRatio(1);
  renderer.domElement.style.position = "absolute";
  renderer.domElement.style.inset = "0";
  renderer.domElement.style.width = "100%";
  renderer.domElement.style.height = "100%";
  renderer.domElement.style.display = "block";
  renderer.setClearColor(clearColor, 1);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.08;
  renderer.shadowMap.enabled = false;
  container.innerHTML = "";
  container.appendChild(renderer.domElement);
  return renderer;
}

function addLights(scene: THREE.Scene): void {
  const ambient = new THREE.AmbientLight(0xffffff, 0.55);
  scene.add(ambient);

  const hemisphere = new THREE.HemisphereLight(0xf7fbff, 0x2a3038, 1.05);
  scene.add(hemisphere);

  const beautyFill = new THREE.DirectionalLight(0xfff8f0, 0.95);
  beautyFill.position.set(0.0, 1.8, 4.2);
  scene.add(beautyFill);

  const key = new THREE.DirectionalLight(0xfff1df, 1.75);
  key.position.set(2.8, 3.5, 4.8);
  scene.add(key);

  const fill = new THREE.DirectionalLight(0xdce8ff, 1.0);
  fill.position.set(-3.8, 2.0, 3.4);
  scene.add(fill);

  const rim = new THREE.DirectionalLight(0xeaf2ff, 0.95);
  rim.position.set(-0.8, 2.8, -3.6);
  scene.add(rim);
}

function boxFromObjects(objects: THREE.Object3D[]): THREE.Box3 {
  const box = new THREE.Box3();
  for (const obj of objects) box.expandByObject(obj);
  return box;
}

function hideNonAvatarMeshes(
  root: THREE.Object3D,
  morphMeshes: MorphMesh[],
): void {
  const keep = new Set<THREE.Object3D>(morphMeshes);
  root.traverse((obj) => {
    const candidate = obj as THREE.Object3D & { isMesh?: boolean };
    if (candidate.isMesh === true && !keep.has(obj)) {
      obj.visible = false;
      window.__renderWarnings.push(
        `Rocketbox runtime hid non-avatar mesh: ${obj.name || obj.uuid}`,
      );
    }
  });
}

function hideObviousStrayMeshes(root: THREE.Object3D): void {
  const strayNames = new Set(["cube", "icosphere", "sphere", "plane"]);
  root.traverse((obj) => {
    const candidate = obj as THREE.Object3D & { isMesh?: boolean };
    const normalizedName = (obj.name || "")
      .toLowerCase()
      .replace(/[._-]?\d+$/, "");
    if (candidate.isMesh === true && strayNames.has(normalizedName)) {
      obj.visible = false;
      window.__renderWarnings.push(
        `Runtime hid obvious stray mesh: ${obj.name || obj.uuid}`,
      );
    }
  });
}

function findVisibleMeshes(root: THREE.Object3D): THREE.Object3D[] {
  const meshes: THREE.Object3D[] = [];
  root.traverse((obj) => {
    const candidate = obj as THREE.Object3D & { isMesh?: boolean };
    if (candidate.isMesh === true && obj.visible) meshes.push(obj);
  });
  return meshes;
}

function eachMaterial(
  material: THREE.Material | THREE.Material[],
  fn: (material: THREE.Material) => void,
): void {
  if (Array.isArray(material)) {
    for (const entry of material) fn(entry);
  } else {
    fn(material);
  }
}

const defringedTextures = new WeakMap<THREE.Texture, THREE.Texture>();

function defringeAlphaTexture(
  texture: THREE.Texture | null,
): THREE.Texture | null {
  if (!texture || !texture.image) return texture;
  const existing = defringedTextures.get(texture);
  if (existing) return existing;

  const image = texture.image as CanvasImageSource & {
    width?: number;
    height?: number;
    naturalWidth?: number;
    naturalHeight?: number;
  };
  const width = image.width ?? image.naturalWidth ?? 0;
  const height = image.height ?? image.naturalHeight ?? 0;
  if (!width || !height) return texture;

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return texture;

  ctx.drawImage(image, 0, 0, width, height);
  const imageData = ctx.getImageData(0, 0, width, height);
  const source = new Uint8ClampedArray(imageData.data);
  const data = imageData.data;

  // Remove barely-visible alpha noise and replace transparent-pixel RGB with
  // nearby opaque hair color. This avoids black/dirty fringes when alpha-blended.
  const alphaNoiseFloor = 8;
  const opaqueAlpha = 96;
  const radius = 3;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      const alpha = source[i + 3];
      if (alpha < alphaNoiseFloor) {
        data[i + 3] = 0;
      }
      if (alpha >= 245) continue;

      let r = 0;
      let g = 0;
      let b = 0;
      let weight = 0;
      for (let dy = -radius; dy <= radius; dy++) {
        const ny = y + dy;
        if (ny < 0 || ny >= height) continue;
        for (let dx = -radius; dx <= radius; dx++) {
          const nx = x + dx;
          if (nx < 0 || nx >= width) continue;
          const ni = (ny * width + nx) * 4;
          const na = source[ni + 3];
          if (na < opaqueAlpha) continue;
          const d = Math.max(1, Math.abs(dx) + Math.abs(dy));
          const w = na / d;
          r += source[ni] * w;
          g += source[ni + 1] * w;
          b += source[ni + 2] * w;
          weight += w;
        }
      }
      if (weight > 0) {
        data[i] = r / weight;
        data[i + 1] = g / weight;
        data[i + 2] = b / weight;
      }
    }
  }

  ctx.putImageData(imageData, 0, 0);
  const cleaned = new THREE.CanvasTexture(canvas);
  cleaned.name = `${texture.name || "hair_texture"}_defringed`;
  cleaned.colorSpace = texture.colorSpace;
  cleaned.flipY = texture.flipY;
  cleaned.wrapS = texture.wrapS;
  cleaned.wrapT = texture.wrapT;
  cleaned.magFilter = texture.magFilter;
  cleaned.minFilter = texture.minFilter;
  cleaned.generateMipmaps = texture.generateMipmaps;
  cleaned.anisotropy = texture.anisotropy;
  cleaned.needsUpdate = true;
  defringedTextures.set(texture, cleaned);
  return cleaned;
}

function applyAvatarMaterialTweaks(
  root: THREE.Object3D,
  backgroundMode: string,
): void {
  const isChroma = backgroundMode.toLowerCase() === "chroma_green";
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh & { isMesh?: boolean };
    if (mesh.isMesh !== true || !mesh.material) return;

    const objectName = (mesh.name || "").toLowerCase();
    if (objectName.startsWith("bun") || objectName.startsWith("hair_base")) {
      // These CC export layers are large transparent card shells behind/around
      // the head. They create the ugly crown/halo in Three.js; keep the cleaner
      // front strand layers for the anchor crop.
      mesh.visible = false;
      window.__renderWarnings.push(
        `Hidden problematic transparent hair layer: ${mesh.name}`,
      );
      return;
    }
    eachMaterial(mesh.material, (material) => {
      const materialName = (material.name || "").toLowerCase();
      const combinedName = `${objectName} ${materialName}`;
      const standard = material as THREE.MeshStandardMaterial;
      const isHair =
        combinedName.includes("hair") ||
        combinedName.includes("bang") ||
        combinedName.includes("bun");
      const isSkin =
        combinedName.includes("body") ||
        combinedName.includes("skin") ||
        combinedName.includes("face");
      const isEyeOrTear =
        combinedName.includes("eye") ||
        combinedName.includes("tear") ||
        combinedName.includes("occlusion");
      const isEyeOcclusion = combinedName.includes("occlusion");
      const isMouthInterior =
        combinedName.includes("teeth") ||
        combinedName.includes("tongue") ||
        combinedName.includes("mouth");

      if ("roughness" in standard && typeof standard.roughness === "number") {
        if (isSkin) standard.roughness = 0.72;
        else standard.roughness = Math.max(standard.roughness, 0.42);
      }
      if ("metalness" in standard && typeof standard.metalness === "number") {
        standard.metalness = 0;
      }
      if (isSkin) {
        if ("aoMapIntensity" in standard) standard.aoMapIntensity = 0.04;
        if ("normalScale" in standard && standard.normalScale) {
          standard.normalScale.multiplyScalar(0.18);
        }
        if ("emissive" in standard && standard.emissive) {
          standard.emissive.set(0x4a3024);
          standard.emissiveIntensity = 0.075;
        }
      }
      if (isEyeOcclusion) {
        material.opacity = 0.0;
        material.transparent = true;
        material.depthWrite = false;
      }
      if (isMouthInterior && "aoMapIntensity" in standard) {
        standard.aoMapIntensity = 0.08;
      }

      if (isHair) {
        // CC hair is made from layered alpha cards with dark RGB in transparent
        // texels. Clean the texture first, then use blended transparency for
        // neutral previews and stricter alpha cutout only for chroma output.
        if ("map" in standard && standard.map) {
          standard.map = defringeAlphaTexture(standard.map) as THREE.Texture;
        }
        if ("alphaMap" in standard && standard.alphaMap) {
          standard.alphaMap = defringeAlphaTexture(
            standard.alphaMap,
          ) as THREE.Texture;
        }
        material.alphaTest = Math.max(
          material.alphaTest ?? 0,
          isChroma ? 0.34 : 0.015,
        );
        material.transparent = !isChroma;
        material.depthWrite = isChroma;
        material.depthTest = true;
        material.side = THREE.DoubleSide;
        material.blending = THREE.NormalBlending;
        material.premultipliedAlpha = false;

        const coverageMaterial = material as THREE.Material & {
          alphaHash?: boolean;
          alphaToCoverage?: boolean;
        };
        coverageMaterial.alphaHash = false;
        coverageMaterial.alphaToCoverage = isChroma;
        mesh.renderOrder = isChroma ? 5 : 10;
      } else if (!isEyeOrTear) {
        material.depthWrite = true;
      }

      material.needsUpdate = true;
    });
  });
}

function degreesToRadians(value: number | undefined): number {
  return ((value ?? 0) * Math.PI) / 180;
}

function fitModel(
  root: THREE.Object3D,
  avatarObjects: THREE.Object3D[],
  transform: BrowserJob["avatar_transform"] = {},
): { box: THREE.Box3; size: THREE.Vector3; center: THREE.Vector3 } {
  root.updateMatrixWorld(true);
  let box = boxFromObjects(avatarObjects);
  const size = new THREE.Vector3();
  const center = new THREE.Vector3();
  box.getSize(size);

  // Auto-orient: if the avatar's longest dimension is Z, it was exported Z-up.
  // Rotate it so Z height becomes Three.js Y height.
  if (size.z > size.y * 1.35 && size.z > size.x * 1.35) {
    root.rotation.x -= Math.PI / 2;
    root.updateMatrixWorld(true);
    box = boxFromObjects(avatarObjects);
    box.getSize(size);
    window.__renderWarnings.push(
      "Rocketbox runtime auto-rotated Z-up avatar to Y-up.",
    );
  }

  root.rotation.x += degreesToRadians(transform?.rotation_x_degrees);
  root.rotation.y += degreesToRadians(transform?.rotation_y_degrees);
  root.rotation.z += degreesToRadians(transform?.rotation_z_degrees);
  if (transform?.scale && transform.scale > 0)
    root.scale.multiplyScalar(transform.scale);
  root.updateMatrixWorld(true);
  box = boxFromObjects(avatarObjects);
  box.getSize(size);

  // Auto-scale: bad FBX→GLB exports often leave the armature at 0.01 scale.
  // If the avatar is tiny, scale the whole root to roughly 1.8 m tall.
  const maxDim = Math.max(size.x, size.y, size.z);
  if (maxDim > 0 && maxDim < 0.5) {
    const factor = 1.8 / maxDim;
    root.scale.multiplyScalar(factor);
    root.updateMatrixWorld(true);
    box = boxFromObjects(avatarObjects);
    box.getSize(size);
    window.__renderWarnings.push(
      `Rocketbox runtime auto-scaled tiny avatar by ${factor.toFixed(2)}x.`,
    );
  }

  box.getCenter(center);

  // Center horizontally and place feet at y=0. Assumes model has now been made Y-up.
  root.position.x -= center.x;
  root.position.z -= center.z;
  root.position.y -= box.min.y;
  root.updateMatrixWorld(true);

  const fittedBox = boxFromObjects(avatarObjects);
  fittedBox.getSize(size);
  fittedBox.getCenter(center);
  return { box: fittedBox, size, center };
}

function applyCamera(
  camera: THREE.PerspectiveCamera,
  cameraName: string,
  size: THREE.Vector3,
  center: THREE.Vector3,
  aspect: number,
  overrides: BrowserJob["camera_overrides"] = {},
): void {
  const preset = CAMERA_PRESETS[cameraName] ?? CAMERA_PRESETS.front_medium;
  const height = Math.max(size.y, 1.6);
  const width = Math.max(size.x, 0.4);
  const depth = Math.max(size.z, 0.4);
  const radius = Math.max(width, depth, height * 0.42);

  const distanceMultiplier = overrides?.distance_multiplier ?? 1;
  const distance =
    radius *
    preset.distanceFactor *
    distanceMultiplier *
    (aspect < 1 ? 1.25 : 1.0);
  const targetHeightFactor =
    overrides?.target_height_factor ?? preset.targetHeightFactor;
  const cameraHeightFactor = overrides?.height_factor ?? preset.heightFactor;
  const target = new THREE.Vector3(
    center.x,
    height * targetHeightFactor,
    center.z,
  );

  camera.position.set(
    (preset.xFactor ?? 0) * radius,
    height * cameraHeightFactor,
    center.z + distance,
  );
  camera.near = 0.01;
  camera.far = 100;
  camera.fov = cameraName === "front_close" ? 18 : 24;
  camera.aspect = aspect;
  camera.lookAt(target);
  camera.updateProjectionMatrix();
}

function findAnimationClip(
  clips: THREE.AnimationClip[],
  requested: string | undefined,
): THREE.AnimationClip | null {
  if (!requested) return null;
  const normalized = requested.toLowerCase();
  return (
    clips.find((clip) => clip.name === requested) ??
    clips.find((clip) => clip.name.toLowerCase() === normalized) ??
    clips.find((clip) => clip.name.toLowerCase().includes(normalized)) ??
    null
  );
}

function playLoopingClip(
  mixer: THREE.AnimationMixer,
  clip: THREE.AnimationClip,
): THREE.AnimationAction {
  const action = mixer.clipAction(clip);
  action.reset();
  action.enabled = true;
  action.setLoop(THREE.LoopRepeat, Infinity);
  action.clampWhenFinished = false;
  action.fadeIn(0.35);
  action.play();
  return action;
}

function playOneShotClip(
  mixer: THREE.AnimationMixer,
  clip: THREE.AnimationClip,
): THREE.AnimationAction {
  const action = mixer.clipAction(clip);
  action.reset();
  action.enabled = true;
  action.setLoop(THREE.LoopOnce, 1);
  action.clampWhenFinished = false;
  action.fadeIn(0.15);
  action.play();
  return action;
}

type ProceduralRig = {
  bones: Record<string, THREE.Object3D>;
  base: Record<string, THREE.Quaternion>;
  basePosition: Record<string, THREE.Vector3>;
};

function buildProceduralRig(morphMeshes: MorphMesh[]): ProceduralRig {
  const bones: Record<string, THREE.Object3D> = {};
  const base: Record<string, THREE.Quaternion> = {};
  const basePosition: Record<string, THREE.Vector3> = {};

  // getObjectByName on gltf.scene does NOT reach skeleton bones in Three.js r180.
  // Enumerate all bones via SkinnedMesh.skeleton.bones instead.
  for (const mesh of morphMeshes) {
    const sm = mesh as unknown as THREE.SkinnedMesh;
    if (sm.skeleton) {
      for (const bone of sm.skeleton.bones) {
        if (!bones[bone.name]) {
          bones[bone.name] = bone;
          base[bone.name] = bone.quaternion.clone();
          basePosition[bone.name] = bone.position.clone();
        }
      }
    }
  }

  window.__renderWarnings.push(
    `Rocketbox procedural rig: ${Object.keys(bones).length} skeleton bones available`,
  );
  return { bones, base, basePosition };
}

function applyBoneDelta(
  rig: ProceduralRig,
  name: string,
  x: number,
  y: number,
  z: number,
): void {
  const bone = rig.bones[name];
  const base = rig.base[name];
  if (!bone || !base) return;
  bone.quaternion
    .copy(base)
    .multiply(
      new THREE.Quaternion().setFromEuler(new THREE.Euler(x, y, z, "XYZ")),
    );
}

function applyBoneWorldTranslation(
  rig: ProceduralRig,
  name: string,
  x: number,
  y: number,
  z: number,
): void {
  const bone = rig.bones[name];
  const base = rig.basePosition[name];
  const parent = bone?.parent;
  if (!bone || !base || !parent) return;

  parent.updateWorldMatrix(true, false);
  const worldBase = parent.localToWorld(base.clone());
  worldBase.add(new THREE.Vector3(x, y, z));
  bone.position.copy(parent.worldToLocal(worldBase));
}

function pulseAt(
  tSeconds: number,
  centerSeconds: number,
  durationSeconds = 0.9,
): number {
  const half = durationSeconds / 2;
  const d = Math.abs(tSeconds - centerSeconds);
  if (d >= half) return 0;
  return Math.sin((1 - d / half) * Math.PI * 0.5);
}

function gestureStrength(
  gestureEvents: NonNullable<BrowserJob["animation"]["gesture_events"]>,
  tSeconds: number,
  names: string[],
): number {
  let strength = 0;
  for (const event of gestureEvents) {
    const eventName = event.type ?? event.clip ?? "";
    if (!names.includes(eventName)) continue;
    strength = Math.max(
      strength,
      pulseAt(tSeconds, event.time, event.duration ?? 0.9),
    );
  }
  return strength;
}

function applyProceduralAnchor(
  rig: ProceduralRig,
  tMs: number,
  gestureEvents: NonNullable<BrowserJob["animation"]["gesture_events"]>,
  speechEnergy = 0,
): void {
  const t = tMs / 1000;
  const breathe = Math.sin(t * Math.PI * 2 * 0.22);
  const micro = Math.sin(t * Math.PI * 2 * 0.09 + 0.7);
  const sway = Math.sin(t * Math.PI * 2 * 0.13 + 1.8);
  const naturalNod = Math.max(0, Math.sin(t * Math.PI * 2 * 0.16 - 0.6));
  const speech = Math.min(1, Math.max(0, speechEnergy));
  const speechBeat =
    speech * (0.45 + 0.55 * Math.sin(t * Math.PI * 2 * 0.58 + 0.4));
  const speechSide = speech * Math.sin(t * Math.PI * 2 * 0.26 + 1.1);
  const speechHand = speech * Math.sin(t * Math.PI * 2 * 0.42 + 2.4);

  const right = gestureStrength(gestureEvents, t, [
    "emphasis_right",
    "explain_right",
  ]);
  const left = gestureStrength(gestureEvents, t, [
    "emphasis_left",
    "explain_left",
  ]);
  const both = gestureStrength(gestureEvents, t, [
    "emphasis_small",
    "explain_small",
  ]);
  const nod = Math.max(
    naturalNod * 0.22,
    gestureStrength(gestureEvents, t, ["nod", "affirm"]),
  );

  if (rig.bones.CC_Base_Head) {
    applyCc4ProceduralAnchor(
      rig,
      breathe,
      micro,
      sway,
      nod,
      right,
      left,
      both,
      speech,
      speechBeat,
      speechSide,
      speechHand,
    );
    return;
  }

  applyBip01ProceduralAnchor(rig, breathe, micro, nod, right, left, both);
}

function applyCc4ProceduralAnchor(
  rig: ProceduralRig,
  breathe: number,
  micro: number,
  sway: number,
  nod: number,
  right: number,
  left: number,
  both: number,
  speechHold: number,
  speechBeat: number,
  speechSide: number,
  speechHand: number,
): void {
  // CC4/Reallusion skeleton support. Keep all values deliberately small: the
  // anchor crop only needs breathing, micro head motion, and relaxed shoulders.
  applyBoneDelta(
    rig,
    "CC_Base_Waist",
    0.012 + breathe * 0.004,
    sway * 0.002,
    0,
  );
  applyBoneDelta(
    rig,
    "CC_Base_Spine01",
    0.026 + breathe * 0.006,
    sway * 0.003,
    micro * 0.003,
  );
  applyBoneDelta(
    rig,
    "CC_Base_Spine02",
    0.034 + breathe * 0.007,
    sway * 0.004,
    micro * 0.004,
  );
  applyBoneDelta(
    rig,
    "CC_Base_NeckTwist01",
    0.002 + nod * 0.016,
    micro * 0.004,
    sway * 0.002,
  );
  applyBoneDelta(
    rig,
    "CC_Base_NeckTwist02",
    0.002 + nod * 0.016,
    micro * 0.004,
    sway * 0.002,
  );
  applyBoneDelta(
    rig,
    "CC_Base_Head",
    -0.004 + nod * 0.022 + breathe * 0.002,
    micro * 0.008,
    sway * 0.004,
  );

  const r = Math.max(right, both * 0.65);
  const l = Math.max(left, both * 0.55);

  applyBoneDelta(
    rig,
    "CC_Base_R_Clavicle",
    -0.085 + breathe * 0.002,
    0.01,
    -0.018 - r * 0.008,
  );
  applyBoneDelta(
    rig,
    "CC_Base_L_Clavicle",
    -0.085 + breathe * 0.002,
    -0.01,
    0.018 + l * 0.008,
  );
  applyBoneWorldTranslation(
    rig,
    "CC_Base_R_Clavicle",
    0,
    -0.04 + speechBeat * 0.004,
    0,
  );
  applyBoneWorldTranslation(
    rig,
    "CC_Base_L_Clavicle",
    0,
    -0.04 + speechBeat * 0.004,
    0,
  );
  applyBoneDelta(
    rig,
    "CC_Base_R_Upperarm",
    0.08 + r * 0.015 + speechHold * 0.045 + speechBeat * 0.025,
    0.18 + speechSide * 0.026,
    0.86 + r * 0.01 + speechSide * 0.036 + speechBeat * 0.014,
  );
  applyBoneDelta(
    rig,
    "CC_Base_L_Upperarm",
    0.08 + l * 0.015 + speechHold * 0.038 + speechBeat * 0.02,
    -0.18 + speechSide * 0.022,
    -0.86 - l * 0.01 + speechSide * 0.03 - speechBeat * 0.012,
  );
  applyBoneDelta(
    rig,
    "CC_Base_R_Forearm",
    0.04 + speechHold * 0.22 + speechBeat * 0.12,
    speechSide * 0.04,
    speechHand * 0.055,
  );
  applyBoneDelta(
    rig,
    "CC_Base_L_Forearm",
    0.035 + speechHold * 0.2 + speechBeat * 0.1,
    -speechSide * 0.035,
    -speechHand * 0.05,
  );
  applyBoneDelta(
    rig,
    "CC_Base_R_Hand",
    speechHand * 0.08,
    speechSide * 0.045,
    speechHold * 0.045 + speechBeat * 0.045,
  );
  applyBoneDelta(
    rig,
    "CC_Base_L_Hand",
    -speechHand * 0.075,
    -speechSide * 0.04,
    -(speechHold * 0.04 + speechBeat * 0.04),
  );
}

function applyBip01ProceduralAnchor(
  rig: ProceduralRig,
  breathe: number,
  micro: number,
  nod: number,
  right: number,
  left: number,
  both: number,
): void {
  // Confident anchor posture: subtle forward lean through torso, stable head.
  // All bone names use underscores (Blender FBX→glTF export convention).
  // Spine X rotates forward, Y/Z add micro-sway.
  applyBoneDelta(rig, "Bip01_Spine", 0.04 + breathe * 0.006, 0, 0);
  applyBoneDelta(rig, "Bip01_Spine1", 0.06 + breathe * 0.007, 0, micro * 0.004);
  applyBoneDelta(rig, "Bip01_Spine2", 0.07 + breathe * 0.008, 0, micro * 0.005);
  // Head: positive X tilts chin down; keep yaw tiny so the anchor stays camera-facing.
  applyBoneDelta(rig, "Bip01_Neck", 0.02 + nod * 0.035, 0, 0);
  applyBoneDelta(
    rig,
    "Bip01_Head",
    0.015 + nod * 0.05 + micro * 0.004,
    micro * 0.003,
    0,
  );

  // Arms: X lowers from the wide bind pose; a small mirrored Z component
  // pulls the arms inward so the anchor does not read as T/A-posed. Gesture
  // pulses lift/reach very slightly rather than playing canned head-turn clips.
  const r = Math.max(right, both * 0.7);
  const l = Math.max(left, both * 0.55);

  applyBoneDelta(rig, "Bip01_R_Clavicle", 0, 0, -0.04 - r * 0.015);
  applyBoneDelta(rig, "Bip01_R_UpperArm", -1.05 + r * 0.18, 0, -0.42 + r * 0.1);
  applyBoneDelta(rig, "Bip01_R_Forearm", 0.22 + r * 0.12, 0, 0.04);
  applyBoneDelta(rig, "Bip01_R_Hand", 0, r * 0.04, r * 0.035);

  applyBoneDelta(rig, "Bip01_L_Clavicle", 0, 0, 0.04 + l * 0.015);
  applyBoneDelta(rig, "Bip01_L_UpperArm", -1.05 + l * 0.18, 0, 0.42 - l * 0.1);
  applyBoneDelta(rig, "Bip01_L_Forearm", 0.22 + l * 0.1, 0, -0.04);
  applyBoneDelta(rig, "Bip01_L_Hand", 0, -l * 0.04, -l * 0.035);
}

async function decodeAudio(job: BrowserJob): Promise<AudioBuffer> {
  setStatus(`Fetching audio: ${job.audio_url}`);
  const audioResp = await fetch(job.audio_url);
  if (!audioResp.ok)
    throw new Error(
      `HTTP ${audioResp.status} fetching audio from "${job.audio_url}"`,
    );
  const arrayBuffer = await audioResp.arrayBuffer();
  const audioCtx = new AudioContext();
  return await audioCtx.decodeAudioData(arrayBuffer);
}

function chooseMediaRecorderMimeType(): string {
  const candidates = [
    "video/webm;codecs=vp9",
    "video/webm;codecs=vp8",
    "video/webm",
  ];
  return (
    candidates.find((mimeType) => MediaRecorder.isTypeSupported(mimeType)) ?? ""
  );
}

async function blobToBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

type CanvasRecorder = {
  recorder: MediaRecorder;
  done: Promise<void>;
};

function startCanvasRecorder(
  canvas: HTMLCanvasElement,
  fps: number,
): CanvasRecorder | null {
  if (
    typeof canvas.captureStream !== "function" ||
    typeof MediaRecorder === "undefined"
  ) {
    window.__renderWarnings.push(
      "Canvas MediaRecorder is unavailable; falling back to Playwright viewport video.",
    );
    return null;
  }

  const stream = canvas.captureStream(fps);
  const chunks: Blob[] = [];
  const mimeType = chooseMediaRecorderMimeType();
  const recorder = mimeType
    ? new MediaRecorder(stream, { mimeType })
    : new MediaRecorder(stream);

  const done = new Promise<void>((resolve, reject) => {
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    recorder.onerror = () => {
      reject(new Error("Canvas MediaRecorder failed."));
    };
    recorder.onstop = async () => {
      try {
        const blob = new Blob(chunks, {
          type: recorder.mimeType || mimeType || "video/webm",
        });
        window.__canvasRecordingMimeType = blob.type || "video/webm";
        window.__canvasRecordingBase64 = await blobToBase64(blob);
        window.__renderWarnings.push(
          `Canvas recording captured ${chunks.length} chunks (${blob.size} bytes, ${window.__canvasRecordingMimeType}).`,
        );
        resolve();
      } catch (err) {
        reject(err instanceof Error ? err : new Error(String(err)));
      }
    };
  });

  recorder.start(250);
  window.__renderWarnings.push(
    `Canvas MediaRecorder started at ${fps} fps (${recorder.mimeType || "default webm"}).`,
  );
  return { recorder, done };
}

export async function runRocketboxRuntime(job: BrowserJob): Promise<void> {
  if (job.face.mode !== "3d_viseme") {
    fatal(
      new Error(
        `Unsupported face.mode "${job.face.mode}". Rocketbox runtime needs "3d_viseme".`,
      ),
    );
  }

  const { visemes, vtimes, vdurations } = normalizeVisemeArrays(
    job.precomputed_visemes,
  );

  const container = document.getElementById("avatar");
  if (!container) fatal(new Error("Required DOM element #avatar not found"));

  const width = job.camera.width;
  const height = job.camera.height;
  const aspect = width / height;

  const backgroundMode = job.render?.background ?? "chroma_green";
  const backgroundColor = backgroundColorForJob(job);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(backgroundColor);
  const camera = new THREE.PerspectiveCamera(24, aspect, 0.01, 100);
  const renderer = configureRenderer(container, width, height, backgroundColor);
  addLights(scene);

  setStatus(`Loading Rocketbox avatar: ${job.avatar_url}`);
  const loader = new GLTFLoader();
  let avatarRoot: THREE.Object3D;
  let animationClips: THREE.AnimationClip[] = [];
  try {
    const gltf = await loader.loadAsync(job.avatar_url, (ev) => {
      if (ev.lengthComputable && ev.total > 0) {
        const pct = Math.round((ev.loaded / ev.total) * 100);
        setStatus(`Loading avatar... ${pct}%`);
      }
    });
    avatarRoot = gltf.scene;
    animationClips = gltf.animations ?? [];
  } catch (err) {
    fatal(err);
  }

  scene.add(avatarRoot);
  const morphMeshes = findMorphMeshes(avatarRoot);
  if (morphMeshes.length === 0)
    fatal(new Error("No morph-target meshes found in avatar GLB."));

  const visemeProfile = resolveVisemeProfile(
    morphMeshes,
    job.face.blendshape_profile,
  );
  const blinkMorphs = collectBlinkMorphs(morphMeshes);
  const neutralFaceMorphs = collectNeutralFaceMorphs(morphMeshes);
  const softNeutralFaceMorphs = collectSoftNeutralFaceMorphs(morphMeshes);

  if (visemeProfile.id === "reallusion_viseme") {
    // Character Creator clothing/hair often do not have morph targets; keep them.
    hideObviousStrayMeshes(avatarRoot);
    applyAvatarMaterialTweaks(avatarRoot, backgroundMode);
  } else {
    // User-authored Rocketbox scenes sometimes export Cube/Icosphere/etc. Keep
    // old strict behavior for Oculus/RPM-style morph-only avatar exports.
    hideNonAvatarMeshes(avatarRoot, morphMeshes);
  }

  if (visemeProfile.missingMorphs.length > 0) {
    window.__renderWarnings.push(
      `${visemeProfile.id} avatar is missing morphs: ${visemeProfile.missingMorphs.join(", ")}`,
    );
  }
  if (blinkMorphs.length === 0) {
    window.__renderWarnings.push(
      "No blink morphs found; blink animation disabled.",
    );
  }
  window.__renderWarnings.push(
    `Using ${visemeProfile.id} profile with ${visemeProfile.controlledMorphs.length} mouth morphs, ${blinkMorphs.length} blink morphs, ${neutralFaceMorphs.length} neutral-face suppressions, and ${softNeutralFaceMorphs.length} soft neutral morphs.`,
  );

  const avatarObjects =
    visemeProfile.id === "reallusion_viseme"
      ? findVisibleMeshes(avatarRoot)
      : morphMeshes;
  const { size, center } = fitModel(
    avatarRoot,
    avatarObjects,
    job.avatar_transform,
  );

  applyCamera(
    camera,
    job.camera.name,
    size,
    center,
    aspect,
    job.camera_overrides,
  );

  const mixer =
    animationClips.length > 0 ? new THREE.AnimationMixer(avatarRoot) : null;
  const availableClipNames = animationClips.map((clip) => clip.name);
  if (availableClipNames.length > 0) {
    window.__renderWarnings.push(
      `Rocketbox animations loaded: ${availableClipNames.join(", ")}`,
    );
  } else {
    window.__renderWarnings.push(
      "Rocketbox GLB has no embedded animation clips; body will remain static.",
    );
  }

  const idleClipName = job.animation?.idle_loop;
  const proceduralAnchor = idleClipName?.toLowerCase() === "procedural_anchor";
  const animationDisabled =
    !idleClipName || idleClipName.toLowerCase() === "none" || proceduralAnchor;
  if (!animationDisabled) {
    const idleClip = findAnimationClip(animationClips, idleClipName);
    if (mixer && idleClip) {
      playLoopingClip(mixer, idleClip);
    } else if (mixer && idleClipName) {
      window.__renderWarnings.push(
        `Requested idle animation not found: ${idleClipName}`,
      );
    }
  }

  const gestureEvents = [...(job.animation?.gesture_events ?? [])].sort(
    (a, b) => a.time - b.time,
  );
  const proceduralRig = proceduralAnchor
    ? buildProceduralRig(morphMeshes)
    : null;
  if (proceduralAnchor) {
    window.__renderWarnings.push("Rocketbox procedural anchor motion enabled.");
  }

  const clipGestureEvents = animationDisabled ? [] : gestureEvents;
  let nextGestureIndex = 0;

  const audioBuffer = await decodeAudio(job);
  const clipDurationMs = Math.max(
    audioBuffer.duration * 1000,
    job.camera.duration_seconds ? job.camera.duration_seconds * 1000 : 0,
  );

  setStatus("Rendering Rocketbox morph animation...");
  window.__renderStatus = "rendering";

  // Play audio inside the page only for timing consistency. The final MP4 audio
  // still comes from FFmpeg muxing the original WAV, same as TalkingHead.
  const audioCtx = new AudioContext();
  const source = audioCtx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(audioCtx.destination);
  const useFrameCapture = !!window.__pushCanvasFrame;
  const canvasRecorder = useFrameCapture
    ? null
    : startCanvasRecorder(renderer.domElement, job.camera.fps);
  const frameCapturePromises: Promise<unknown>[] = [];
  const frameDurationMs = 1000 / job.camera.fps;
  const totalCaptureFrames = Math.ceil(clipDurationMs / frameDurationMs);
  let nextCaptureFrame = 0;
  if (window.__pushCanvasFrame) {
    window.__renderWarnings.push(
      `Canvas PNG frame capture enabled (${totalCaptureFrames} frames at ${job.camera.fps} fps).`,
    );
  }
  const startPerf = performance.now();
  let lastPerf = startPerf;
  let smoothedSpeechGestureStrength = 0;
  const smoothedTongueMotion: TongueMotion = { ...ZERO_TONGUE_MOTION };
  const baseY = avatarRoot.position.y;
  const baseRotationY = avatarRoot.rotation.y;
  if (!useFrameCapture) source.start();

  function frame(): void {
    const now = performance.now();
    const wallElapsedMs = now - startPerf;
    const renderElapsedMs = useFrameCapture
      ? nextCaptureFrame * frameDurationMs
      : wallElapsedMs;
    const deltaSeconds = useFrameCapture
      ? frameDurationMs / 1000
      : Math.max(0, (now - lastPerf) / 1000);
    lastPerf = now;

    if (mixer) mixer.update(deltaSeconds);

    while (
      nextGestureIndex < clipGestureEvents.length &&
      renderElapsedMs >= clipGestureEvents[nextGestureIndex].time * 1000
    ) {
      const event = clipGestureEvents[nextGestureIndex];
      const clipName = event.clip ?? event.type;
      const clip = findAnimationClip(animationClips, clipName);
      if (mixer && clip) {
        playOneShotClip(mixer, clip);
      } else if (clipName) {
        window.__renderWarnings.push(
          `Gesture animation not found: ${clipName}`,
        );
      }
      nextGestureIndex += 1;
    }
    resetMorphs(morphMeshes, [
      ...visemeProfile.controlledMorphs,
      ...blinkMorphs,
      ...neutralFaceMorphs,
      ...softNeutralFaceMorphs.map(([name]) => name),
    ]);

    applySoftNeutralFace(morphMeshes, softNeutralFaceMorphs);

    const active = currentVisemeAt(
      renderElapsedMs,
      visemes,
      vtimes,
      vdurations,
    );
    let mouthOpenStrength = 0;
    let speechGestureStrength = 0;
    let targetTongueMotion = ZERO_TONGUE_MOTION;
    if (active) {
      applyVisemeCue(morphMeshes, visemeProfile, active.cue, active.value);
      if (active.cue !== "sil") {
        speechGestureStrength = Math.min(
          1,
          Math.max(0, active.value * 0.55 + mouthOpenStrength * 0.45),
        );
      }
      if (visemeProfile.id === "reallusion_viseme") {
        mouthOpenStrength = mouthOpenStrengthForCue(active.cue, active.value);
        targetTongueMotion = tongueMotionForCue(
          active.cue,
          active.value,
          mouthOpenStrength,
        );
        if (active.cue !== "sil") {
          speechGestureStrength = Math.min(
            1,
            Math.max(0.18, active.value * 0.5 + mouthOpenStrength * 0.5),
          );
        }
      }
    }
    applyBlink(morphMeshes, blinkMorphs, renderElapsedMs);

    const speechSmoothingRate =
      speechGestureStrength > smoothedSpeechGestureStrength ? 3.2 : 1.9;
    const speechSmoothingAlpha =
      1 - Math.exp(-deltaSeconds * speechSmoothingRate);
    smoothedSpeechGestureStrength +=
      (speechGestureStrength - smoothedSpeechGestureStrength) *
      speechSmoothingAlpha;

    const tongueSmoothingAlpha = 1 - Math.exp(-deltaSeconds * 9);
    smoothedTongueMotion.x +=
      (targetTongueMotion.x - smoothedTongueMotion.x) * tongueSmoothingAlpha;
    smoothedTongueMotion.y +=
      (targetTongueMotion.y - smoothedTongueMotion.y) * tongueSmoothingAlpha;
    smoothedTongueMotion.z +=
      (targetTongueMotion.z - smoothedTongueMotion.z) * tongueSmoothingAlpha;

    if (proceduralRig) {
      applyProceduralAnchor(
        proceduralRig,
        renderElapsedMs,
        gestureEvents,
        smoothedSpeechGestureStrength,
      );
    }
    applyCc4JawMotion(proceduralRig, mouthOpenStrength, smoothedTongueMotion);

    // Keep root transform stable for anchor renders. Facial morphs and the
    // procedural anchor layer provide motion without camera-facing drift.
    avatarRoot.rotation.y = baseRotationY;
    avatarRoot.position.y = baseY;

    renderer.render(scene, camera);

    if (useFrameCapture && window.__pushCanvasFrame) {
      const dataUrl = renderer.domElement.toDataURL("image/png");
      const frameIndex = nextCaptureFrame;
      nextCaptureFrame += 1;
      window.__canvasFrameCaptureCount = nextCaptureFrame;
      frameCapturePromises.push(window.__pushCanvasFrame(dataUrl, frameIndex));
    }

    if (
      (useFrameCapture && nextCaptureFrame >= totalCaptureFrames) ||
      (!useFrameCapture && wallElapsedMs >= clipDurationMs + 150)
    ) {
      const finish = (): void => {
        window.__renderStatus = "done";
        setStatus("Done.");
        renderer.dispose();
      };

      const recorderDone =
        canvasRecorder && canvasRecorder.recorder.state !== "inactive"
          ? canvasRecorder.done
          : Promise.resolve();
      if (canvasRecorder && canvasRecorder.recorder.state === "recording") {
        canvasRecorder.recorder.requestData();
        canvasRecorder.recorder.stop();
      }

      Promise.all([recorderDone, ...frameCapturePromises])
        .then(finish)
        .catch((err) => fatal(err));
      return;
    }
    requestAnimationFrame(frame);
  }

  requestAnimationFrame(frame);
}
