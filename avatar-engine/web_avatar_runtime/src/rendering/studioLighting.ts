import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

export type StudioToneMapping = "aces" | "agx" | "neutral";

export function configureStudioRenderer(
  renderer: THREE.WebGLRenderer,
  toneMapping: StudioToneMapping,
): void {
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping =
    toneMapping === "agx"
      ? THREE.AgXToneMapping
      : toneMapping === "neutral"
        ? THREE.NeutralToneMapping
        : THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
}

export function addStudioLighting(
  scene: THREE.Scene,
  renderer: THREE.WebGLRenderer,
): { dispose: () => void } {
  const pmrem = new THREE.PMREMGenerator(renderer);
  pmrem.compileEquirectangularShader();
  const environment = pmrem.fromScene(new RoomEnvironment(), 0.04);
  scene.environment = environment.texture;

  const key = new THREE.RectAreaLight(0xffead8, 1.0, 2.2, 2.8);
  key.name = "studio_key";
  key.position.set(2.6, 2.9, 3.8);
  key.lookAt(0, 1.25, 0);
  scene.add(key);

  const fill = new THREE.RectAreaLight(0xd9e7ff, 0.22, 2.6, 2.8);
  fill.name = "studio_fill";
  fill.position.set(-3.2, 2.1, 3.0);
  fill.lookAt(0, 1.2, 0);
  scene.add(fill);

  const rim = new THREE.RectAreaLight(0xe8f0ff, 0.45, 1.8, 2.2);
  rim.name = "studio_rim";
  rim.position.set(-1.4, 2.8, -2.6);
  rim.lookAt(0, 1.35, 0);
  scene.add(rim);

  // RectAreaLight cannot cast shadows.  This restrained directional source is
  // aligned near the key and exists only for bounded self-shadow definition.
  const shadow = new THREE.DirectionalLight(0xfff4e8, 0.16);
  shadow.name = "studio_shadow_key";
  shadow.position.set(2.4, 3.6, 4.0);
  shadow.target.position.set(0, 1.25, 0);
  shadow.castShadow = true;
  shadow.shadow.mapSize.set(1024, 1024);
  shadow.shadow.camera.near = 0.1;
  shadow.shadow.camera.far = 12;
  shadow.shadow.camera.left = -1.6;
  shadow.shadow.camera.right = 1.6;
  shadow.shadow.camera.top = 2.2;
  shadow.shadow.camera.bottom = -0.6;
  shadow.shadow.bias = -0.0002;
  shadow.shadow.normalBias = 0.018;
  scene.add(shadow, shadow.target);

  return {
    dispose: () => {
      environment.dispose();
      pmrem.dispose();
    },
  };
}
