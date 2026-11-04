"""Runs inside background Blender: import one model (FBX/OBJ/glTF) and write its structure as a versioned snapshot
JSON: objects with vertex/polygon/triangle counts, material and texture names, bones, animations with frame ranges,
bounding box.   blender -b --python model_meta.py -- <model> <out.json>
Schema version 1 (asset_meta.SNAPSHOT_VERSION); bump both when the shape changes."""
import json
import sys

import bpy
from mathutils import Vector

VERSION = 1


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    src, out = argv[0], argv[1]
    low = src.lower()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if low.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=src)
    elif low.endswith(".obj"):
        bpy.ops.wm.obj_import(filepath=src)
    else:
        bpy.ops.import_scene.gltf(filepath=src)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    objects, materials, textures, pts = [], set(), set(), []
    # Importers add helper objects that are not part of the model: glTF puts bone display shapes into a
    # "glTF_not_exported" collection, and any mesh used as a bone's custom shape is display only.
    bone_shapes = {pb.custom_shape for o in bpy.data.objects if o.type == "ARMATURE" for pb in o.pose.bones if pb.custom_shape}
    helper = lambda o: o in bone_shapes or any(c.name.startswith("glTF_not_exported") for c in o.users_collection)
    for o in sorted(bpy.data.objects, key=lambda x: x.name):
        if helper(o):
            continue
        entry = {"name": o.name, "type": o.type, "verts": 0, "polys": 0, "tris": 0}
        if o.type == "MESH":
            mesh = o.evaluated_get(depsgraph).to_mesh()
            calc = getattr(mesh, "calc_loop_triangles", None)      # explicit on 4.x; implicit on newer versions
            if calc:
                calc()
            entry.update(verts=len(mesh.vertices), polys=len(mesh.polygons), tris=len(mesh.loop_triangles))
            o.evaluated_get(depsgraph).to_mesh_clear()
            for slot in o.material_slots:
                if slot.material:
                    materials.add(slot.material.name)
                    tree = slot.material.node_tree
                    for node in (tree.nodes if tree else []):
                        if node.type == "TEX_IMAGE" and node.image:
                            textures.add(node.image.name)
            pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
        objects.append(entry)
    bones = sorted(b.name for a in bpy.data.armatures for b in a.bones)
    actions = [{"name": a.name, "start": int(a.frame_range[0]), "end": int(a.frame_range[1])}
               for a in sorted(bpy.data.actions, key=lambda x: x.name)]
    bbox = None
    if pts:
        bbox = {"min": [round(min(p[i] for p in pts), 4) for i in range(3)],
                "max": [round(max(p[i] for p in pts), 4) for i in range(3)]}
    snap = {"version": VERSION, "objects": objects, "object_names": [o["name"] for o in objects],
            "materials": sorted(materials), "textures": sorted(textures),
            "bones": len(bones), "bone_names": bones,
            "actions": actions, "action_names": [a["name"] for a in actions], "bbox": bbox,
            "totals": {k: sum(o[k] for o in objects) for k in ("verts", "polys", "tris")}}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(snap, f)


main()
