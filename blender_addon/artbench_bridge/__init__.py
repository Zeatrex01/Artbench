"""Artbench Bridge: notes inside Blender, and a link to Artbench on top.

- notes.py: notes and to-dos kept in the .blend, pinned to objects in the 3D view; they work with Artbench closed.
- link.py: tells the Artbench server on this machine which .blend is open, and hands it the file's notes on request.
- here: the connection panel, the add-on preferences (address, Test connection) and registration.

Standalone: Python standard library and bpy only; it never imports Artbench's own code."""
import atexit
import webbrowser

import bpy

from . import link, notes

bl_info = {                          # for Blender versions that install legacy add-ons; 4.2+ reads blender_manifest.toml
    "name": "Artbench Bridge", "author": "Zeatrex01", "version": (0, 3, 0), "blender": (4, 2, 0),
    "location": "3D View > Sidebar > Artbench", "description": "Notes pinned to objects in the .blend, and a link to Artbench",
    "category": "Import-Export",
}


class ARTBENCH_OT_test_connection(bpy.types.Operator):
    bl_idname = "artbench.test_connection"
    bl_label = "Test connection"
    bl_description = "Ask Artbench now whether it answers, and say what happened"

    def execute(self, context):
        try:
            link.refresh_now()
        except link.ArtbenchError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        project = link.STATE["project"]
        self.report({"INFO"}, f"Connected to Artbench at {link.server_url()}" + (f", project {project}" if project else ""))
        return {"FINISHED"}


class ARTBENCH_OT_open_page(bpy.types.Operator):
    bl_idname = "artbench.open_page"
    bl_label = "Open Artbench"
    bl_description = "Open the Artbench page"

    def execute(self, context):
        webbrowser.open(link.server_url() + "/")
        return {"FINISHED"}


class ARTBENCH_OT_open_preferences(bpy.types.Operator):
    bl_idname = "artbench.open_preferences"
    bl_label = "Connection settings"
    bl_description = "Open this add-on's preferences: the Artbench address and Test connection"

    def execute(self, context):
        bpy.ops.screen.userpref_show()
        context.preferences.active_section = "ADDONS"
        bpy.data.window_managers["WinMan"].addon_search = "Artbench"
        return {"FINISHED"}


def draw_status(layout):
    col = layout.column(align=True)
    for icon, text, alert in link.status_lines():
        row = col.row()
        row.alert = alert
        row.label(text=text, icon=icon)


class ArtbenchBridgePreferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    url: bpy.props.StringProperty(name="Artbench address", default=link.DEFAULT_URL,
                                  description="Where Artbench runs on this machine; the default fits a normal install")

    def draw(self, context):
        layout = self.layout
        layout.label(text="Notes live in the .blend (3D view > Sidebar > Artbench). Artbench, when open, gets a copy on Send.")
        box = layout.box()
        box.label(text="Connection", icon="LINKED")
        draw_status(box)
        box.prop(self, "url")
        row = box.row()
        row.operator("artbench.test_connection", icon="FILE_REFRESH")
        row.operator("artbench.open_page", icon="URL")


class ARTBENCH_PT_bridge(bpy.types.Panel):
    bl_label = "Artbench link"
    bl_idname = "ARTBENCH_PT_bridge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Artbench"
    bl_order = 1

    def draw_header(self, context):
        self.layout.label(text="", icon="LINKED" if link.STATE["connected"] else "UNLINKED")

    def draw(self, context):
        layout = self.layout
        draw_status(layout)
        row = layout.row(align=True)
        if link.STATE["connected"]:
            row.operator("artbench.open_page", icon="URL")
            row.operator("artbench.test_connection", text="", icon="FILE_REFRESH")
        else:
            row.operator("artbench.test_connection", text="Try again", icon="FILE_REFRESH")
            row.operator("artbench.open_preferences", text="", icon="PREFERENCES")


CLASSES = (ArtbenchBridgePreferences, ARTBENCH_OT_test_connection, ARTBENCH_OT_open_page, ARTBENCH_OT_open_preferences,
           ARTBENCH_PT_bridge)


def register():
    notes.register()                                   # first: the Notes panel sits above the link
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    if not bpy.app.timers.is_registered(link.tick):
        bpy.app.timers.register(link.tick, first_interval=0.5, persistent=True)
    atexit.register(link.on_exit)


def unregister():
    if bpy.app.timers.is_registered(link.tick):
        bpy.app.timers.unregister(link.tick)
    atexit.unregister(link.on_exit)
    link.on_exit()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    notes.unregister()
