import bpy
import sys

def main():
    print("=== Blender Scene Render Settings ===")
    scene = bpy.context.scene
    print(f"Render Engine: {scene.render.engine}")
    
    eevee = getattr(scene, "eevee", None)
    if eevee:
        print("Eevee Settings:")
        for attr in dir(eevee):
            if not attr.startswith("__") and not attr.startswith("bl_") and not attr.startswith("rna_"):
                try:
                    val = getattr(eevee, attr)
                    print(f"  {attr}: {val}")
                except Exception:
                    pass
    else:
        print("No Eevee settings found on scene.")
        
    cycles = getattr(scene, "cycles", None)
    if cycles:
        print("Cycles Settings:")
        for attr in dir(cycles):
            if not attr.startswith("__") and not attr.startswith("bl_") and not attr.startswith("rna_"):
                try:
                    val = getattr(cycles, attr)
                    print(f"  {attr}: {val}")
                except Exception:
                    pass
    else:
        print("No Cycles settings found on scene.")

if __name__ == "__main__":
    main()
