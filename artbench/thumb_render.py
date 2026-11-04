"""Runs inside background Blender: import one model (FBX/OBJ/glTF) or open a .blend, frame it and render a small
Workbench preview; or, for an image (TGA, PSD, TIFF, EXR, a large PNG...), scale it so its long side is the preview
size and save it as PNG.   blender -b --python thumb_render.py -- <model or image> <out.png> [size]"""
import sys

import bpy
from mathutils import Vector


IMAGES = (".png", ".jpg", ".jpeg", ".tga", ".psd", ".tif", ".tiff", ".exr", ".bmp", ".hdr", ".webp")


def image_preview(src, out, size):
    img = bpy.data.images.load(src)
    w, h = img.size
    if w > size or h > size:
        k = size / max(w, h)
        img.scale(max(1, round(w * k)), max(1, round(h * k)))
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    src, out = argv[0], argv[1]
    size = int(argv[2]) if len(argv) > 2 else 256
    low = src.lower()
    if low.endswith(IMAGES):
        image_preview(src, out, size)
        return
    if low.endswith(".blend"):
        bpy.ops.wm.open_mainfile(filepath=src)
        for o in bpy.data.objects:
            if o.type in ("CAMERA", "LIGHT") or o.hide_render or o.hide_viewport:
                continue
            o.hide_render = False
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if low.endswith(".fbx"):
            bpy.ops.import_scene.fbx(filepath=src)
        elif low.endswith(".obj"):
            bpy.ops.wm.obj_import(filepath=src)
        else:
            bpy.ops.import_scene.gltf(filepath=src)

    # visible_get() drops helper meshes nobody sees, like the bone shape ("Icosphere") the glTF importer adds
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.hide_render and o.visible_get()]
    if not meshes:
        raise SystemExit("no mesh")
    # The posed vertices, not the bound boxes: a rigged character's bound box is its rest pose in the mesh's own space,
    # so framing by it left the figure small and high in the picture.
    depsgraph = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in meshes:
        ev = o.evaluated_get(depsgraph)
        mesh = ev.to_mesh()
        pts.extend(ev.matrix_world @ v.co for v in mesh.vertices)
        ev.to_mesh_clear()
    if not pts:
        pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center, radius = (lo + hi) / 2, max((hi - lo).length / 2, 1e-3)

    scene = bpy.context.scene
    scene.render.resolution_x = scene.render.resolution_y = size
    cam_data = bpy.data.cameras.new("ThumbCam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("ThumbCam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    direction = Vector((1.0, -1.2, 0.8)).normalized()
    cam.location = center + direction * radius * 4
    cam.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    loc, _ = cam.camera_fit_coords(bpy.context.evaluated_depsgraph_get(), [c for p in pts for c in p])
    dist = (Vector(loc) - center).dot(direction)
    cam.location = Vector(loc) + direction * dist * 0.08              # a small margin around the tight fit
    cam_data.clip_start = max(dist * 0.01, 1e-4)
    cam_data.clip_end = dist * 4 + radius * 4

    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.color_type = "TEXTURE"
    sh.show_shadows = False
    sh.show_cavity = True
    scene.display_settings.display_device = "sRGB"
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)


main()
