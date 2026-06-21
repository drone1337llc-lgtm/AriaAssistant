## Mixamo Animation Batcher Window
##
## Standalone editor window for batch importing Mixamo FBX animations.
## Opens via Project → Tools → "Mixamo Animation Batcher..."
##
## Requires a sample_bone_map.tres in the plugin folder with a correctly
## mapped SkeletonProfileHumanoid for Mixamo rigs.
##
## @author KarnesTH
## @version 1.0.0
@tool
extends Window


@onready var _source_path: LineEdit = %SourcePath
@onready var _source_browse_folder: Button = %SourceBrowseFolder
@onready var _source_browse_files: Button = %SourceBrowseFiles
@onready var _export_path: LineEdit = %ExportPath
@onready var _export_browse: Button = %ExportBrowse
@onready var _found_label: Label = %FoundLabel
@onready var _file_list: ItemList = %FileList
@onready var _progress_bar: ProgressBar = %ProgressBar
@onready var _status_label: Label = %StatusLabel
@onready var _start_btn: Button = %StartBtn
@onready var _clear_btn: Button = %ClearBtn

var _source_folder_dialog: FileDialog = null
var _source_files_dialog: FileDialog = null
var _export_dialog: FileDialog = null
var _overwrite_dialog: ConfirmationDialog = null
var _fbx_files: Array[String] = []
var _overwrite_all: bool = false


func _ready() -> void:
	_source_browse_folder.pressed.connect(_on_source_browse_folder_pressed)
	_source_browse_files.pressed.connect(_on_source_browse_files_pressed)
	_export_browse.pressed.connect(_on_export_browse_pressed)
	_start_btn.pressed.connect(_on_start_pressed)
	_clear_btn.pressed.connect(_on_clear_pressed)
	_progress_bar.value = 0.0
	_start_btn.disabled = true
	_set_status("Select source and export folders to begin.")
	
	_source_folder_dialog = FileDialog.new()
	_source_folder_dialog.file_mode = FileDialog.FILE_MODE_OPEN_DIR
	_source_folder_dialog.access = FileDialog.ACCESS_RESOURCES
	_source_folder_dialog.title = "Select FBX Source Folder"
	_source_folder_dialog.dir_selected.connect(_on_source_dir_selected)
	add_child(_source_folder_dialog)
	
	_source_files_dialog = FileDialog.new()
	_source_files_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILES
	_source_files_dialog.access = FileDialog.ACCESS_RESOURCES
	_source_files_dialog.title = "Select FBX Files"
	_source_files_dialog.filters = PackedStringArray(["*.fbx ; FBX Files"])
	_source_files_dialog.files_selected.connect(_on_source_files_selected)
	add_child(_source_files_dialog)
	
	_export_dialog = FileDialog.new()
	_export_dialog.file_mode = FileDialog.FILE_MODE_OPEN_DIR
	_export_dialog.access = FileDialog.ACCESS_RESOURCES
	_export_dialog.title = "Select Export Folder for .res Files"
	_export_dialog.dir_selected.connect(_on_export_dir_selected)
	add_child(_export_dialog)
	
	_overwrite_dialog = ConfirmationDialog.new()
	_overwrite_dialog.title = "File Already Exists"
	_overwrite_dialog.add_button("Yes to All", true, "yes_to_all")
	_overwrite_dialog.add_button("Skip", true, "skip")
	_overwrite_dialog.custom_action.connect(_on_overwrite_custom_action)
	add_child(_overwrite_dialog)


func _on_source_browse_folder_pressed() -> void:
	_source_folder_dialog.popup_centered_ratio(0.6)


func _on_source_browse_files_pressed() -> void:
	_source_files_dialog.popup_centered_ratio(0.6)


func _on_export_browse_pressed() -> void:
	_export_dialog.popup_centered_ratio(0.6)


func _on_source_dir_selected(dir: String) -> void:
	_source_path.text = dir
	_scan_for_fbx(dir)
	_validate_start_btn()


## Called when individual FBX files are selected via the file picker.
func _on_source_files_selected(paths: PackedStringArray) -> void:
	_fbx_files.clear()
	_file_list.clear()
	for path in paths:
		_fbx_files.append(path)
		_file_list.add_item(path.get_file())
	_source_path.text = paths[0].get_base_dir() if paths.size() > 0 else ""
	_found_label.text = "Found FBX Files: %d" % _fbx_files.size()
	_set_status("%d FBX file(s) selected." % _fbx_files.size())
	_validate_start_btn()


func _on_export_dir_selected(dir: String) -> void:
	_export_path.text = dir
	_validate_start_btn()


## Scans [param dir] for .fbx files and populates the file list.
func _scan_for_fbx(dir: String) -> void:
	_fbx_files.clear()
	_file_list.clear()
	
	var da := DirAccess.open(dir)
	if da == null:
		_set_status("Could not open source folder.")
		return
	
	da.list_dir_begin()
	var file := da.get_next()
	while file != "":
		if not da.current_is_dir() and file.to_lower().ends_with(".fbx"):
			_fbx_files.append(dir.path_join(file))
			_file_list.add_item(file)
		file = da.get_next()
	da.list_dir_end()
	
	_found_label.text = "Found FBX Files: %d" % _fbx_files.size()
	if _fbx_files.is_empty():
		_set_status("No FBX files found in selected folder.")
	else:
		_set_status("%d FBX file(s) ready to import." % _fbx_files.size())


## Enables the start button only when both folders are set and FBX files were found.
func _validate_start_btn() -> void:
	_start_btn.disabled = _export_path.text.is_empty() or _fbx_files.is_empty()


## Iterates over all found FBX files, applies import settings for each,
## then triggers a single reimport and refreshes the filesystem.
func _on_start_pressed() -> void:
	if _fbx_files.is_empty():
		return
	
	_start_btn.disabled = true
	_clear_btn.disabled = true
	_progress_bar.value = 0.0
	_overwrite_all = false
	var export_dir := _export_path.text
	
	for i in _fbx_files.size():
		var fbx_path := _fbx_files[i]
		var file_name := fbx_path.get_file().get_basename()
		var res_path := export_dir.path_join(_to_snake_case(file_name) + ".res")
		
		if not _overwrite_all and FileAccess.file_exists(res_path):
			var should_overwrite := await _ask_overwrite(file_name)
			if not should_overwrite:
				_set_status("Skipped: %s" % file_name)
				_progress_bar.value = float(i + 1) / float(_fbx_files.size()) * 100.0
				continue
		
		_set_status("Processing: %s (%d / %d)" % [file_name, i + 1, _fbx_files.size()])
		_file_list.select(i)
		_apply_import_settings(fbx_path, export_dir)
		_progress_bar.value = float(i + 1) / float(_fbx_files.size()) * 100.0
		await get_tree().process_frame
	
	await _trigger_reimport()
	_set_status("Done! %d animations processed." % _fbx_files.size())
	_start_btn.disabled = false
	_clear_btn.disabled = false
	await get_tree().create_timer(1.5).timeout
	hide()


## Shows a confirmation dialog asking whether to overwrite [param file_name].
## Returns true if the user chooses to overwrite, false to skip.
var _overwrite_result: bool = false
var _overwrite_resolved: bool = false

func _ask_overwrite(file_name: String) -> bool:
	_overwrite_resolved = false
	_overwrite_dialog.dialog_text = '"%s.res" already exists. Overwrite?' % file_name
	_overwrite_dialog.popup_centered()
	_overwrite_dialog.confirmed.connect(_on_overwrite_confirmed, CONNECT_ONE_SHOT)
	while not _overwrite_resolved:
		await get_tree().process_frame
	return _overwrite_result


func _on_overwrite_confirmed() -> void:
	_overwrite_result = true
	_overwrite_resolved = true


func _on_overwrite_custom_action(action: StringName) -> void:
	if action == "yes_to_all":
		_overwrite_all = true
		_overwrite_result = true
	else:
		_overwrite_result = false
	_overwrite_resolved = true
	_overwrite_dialog.hide()


## Writes retargeting and animation save settings into the .import config
## for [param fbx_path], targeting [param export_dir] for the .res output.
## Sets SkeletonProfileHumanoid bone map, enables bone renaming, and
## activates save_to_file for the mixamo_com animation track.
func _apply_import_settings(fbx_path: String, export_dir: String) -> void:
	var import_path := fbx_path + ".import"
	var config := ConfigFile.new()
	
	if config.load(import_path) != OK:
		push_warning("MixamoBatcher: Could not load import file: %s" % import_path)
		return
	
	var subresources: Dictionary = config.get_value("params", "_subresources", {})
	
	if "nodes" not in subresources:
		subresources["nodes"] = {}
	if "PATH:Skeleton3D" not in subresources["nodes"]:
		subresources["nodes"]["PATH:Skeleton3D"] = {}
	
	var skel: Dictionary = subresources["nodes"]["PATH:Skeleton3D"]
	skel["retarget/bone_map"] = _create_bone_map()
	skel["retarget/bone_renamer/unique_node/skeleton_name"] = "Skeleton"
	skel["retarget/bone_renamer/rename_bones"] = true
	skel["retarget/remove_tracks/unmapped_bones"] = true
	subresources["nodes"]["PATH:Skeleton3D"] = skel
	
	if "animations" not in subresources:
		subresources["animations"] = {}
	if "mixamo_com" not in subresources["animations"]:
		subresources["animations"]["mixamo_com"] = {}
	
	var res_path := export_dir.path_join(_to_snake_case(fbx_path.get_file().get_basename()) + ".res")
	var anim: Dictionary = subresources["animations"]["mixamo_com"]
	anim["save_to_file/enabled"] = true
	anim["save_to_file/path"] = res_path
	anim["save_to_file/fallback_path"] = res_path
	anim["save_to_file/keep_custom_tracks"] = ""
	anim["settings/loop_mode"] = 1
	subresources["animations"]["mixamo_com"] = anim
	
	config.set_value("params", "_subresources", subresources)
	
	if config.save(import_path) != OK:
		push_warning("MixamoBatcher: Could not save import file: %s" % import_path)


## Loads the pre-configured sample_bone_map.tres and duplicates its profile
## so each FBX import gets an independent copy of the SkeletonProfileHumanoid.
func _create_bone_map() -> BoneMap:
	var source: BoneMap = load("res://addons/mixamo_animation_batcher/sample_bone_map.tres")
	var bm: BoneMap = source.duplicate(true)
	bm.resource_local_to_scene = true
	bm.profile.resource_local_to_scene = true
	return bm


## Triggers a single reimport of all processed FBX files, waits for
## the filesystem to finish, then runs a scan so newly created .res files
## appear in the FileSystem dock.
func _trigger_reimport() -> void:
	var fs := EditorInterface.get_resource_filesystem()
	fs.reimport_files(_fbx_files)
	await fs.filesystem_changed
	await get_tree().create_timer(2.0).timeout
	fs.scan()


## Resets all UI fields and internal state.
func _on_clear_pressed() -> void:
	_source_path.text = ""
	_export_path.text = ""
	_fbx_files.clear()
	_file_list.clear()
	_found_label.text = "Found FBX Files: 0"
	_progress_bar.value = 0.0
	_overwrite_all = false
	_start_btn.disabled = true
	_set_status("Select source and export folders to begin.")


## Converts [param text] to snake_case for use as a .res filename.
func _to_snake_case(text: String) -> String:
	var result := ""
	var prev_lower := false
	for i in text.length():
		var c := text[i]
		if c == " ":
			if result and result[-1] != "_":
				result += "_"
		elif c >= "A" and c <= "Z":
			if prev_lower and result and result[-1] != "_":
				result += "_"
			result += c.to_lower()
			prev_lower = false
		else:
			result += c.to_lower()
			prev_lower = true
	return result


## Updates the status label with [param msg].
func _set_status(msg: String) -> void:
	_status_label.text = msg
