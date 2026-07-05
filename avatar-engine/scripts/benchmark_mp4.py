import bpy
import time
import os

def benchmark():
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 100 # test 100 frames to get a stable FPS average
    
    render_dir = "/Users/abhilaksh/Projects/SynthPost/avatar-engine/assets/temp/benchmark_mp4"
    os.makedirs(render_dir, exist_ok=True)
    
    # 1. Configure Eevee Next to fast settings (8 samples, no raytracing)
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
            
    eevee = getattr(scene, "eevee", None)
    if eevee:
        eevee.taa_render_samples = 8
        eevee.taa_samples = 4
        eevee.use_raytracing = False
        eevee.use_volumetric_shadows = False
        eevee.use_shadows = True
    
    # 2. Configure native FFmpeg video output in Blender
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
    
    output_path = os.path.join(render_dir, "benchmark_out")
    scene.render.filepath = output_path
    
    print("\n--- Benchmarking Blender Direct-to-MP4 Render ---")
    t0 = time.time()
    bpy.ops.render.render(animation=True)
    duration = time.time() - t0
    fps = 100.0 / duration
    print(f"Direct MP4 Render Duration: {duration:.2f}s ({fps:.2f} frames/sec)")

if __name__ == "__main__":
    benchmark()
