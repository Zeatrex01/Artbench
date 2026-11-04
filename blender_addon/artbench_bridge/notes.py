"""Notes kept inside the .blend: plain notes and to-dos with a priority, each one able to point at an object of the
scene. In the 3D view an amber pin and the note's first line float beside that object, like a sticky note on the
model. The sidebar (tab Artbench, panel Notes) lists them; right-click an object > Add note writes one for it.

They live on the scene (scene.artbench_notes), so they travel with the file and work with Artbench closed. The object is
held by a pointer, so renaming it keeps the link. Every change goes through Blender's undo, which also tells Blender
the file has changed. When Artbench is connected, Send to Artbench hands it a copy of this file's notes; Artbench only shows
that copy, the notes stay in the file."""
import math
import time

import blf
import bpy
import gpu
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from . import link

KINDS = [("todo", "To-do", "Something to do, with a checkbox"), ("note", "Note", "Something to remember")]
PRIORITIES = [("high", "High", ""), ("normal", "Normal", ""), ("low", "Low", "")]
PRIORITY_ICON = {"high": "COLLECTION_COLOR_01", "normal": "COLLECTION_COLOR_03", "low": "LAYER_USED"}
PIN_COLOR = {"high": (0.95, 0.36, 0.30, 1.0), "normal": (0.96, 0.69, 0.20, 1.0), "low": (0.62, 0.62, 0.62, 1.0)}
PIN_TEXT = 48                        # characters of a note shown beside its object
_RANK = {"high": 0, "normal": 1, "low": 2}
_sent = {}                           # file -> (time, count) of this session's last send
_handle = []


class ArtbenchNote(bpy.types.PropertyGroup):
    text: bpy.props.StringProperty(name="Note", description="What the note says")
    kind: bpy.props.EnumProperty(name="Kind", items=KINDS, default="todo")
    done: bpy.props.BoolProperty(name="Done", description="This to-do is done")
    priority: bpy.props.EnumProperty(name="Priority", items=PRIORITIES, default="normal")
    obj: bpy.props.PointerProperty(name="Object", type=bpy.types.Object,
                                   description="The object this note is about; its pin floats beside it")


def first_line(text):
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return line if len(line) <= PIN_TEXT else line[:PIN_TEXT - 1].rstrip() + "…"


def open_count(scene):
    return sum(1 for n in scene.artbench_notes if not (n.kind == "todo" and n.done))


def pin_items(scene, view_layer):
    """[(object, text, more, priority)]: one pin per visible object that has open notes, showing its most urgent one
    and how many more it has. Done to-dos and objects outside this view layer get no pin."""
    by_obj = {}
    for n in scene.artbench_notes:
        if not n.obj or (n.kind == "todo" and n.done) or not n.text.strip():
            continue
        if n.obj.name not in view_layer.objects or not n.obj.visible_get(view_layer=view_layer):
            continue
        by_obj.setdefault(n.obj.name, (n.obj, []))[1].append(n)
    out = []
    for obj, notes in by_obj.values():
        notes.sort(key=lambda n: _RANK[n.priority])
        out.append((obj, first_line(notes[0].text), len(notes) - 1, notes[0].priority))
    return out


def notes_payload(scene):
    """What Send to Artbench carries for this file."""
    return {"file": bpy.data.filepath, "notes": [
        {"text": n.text, "kind": n.kind, "done": n.done, "priority": n.priority, "object": n.obj.name if n.obj else None}
        for n in scene.artbench_notes if n.text.strip()]}


# --- pins in the 3D view --------------------------------------------------------------------------------------------

def _anchor(obj):
    """The top middle of the object's bounds, in the world: where its pin sits."""
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return Vector((sum(c.x for c in corners) / 8, sum(c.y for c in corners) / 8, max(c.z for c in corners)))


def _shape(shader, kind, verts, color):
    shader.uniform_float("color", color)
    batch_for_shader(shader, kind, {"pos": verts}).draw(shader)


def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1), (x0, y1)]


def _disc(x, y, r, steps=16):
    ring = [(x + r * math.cos(2 * math.pi * i / steps), y + r * math.sin(2 * math.pi * i / steps)) for i in range(steps + 1)]
    return [p for i in range(steps) for p in ((x, y), ring[i], ring[i + 1])]


def draw_pins():
    ctx = bpy.context
    scene, space = ctx.scene, ctx.space_data
    if not scene.artbench_show_pins or not getattr(space, "overlay", None) or not space.overlay.show_overlays:
        return
    items = pin_items(scene, ctx.view_layer)
    if not items:
        return
    s = ctx.preferences.system.ui_scale or 1.0               # 0 until a window has opened
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")
    blf.size(0, 11 * s)
    for obj, text, more, priority in items:
        at = location_3d_to_region_2d(ctx.region, ctx.region_data, _anchor(obj))
        if at is None:                                     # behind the view
            continue
        x, y = at.x, at.y + 8 * s
        label = text + (f"  +{more}" if more else "")
        w, h = blf.dimensions(0, label)
        _shape(shader, "TRIS", _rect(x + 8 * s, y - 5 * s, x + 18 * s + w, y + h + 5 * s), (0.08, 0.08, 0.08, 0.72))
        _shape(shader, "TRIS", _rect(x + 8 * s, y - 5 * s, x + 10 * s, y + h + 5 * s), PIN_COLOR[priority])
        _shape(shader, "TRIS", _disc(x, y + h / 2, 4.5 * s), PIN_COLOR[priority])
        blf.position(0, x + 14 * s, y, 0)
        blf.color(0, 1.0, 0.96, 0.88, 1.0)
        blf.draw(0, label)
    gpu.state.blend_set("NONE")


# --- operators ------------------------------------------------------------------------------------------------------

class ARTBENCH_OT_note_add(bpy.types.Operator):
    bl_idname = "artbench.note_add"
    bl_label = "Add note"
    bl_description = "Write a note or a to-do in this file, on the active object"
    bl_options = {"REGISTER", "UNDO"}
    text: bpy.props.StringProperty(name="Note")
    kind: bpy.props.EnumProperty(name="Kind", items=KINDS, default="todo")
    priority: bpy.props.EnumProperty(name="Priority", items=PRIORITIES, default="normal")
    attach: bpy.props.BoolProperty(name="On the active object", default=True)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "text", text="")
        layout.row().prop(self, "kind", expand=True)
        layout.prop(self, "priority")
        obj = context.active_object
        if obj:
            layout.prop(self, "attach", text=f"On {obj.name}")

    def execute(self, context):
        if not self.text.strip():
            self.report({"WARNING"}, "Write the note first")
            return {"CANCELLED"}
        scene = context.scene
        note = scene.artbench_notes.add()
        note.text, note.kind, note.priority = self.text.strip(), self.kind, self.priority
        if self.attach and context.active_object:
            note.obj = context.active_object
        scene.artbench_note_index = len(scene.artbench_notes) - 1
        self.text = ""
        return {"FINISHED"}


class ARTBENCH_OT_note_remove(bpy.types.Operator):
    bl_idname = "artbench.note_remove"
    bl_label = "Remove note"
    bl_description = "Remove the selected note from this file"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return len(context.scene.artbench_notes) > 0

    def execute(self, context):
        scene = context.scene
        i = scene.artbench_note_index
        if not 0 <= i < len(scene.artbench_notes):
            return {"CANCELLED"}
        scene.artbench_notes.remove(i)
        scene.artbench_note_index = min(i, len(scene.artbench_notes) - 1)
        return {"FINISHED"}


class ARTBENCH_OT_note_goto(bpy.types.Operator):
    bl_idname = "artbench.note_goto"
    bl_label = "Show the object"
    bl_description = "Select the note's object and frame it in the 3D view"
    bl_options = {"REGISTER", "UNDO"}
    index: bpy.props.IntProperty()

    def execute(self, context):
        notes = context.scene.artbench_notes
        obj = notes[self.index].obj if 0 <= self.index < len(notes) else None
        if not obj or obj.name not in context.view_layer.objects:
            self.report({"WARNING"}, "This note's object is not in the scene")
            return {"CANCELLED"}
        for o in context.view_layer.objects:
            o.select_set(o == obj)
        context.view_layer.objects.active = obj
        for area in getattr(context.screen, "areas", []):
            if area.type == "VIEW_3D":
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                with context.temp_override(area=area, region=region):
                    bpy.ops.view3d.view_selected()
                break
        return {"FINISHED"}


class ARTBENCH_OT_notes_send(bpy.types.Operator):
    bl_idname = "artbench.notes_send"
    bl_label = "Send to Artbench"
    bl_description = "Give Artbench a copy of this file's notes; sending again replaces the copy (the notes stay here)"

    @classmethod
    def poll(cls, context):
        return bool(link.STATE["connected"] and bpy.data.filepath)

    def execute(self, context):
        body = notes_payload(context.scene)
        try:
            got = link.call(link.server_url(), "blender_notes_send", body) or {}
        except link.ArtbenchError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        _sent[bpy.data.filepath] = (time.time(), got.get("count", len(body["notes"])))
        self.report({"INFO"}, f"Sent {len(body['notes'])} notes to Artbench, project {got.get('project')}")
        return {"FINISHED"}


# --- interface ------------------------------------------------------------------------------------------------------

class ARTBENCH_UL_notes(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        if item.kind == "todo":
            row.prop(item, "done", text="")
        else:
            row.label(text="", icon="TEXT")
        text = row.row()
        text.active = not (item.kind == "todo" and item.done)
        text.prop(item, "text", text="", emboss=False, icon=PRIORITY_ICON[item.priority])
        if item.obj:
            row.label(text=item.obj.name, icon="OBJECT_DATA")


class ARTBENCH_PT_notes(bpy.types.Panel):
    bl_label = "Notes"
    bl_idname = "ARTBENCH_PT_notes"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Artbench"
    bl_order = 0

    def draw_header(self, context):
        n = open_count(context.scene)
        self.layout.label(text=f"{n} open" if n else "")

    def draw(self, context):
        layout, scene = self.layout, context.scene
        row = layout.row()
        row.template_list("ARTBENCH_UL_notes", "", scene, "artbench_notes", scene, "artbench_note_index", rows=4)
        side = row.column(align=True)
        side.operator("artbench.note_add", text="", icon="ADD")
        side.operator("artbench.note_remove", text="", icon="REMOVE")
        i = scene.artbench_note_index
        if 0 <= i < len(scene.artbench_notes):
            note = scene.artbench_notes[i]
            box = layout.box()
            box.prop(note, "text", text="")
            box.row().prop(note, "kind", expand=True)
            box.prop(note, "priority")
            obj_row = box.row(align=True)
            obj_row.prop(note, "obj")
            if note.obj:
                obj_row.operator("artbench.note_goto", text="", icon="ZOOM_SELECTED").index = i
        elif not scene.artbench_notes:
            layout.label(text="Right-click an object > Add note, or press +.", icon="INFO")
        layout.prop(scene, "artbench_show_pins", icon="HIDE_OFF" if scene.artbench_show_pins else "HIDE_ON")
        draw_send(layout)


def draw_send(layout):
    """Send to Artbench, only while Artbench answers: the notes never need it."""
    if not link.STATE["connected"]:
        return
    if not bpy.data.filepath:
        layout.label(text="Save the file to send its notes to Artbench", icon="INFO")
        return
    if not link.STATE["project"]:
        layout.label(text="This file is in no Artbench project", icon="INFO")
        return
    layout.operator("artbench.notes_send", icon="EXPORT")
    sent = _sent.get(bpy.data.filepath)
    if sent:
        layout.label(text=f"Sent {sent[1]} at {time.strftime('%H:%M', time.localtime(sent[0]))}", icon="CHECKMARK")


def draw_menu(self, context):
    self.layout.separator()
    self.layout.operator("artbench.note_add", text="Add note", icon="PINNED")


CLASSES = (ArtbenchNote, ARTBENCH_OT_note_add, ARTBENCH_OT_note_remove, ARTBENCH_OT_note_goto, ARTBENCH_OT_notes_send,
           ARTBENCH_UL_notes, ARTBENCH_PT_notes)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    scene = bpy.types.Scene
    scene.artbench_notes = bpy.props.CollectionProperty(type=ArtbenchNote)
    scene.artbench_note_index = bpy.props.IntProperty(name="Selected note", default=0)
    scene.artbench_show_pins = bpy.props.BoolProperty(name="Show pins in the 3D view", default=True,
                                                   description="Show each open note beside its object")
    bpy.types.VIEW3D_MT_object_context_menu.append(draw_menu)
    _handle.append(bpy.types.SpaceView3D.draw_handler_add(draw_pins, (), "WINDOW", "POST_PIXEL"))


def unregister():
    while _handle:
        bpy.types.SpaceView3D.draw_handler_remove(_handle.pop(), "WINDOW")
    bpy.types.VIEW3D_MT_object_context_menu.remove(draw_menu)
    for name in ("artbench_notes", "artbench_note_index", "artbench_show_pins"):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
