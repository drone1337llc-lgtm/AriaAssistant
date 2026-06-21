## Mixamo Animation Batcher Plugin
##
## Adds a "Mixamo Animation Batcher..." entry under the Tools menu.
## Opens a standalone window for batch importing Mixamo FBX animations.
##
## @author KarnesTH
## @version 1.0.0
@tool
extends EditorPlugin


const WINDOW_SCENE := preload("res://addons/mixamo_animation_batcher/ui/batcher.tscn")

var _window: Window = null


func _enter_tree() -> void:
	add_tool_menu_item("Mixamo Animation Batcher...", _open_window)


func _exit_tree() -> void:
	remove_tool_menu_item("Mixamo Animation Batcher...")
	if _window and is_instance_valid(_window):
		_window.queue_free()
		_window = null


func _open_window() -> void:
	if _window and is_instance_valid(_window):
		_window.show()
		_window.grab_focus()
		return

	_window = WINDOW_SCENE.instantiate()
	_window.close_requested.connect(_on_window_close_requested)
	EditorInterface.get_base_control().add_child(_window)
	_window.popup_centered(Vector2i(480, 600))


func _on_window_close_requested() -> void:
	if _window and is_instance_valid(_window):
		_window.hide()
