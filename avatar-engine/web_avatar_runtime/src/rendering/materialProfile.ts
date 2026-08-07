import * as THREE from "three";

export type SemanticMaterialClass =
  | "skin"
  | "eye"
  | "cornea"
  | "eye_occlusion"
  | "tearline"
  | "hair"
  | "eyelash"
  | "teeth"
  | "tongue"
  | "cloth"
  | "nails"
  | "generic";

export type MaterialEntry = {
  class: SemanticMaterialClass;
  textures?: Record<string, string>;
};

export type MaterialProfile = {
  version: "material_profile_v1";
  broken_meshes?: string[];
  defringe_hair?: boolean;
  materials: Record<string, MaterialEntry>;
};

export type MaterialApplicationReport = {
  profile_version: string;
  resolved_materials: number;
  fallback_materials: string[];
  hidden_meshes: string[];
  loaded_texture_slots: string[];
  semantic_counts: Record<string, number>;
  subsurface_approximation: string;
};

type ProfileMaterial = THREE.MeshPhysicalMaterial & {
  alphaHash?: boolean;
  alphaToCoverage?: boolean;
};

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

function materialUrl(avatarUrl: string, relativePath: string): string {
  return new URL(relativePath, new URL(avatarUrl, window.location.href)).href;
}

function applyCommonPhysical(material: ProfileMaterial): void {
  material.metalness = 0;
  material.envMapIntensity = 0.22;
  material.emissive.set(0x000000);
  material.emissiveIntensity = 0;
}

function applySemanticSettings(
  material: ProfileMaterial,
  semantic: SemanticMaterialClass,
): void {
  applyCommonPhysical(material);
  switch (semantic) {
    case "skin":
      material.roughness = 0.68;
      material.normalScale.set(0.58, 0.58);
      material.specularIntensity = 0.32;
      material.ior = 1.4;
      material.sheen = 0.02;
      material.sheenColor.set(0x6b3028);
      material.sheenRoughness = 0.88;
      material.transmission = 0.004;
      material.thickness = 0.06;
      material.attenuationDistance = 1.2;
      material.attenuationColor.set(0xffb9a4);
      material.clearcoat = 0.025;
      material.clearcoatRoughness = 0.72;
      break;
    case "eye":
      material.roughness = 0.42;
      material.normalScale.set(0.5, 0.5);
      material.specularIntensity = 0.38;
      break;
    case "cornea":
      material.roughness = 0.12;
      material.ior = 1.376;
      material.specularIntensity = 0.82;
      material.clearcoat = 0.72;
      material.clearcoatRoughness = 0.08;
      break;
    case "eye_occlusion":
      material.roughness = 0.76;
      material.opacity = 0.16;
      material.transparent = true;
      material.depthWrite = false;
      break;
    case "tearline":
      material.roughness = 0.08;
      material.opacity = 0.32;
      material.transparent = true;
      material.depthWrite = false;
      material.clearcoat = 1;
      material.clearcoatRoughness = 0.03;
      material.specularIntensity = 0.9;
      break;
    case "hair":
    case "eyelash":
      material.roughness = semantic === "hair" ? 0.58 : 0.48;
      material.alphaTest = semantic === "hair" ? 0.015 : 0.08;
      material.transparent = true;
      material.depthWrite = false;
      material.depthTest = true;
      material.side = THREE.DoubleSide;
      // Alpha hash was tested in the fixed gate and rejected because its
      // stipple remains visible in deterministic PNG capture without TAA.
      material.alphaHash = false;
      material.alphaToCoverage = false;
      material.specularIntensity = semantic === "hair" ? 0.22 : 0.16;
      break;
    case "teeth":
      material.color.multiply(new THREE.Color(0xfff2df));
      material.roughness = 0.46;
      material.specularIntensity = 0.42;
      break;
    case "tongue":
      material.color.multiply(new THREE.Color(0xf1b0a8));
      material.roughness = 0.56;
      material.specularIntensity = 0.3;
      break;
    case "cloth":
      material.roughness = 0.86;
      material.specularIntensity = 0.18;
      break;
    case "nails":
      material.roughness = 0.5;
      material.clearcoat = 0.12;
      material.clearcoatRoughness = 0.4;
      break;
    case "generic":
      material.roughness = Math.max(material.roughness, 0.45);
      break;
  }
}

export async function applyMaterialProfile(
  root: THREE.Object3D,
  profile: MaterialProfile,
  avatarUrl: string,
): Promise<MaterialApplicationReport> {
  const loader = new THREE.TextureLoader();
  const textureCache = new Map<string, Promise<THREE.Texture>>();
  const loadedSlots: string[] = [];
  const fallbackMaterials: string[] = [];
  const hiddenMeshes: string[] = [];
  const semanticCounts: Record<string, number> = {};
  const tasks: Promise<void>[] = [];
  const brokenMeshes = new Set(profile.broken_meshes ?? []);

  const loadDataTexture = (relativePath: string): Promise<THREE.Texture> => {
    const url = materialUrl(avatarUrl, relativePath);
    const existing = textureCache.get(url);
    if (existing) return existing;
    const pending = loader.loadAsync(url).then((texture) => {
      texture.colorSpace = THREE.NoColorSpace;
      texture.flipY = false;
      texture.wrapS = THREE.RepeatWrapping;
      texture.wrapT = THREE.RepeatWrapping;
      texture.needsUpdate = true;
      return texture;
    });
    textureCache.set(url, pending);
    return pending;
  };

  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh & { isMesh?: boolean };
    if (mesh.isMesh !== true || !mesh.material) return;
    if (brokenMeshes.has(mesh.name)) {
      mesh.visible = false;
      hiddenMeshes.push(mesh.name);
      return;
    }
    mesh.castShadow = true;
    mesh.receiveShadow = true;

    eachMaterial(mesh.material, (rawMaterial) => {
      const material = rawMaterial as ProfileMaterial;
      const entry = profile.materials[material.name];
      if (!entry || !(material instanceof THREE.MeshStandardMaterial)) {
        fallbackMaterials.push(material.name || mesh.name || material.uuid);
        return;
      }
      semanticCounts[entry.class] = (semanticCounts[entry.class] ?? 0) + 1;
      if (entry.class === "hair" || entry.class === "eyelash") {
        mesh.renderOrder = entry.class === "hair" ? 10 : 12;
      }
      applySemanticSettings(material, entry.class);
      const textures = entry.textures ?? {};
      const attach = async (slot: string, property: keyof ProfileMaterial): Promise<void> => {
        const relativePath = textures[slot];
        if (!relativePath) return;
        const texture = await loadDataTexture(relativePath);
        (material[property] as THREE.Texture | null) = texture;
        loadedSlots.push(`${material.name}:${slot}`);
      };
      tasks.push(
        (async () => {
          await attach("roughness", "roughnessMap");
          await attach("ao", "aoMap");
          await attach("specular", "specularIntensityMap");
          await attach("sss", "thicknessMap");
          await attach("transmission", "transmissionMap");
          if (entry.class === "skin" && textures.micro_normal) {
            await attach("micro_normal", "clearcoatNormalMap");
            material.clearcoatNormalScale.set(0.08, 0.08);
          }
          material.aoMapIntensity = entry.class === "skin" ? 0.38 : 0.65;
          material.needsUpdate = true;
        })(),
      );
    });
  });

  await Promise.all(tasks);
  return {
    profile_version: profile.version,
    resolved_materials: Object.values(semanticCounts).reduce((a, b) => a + b, 0),
    fallback_materials: [...new Set(fallbackMaterials)].sort(),
    hidden_meshes: hiddenMeshes.sort(),
    loaded_texture_slots: loadedSlots.sort(),
    semantic_counts: semanticCounts,
    subsurface_approximation:
      "bounded MeshPhysicalMaterial transmission/thickness masks with low sheen; no emissive",
  };
}
