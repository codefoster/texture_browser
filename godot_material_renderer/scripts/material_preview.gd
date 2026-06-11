extends Node3D

@onready var sphere: MeshInstance3D = $Sphere
@onready var camera: Camera3D = $Camera3D

var output_path := ""
var hdri_debug_output := ""
var capture_requested := false
var capture_frame_delay := 8
var frames_waited := 0
var show_hdri_background := false
var scene_environment: Environment
var key_light: SpotLight3D
var default_preview_mesh: Mesh
var backdrop: MeshInstance3D
var backdrop_material: StandardMaterial3D
var hdri_reference: MeshInstance3D
var hdri_source_image: Image
var hdri_sky_material: PanoramaSkyMaterial
var hdri_texture: ImageTexture
var hdri_rotation_timer: Timer
var hdri_last_offset := -1
var preview_material: StandardMaterial3D
var albedo_source_image: Image
var normal_source_image: Image
var normal_flip_green := false
var height_source_image: Image
var height_enabled := false
var height_scale := 5.0
var height_invert := false
var roughness_source_image: Image
var roughness_mode := "original_red"
var ao_source_image: Image
var metallic_source_image: Image
var packed_source_image: Image
var packed_maps_enabled := false
var packed_ao_channel := "r"
var packed_roughness_channel := "g"
var packed_metallic_channel := "b"
var map_paths: Dictionary = {}
var map_sizes: Dictionary = {}
var controls_layer: CanvasLayer
var status_label: Label
var health_label: Label
var workflow_option: OptionButton
var packed_maps_check: CheckBox
var packed_ao_option: OptionButton
var packed_roughness_option: OptionButton
var packed_metallic_option: OptionButton
var uv_scale_label: Label
var height_scale_label: Label
var height_enabled_check: CheckBox
var height_invert_check: CheckBox
var roughness_label: Label
var ao_strength_label: Label
var roughness_mode_option: OptionButton
var hdri_rotation_label: Label
var hdri_brightness_label: Label
var key_light_label: Label
var export_dialog: FileDialog
var texture_import_dialog: FileDialog
var object_import_dialog: FileDialog
var preset_name_dialog: AcceptDialog
var preset_name_edit: LineEdit
var preview_preset_option: OptionButton
var lighting_preset_option: OptionButton
var pending_import_channel := ""
var export_directory := ""
var dragging_sphere := false
var scaling_sphere := false
var light_handle: Button
var dragging_light_handle := false
var light_handle_position := Vector2(-1.0, -1.0)
var solo_view_mode := "material"
var workflow_preset := "metal_rough"
var sphere_size := 1.0
var uv_scale := 1.0
var roughness_scale := 1.0
var ao_strength := 1.0
var albedo_only := false
var hdri_rotation_degrees := 0.0
var hdri_brightness := 1.15
var key_light_energy := 2.2
var background_color := Color(0.09, 0.10, 0.12)
const DEFAULT_HDRI_PATH := "res://assets/hdri/Ice_Lake_Ref.hdr"
const MAX_PREVIEW_CONTROL_MAP_SIZE := 512
const MAX_PREVIEW_TEXTURE_SIZE := 2048
const MAX_CUSTOM_OBJECT_TRIANGLES := 100000
const SETTINGS_PATH := "user://material_preview_settings.cfg"
const PRESET_SECTION := "preview_presets"


func _ready() -> void:
	var args: Dictionary = _parse_args(OS.get_cmdline_user_args())
	_load_viewer_settings()
	output_path = str(args.get("output", ""))
	hdri_debug_output = str(args.get("debug_save_hdri", ""))
	capture_requested = output_path != ""
	capture_frame_delay = int(str(args.get("capture_frames", "8")))
	if args.has("hdri_rotation"):
		hdri_rotation_degrees = float(str(args.get("hdri_rotation", "0.0")))
	show_hdri_background = _is_true(args.get("show_hdri_background", ""))
	if args.has("flip_normal_green"):
		normal_flip_green = _is_true(args.get("flip_normal_green", ""))
	if args.has("workflow"):
		workflow_preset = str(args.get("workflow", "metal_rough"))
	if args.has("roughness_mode"):
		roughness_mode = str(args.get("roughness_mode", "original_red"))
	if args.has("ao_strength"):
		ao_strength = float(str(args.get("ao_strength", "1.0")))
	albedo_only = _is_true(args.get("albedo_only", ""))
	if args.has("use_packed"):
		packed_maps_enabled = _is_true(args.get("use_packed", ""))
	if args.has("height_scale"):
		height_scale = float(str(args.get("height_scale", "5.0")))
	if args.has("invert_height"):
		height_invert = _is_true(args.get("invert_height", ""))
	if args.has("workflow") and not args.has("roughness_mode"):
		roughness_mode = _default_roughness_mode_for_workflow(workflow_preset)
	if _is_true(args.get("invert_roughness", "")):
		roughness_mode = "invert_red"

	_setup_scene()
	_apply_hdri(args)
	_apply_material(args)
	if args.has("object"):
		_import_preview_object(str(args.get("object", "")))

	if _is_true(args.get("show_hdri_reference", "")):
		_create_hdri_reference()
	if not capture_requested:
		_create_controls()


func _process(_delta: float) -> void:
	if not capture_requested:
		return

	frames_waited += 1
	if frames_waited < capture_frame_delay:
		return

	var image := get_viewport().get_texture().get_image()
	var error := image.save_png(output_path)
	if error != OK:
		push_error("Failed to save material preview PNG: %s" % output_path)
		get_tree().quit(1)
		return

	print("Saved material preview: %s" % output_path)
	get_tree().quit(0)


func _unhandled_input(event: InputEvent) -> void:
	if capture_requested:
		return

	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_WHEEL_UP and event.pressed:
		_set_sphere_size(sphere_size + 0.05)
		get_viewport().set_input_as_handled()
		return

	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_WHEEL_DOWN and event.pressed:
		_set_sphere_size(sphere_size - 0.05)
		get_viewport().set_input_as_handled()
		return

	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		scaling_sphere = event.pressed and event.alt_pressed
		dragging_sphere = event.pressed and not scaling_sphere
		get_viewport().set_input_as_handled()
		return

	if event is InputEventMouseMotion and scaling_sphere:
		_set_sphere_size(sphere_size + event.relative.x * 0.008)
		get_viewport().set_input_as_handled()
		return

	if event is InputEventMouseMotion and dragging_sphere:
		sphere.rotation_degrees.y += event.relative.x * 0.35
		sphere.rotation_degrees.x = clamp(sphere.rotation_degrees.x + event.relative.y * 0.25, -80.0, 80.0)
		get_viewport().set_input_as_handled()


func _setup_scene() -> void:
	default_preview_mesh = sphere.mesh
	camera.position = Vector3(0.0, 0.08, 3.0)
	camera.look_at(Vector3.ZERO, Vector3.UP)
	camera.current = true
	sphere.scale = Vector3.ONE * sphere_size
	sphere.rotation_degrees = Vector3(-8.0, 34.0, 0.0)
	if not show_hdri_background:
		_create_dark_backdrop()

	var world := WorldEnvironment.new()
	scene_environment = Environment.new()
	scene_environment.background_mode = Environment.BG_COLOR
	scene_environment.background_color = background_color
	scene_environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	scene_environment.ambient_light_color = Color(0.25, 0.27, 0.30)
	scene_environment.ambient_light_energy = 0.0
	world.environment = scene_environment
	add_child(world)

	var key := SpotLight3D.new()
	key.name = "KeyLight"
	key.light_energy = key_light_energy
	key.spot_range = 8.0
	key.spot_angle = 42.0
	key.spot_angle_attenuation = 0.35
	key_light = key
	add_child(key)


func _create_dark_backdrop() -> void:
	backdrop = MeshInstance3D.new()
	backdrop.name = "DarkBackdrop"
	var quad := QuadMesh.new()
	quad.size = Vector2(24.0, 24.0)
	backdrop.mesh = quad
	backdrop.position = Vector3(0.0, 0.0, -4.0)

	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = background_color
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	backdrop_material = material
	backdrop.set_surface_override_material(0, material)
	add_child(backdrop)


func _create_hdri_reference() -> void:
	hdri_reference = MeshInstance3D.new()
	hdri_reference.name = "HDRIReference"
	var reference_mesh := SphereMesh.new()
	reference_mesh.radius = 0.18
	reference_mesh.height = 0.36
	reference_mesh.radial_segments = 64
	reference_mesh.rings = 32
	hdri_reference.mesh = reference_mesh
	hdri_reference.position = Vector3(1.18, -0.72, 0.24)

	var reference_material := StandardMaterial3D.new()
	reference_material.albedo_color = Color(0.85, 0.88, 0.92)
	reference_material.metallic = 1.0
	reference_material.roughness = 0.03
	hdri_reference.set_surface_override_material(0, reference_material)
	add_child(hdri_reference)


func _apply_hdri(args: Dictionary) -> void:
	var hdri_path: String = str(args.get("hdri", ""))
	if hdri_path == "":
		hdri_path = DEFAULT_HDRI_PATH
	hdri_source_image = _load_image(hdri_path)
	if hdri_source_image == null or scene_environment == null:
		return

	hdri_sky_material = PanoramaSkyMaterial.new()
	_apply_hdri_rotation()
	_apply_hdri_brightness()

	var sky := Sky.new()
	sky.process_mode = Sky.PROCESS_MODE_REALTIME
	sky.radiance_size = Sky.RADIANCE_SIZE_256
	sky.sky_material = hdri_sky_material

	scene_environment.sky = sky
	scene_environment.background_mode = Environment.BG_SKY
	scene_environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	scene_environment.ambient_light_energy = hdri_brightness


func _apply_material(args: Dictionary) -> void:
	preview_material = StandardMaterial3D.new()
	preview_material.albedo_color = Color(0.62, 0.58, 0.52)
	preview_material.roughness = roughness_scale
	preview_material.metallic = 0.0
	preview_material.uv1_scale = Vector3(uv_scale, uv_scale, 1.0)

	albedo_source_image = _load_image(str(args.get("basecolor", "")))
	if albedo_source_image != null:
		_record_map_source("albedo", str(args.get("basecolor", "")), albedo_source_image)
		_limit_image_size(albedo_source_image, MAX_PREVIEW_TEXTURE_SIZE)
		preview_material.albedo_texture = ImageTexture.create_from_image(albedo_source_image)

	normal_source_image = _load_image(str(args.get("normal", "")))
	if normal_source_image != null:
		_record_map_source("normal", str(args.get("normal", "")), normal_source_image)
		_limit_image_size(normal_source_image, MAX_PREVIEW_TEXTURE_SIZE)
		_set_normal_texture()

	height_source_image = _load_image(str(args.get("height", "")))
	if height_source_image != null:
		_record_map_source("height", str(args.get("height", "")), height_source_image)
		_limit_image_size(height_source_image, MAX_PREVIEW_CONTROL_MAP_SIZE)
		height_enabled = not args.has("use_height") or _is_true(args.get("use_height", ""))
		_set_height_texture()

	roughness_source_image = _load_image(str(args.get("roughness", "")))
	if roughness_source_image != null:
		_record_map_source("roughness", str(args.get("roughness", "")), roughness_source_image)
		_limit_image_size(roughness_source_image, MAX_PREVIEW_CONTROL_MAP_SIZE)
		_set_roughness_texture()
		preview_material.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED

	metallic_source_image = _load_image(str(args.get("metallic", "")))
	if metallic_source_image != null:
		_record_map_source("metallic", str(args.get("metallic", "")), metallic_source_image)
		_limit_image_size(metallic_source_image, MAX_PREVIEW_CONTROL_MAP_SIZE)
		_set_metallic_texture()

	ao_source_image = _load_image(str(args.get("ao", "")))
	if ao_source_image != null:
		_record_map_source("ao", str(args.get("ao", "")), ao_source_image)
		_limit_image_size(ao_source_image, MAX_PREVIEW_CONTROL_MAP_SIZE)
		_set_ao_texture()

	packed_source_image = _load_image(str(args.get("packed", "")))
	if packed_source_image != null:
		_record_map_source("packed", str(args.get("packed", "")), packed_source_image)
		_limit_image_size(packed_source_image, MAX_PREVIEW_CONTROL_MAP_SIZE)
		_apply_material_channel_sources()

	sphere.set_surface_override_material(0, preview_material)
	_apply_view_mode()
	_update_health_check()


func _create_controls() -> void:
	controls_layer = CanvasLayer.new()
	controls_layer.name = "PreviewControls"
	add_child(controls_layer)

	var panel := PanelContainer.new()
	panel.position = Vector2(16.0, 16.0)
	panel.custom_minimum_size = Vector2(360.0, 0.0)
	var panel_style := StyleBoxFlat.new()
	panel_style.bg_color = Color(0.06, 0.07, 0.08, 0.88)
	panel_style.border_color = Color(0.24, 0.29, 0.34, 1.0)
	panel_style.set_border_width_all(1)
	panel_style.set_corner_radius_all(6)
	panel.add_theme_stylebox_override("panel", panel_style)
	controls_layer.add_child(panel)

	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 12)
	margin.add_theme_constant_override("margin_top", 10)
	margin.add_theme_constant_override("margin_right", 12)
	margin.add_theme_constant_override("margin_bottom", 10)
	panel.add_child(margin)

	var stack := VBoxContainer.new()
	stack.add_theme_constant_override("separation", 8)
	margin.add_child(stack)

	var workflow_row := HBoxContainer.new()
	workflow_row.add_theme_constant_override("separation", 8)
	stack.add_child(workflow_row)

	var workflow_label := Label.new()
	workflow_label.text = "Workflow"
	workflow_label.custom_minimum_size = Vector2(96.0, 0.0)
	workflow_row.add_child(workflow_label)

	workflow_option = OptionButton.new()
	workflow_option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	workflow_option.add_item("Metal / Rough")
	workflow_option.set_item_metadata(0, "metal_rough")
	workflow_option.add_item("Spec / Gloss")
	workflow_option.set_item_metadata(1, "spec_gloss")
	workflow_option.add_item("ORM packed")
	workflow_option.set_item_metadata(2, "orm")
	workflow_option.add_item("MRO packed")
	workflow_option.set_item_metadata(3, "mro")
	workflow_option.add_item("RMA packed")
	workflow_option.set_item_metadata(4, "rma")
	workflow_option.add_item("Diffuse / Normal")
	workflow_option.set_item_metadata(5, "diffuse_normal")
	workflow_option.select(_workflow_preset_index(workflow_preset))
	workflow_option.item_selected.connect(_on_workflow_selected)
	workflow_row.add_child(workflow_option)

	var sphere_hint := Label.new()
	sphere_hint.text = "Object scale: wheel or Alt+drag"
	stack.add_child(sphere_hint)
	uv_scale_label = _add_slider_row(stack, "UV scale", 0.1, 8.0, 0.1, uv_scale, _on_uv_scale_changed)
	height_scale_label = _add_slider_row(stack, "Height", 0.0, 12.0, 0.1, height_scale, _on_height_scale_changed)
	roughness_label = _add_slider_row(stack, "Roughness", 0.0, 1.0, 0.01, roughness_scale, _on_roughness_changed)
	ao_strength_label = _add_slider_row(stack, "AO strength", 0.0, 1.0, 0.01, ao_strength, _on_ao_strength_changed)
	hdri_rotation_label = _add_slider_row(stack, "HDRI rotate", 0.0, 360.0, 1.0, hdri_rotation_degrees, _on_hdri_rotation_changed)
	hdri_brightness_label = _add_slider_row(stack, "HDRI bright", 0.0, 100.0, 0.1, hdri_brightness, _on_hdri_brightness_changed)
	key_light_label = _add_slider_row(stack, "Key light", 0.0, 6.0, 0.05, key_light_energy, _on_key_light_energy_changed)

	var bg_label := Label.new()
	bg_label.text = "Background"
	stack.add_child(bg_label)

	var bg_row := HBoxContainer.new()
	bg_row.add_theme_constant_override("separation", 6)
	stack.add_child(bg_row)
	_add_background_swatch(bg_row, Color(1.0, 1.0, 1.0), "White")
	_add_background_swatch(bg_row, Color(0.78, 0.78, 0.78), "Light gray")
	_add_background_swatch(bg_row, Color(0.56, 0.56, 0.56), "Mid light")
	_add_background_swatch(bg_row, Color(0.34, 0.34, 0.34), "Mid dark")
	_add_background_swatch(bg_row, Color(0.12, 0.12, 0.12), "Dark gray")
	_add_background_swatch(bg_row, Color(0.0, 0.0, 0.0), "Black")

	var lighting_row := HBoxContainer.new()
	lighting_row.add_theme_constant_override("separation", 8)
	stack.add_child(lighting_row)

	var lighting_label := Label.new()
	lighting_label.text = "Lighting"
	lighting_label.custom_minimum_size = Vector2(96.0, 0.0)
	lighting_row.add_child(lighting_label)

	lighting_preset_option = OptionButton.new()
	lighting_preset_option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lighting_preset_option.add_item("Custom")
	lighting_preset_option.set_item_metadata(0, "custom")
	lighting_preset_option.add_item("Studio")
	lighting_preset_option.set_item_metadata(1, "studio")
	lighting_preset_option.add_item("Outdoor HDRI")
	lighting_preset_option.set_item_metadata(2, "outdoor")
	lighting_preset_option.add_item("Grazing side")
	lighting_preset_option.set_item_metadata(3, "grazing")
	lighting_preset_option.add_item("Top light")
	lighting_preset_option.set_item_metadata(4, "top")
	lighting_preset_option.add_item("Bottom light")
	lighting_preset_option.set_item_metadata(5, "bottom")
	lighting_preset_option.add_item("Neutral flat")
	lighting_preset_option.set_item_metadata(6, "neutral")
	lighting_preset_option.item_selected.connect(_on_lighting_preset_selected)
	lighting_row.add_child(lighting_preset_option)

	var solo_label := Label.new()
	solo_label.text = "Solo map"
	stack.add_child(solo_label)

	var solo_row_one := HBoxContainer.new()
	solo_row_one.add_theme_constant_override("separation", 6)
	stack.add_child(solo_row_one)
	_add_solo_button(solo_row_one, "Mat", "material")
	_add_solo_button(solo_row_one, "Albedo", "albedo")
	_add_solo_button(solo_row_one, "Rough", "roughness")
	_add_solo_button(solo_row_one, "Normal", "normal")

	var solo_row_two := HBoxContainer.new()
	solo_row_two.add_theme_constant_override("separation", 6)
	stack.add_child(solo_row_two)
	_add_solo_button(solo_row_two, "AO", "ao")
	_add_solo_button(solo_row_two, "Height", "height")
	_add_solo_button(solo_row_two, "Metal", "metallic")
	_add_solo_button(solo_row_two, "Packed", "packed")

	var flip_normal_check := CheckBox.new()
	flip_normal_check.text = "Flip normal green"
	flip_normal_check.button_pressed = normal_flip_green
	flip_normal_check.toggled.connect(_on_flip_normal_green_toggled)
	stack.add_child(flip_normal_check)

	var height_row := HBoxContainer.new()
	height_row.add_theme_constant_override("separation", 8)
	stack.add_child(height_row)

	height_enabled_check = CheckBox.new()
	height_enabled_check.text = "Use height"
	height_enabled_check.button_pressed = height_enabled
	height_enabled_check.toggled.connect(_on_height_enabled_toggled)
	height_row.add_child(height_enabled_check)

	height_invert_check = CheckBox.new()
	height_invert_check.text = "Invert height"
	height_invert_check.button_pressed = height_invert
	height_invert_check.toggled.connect(_on_height_invert_toggled)
	height_row.add_child(height_invert_check)

	var albedo_only_check := CheckBox.new()
	albedo_only_check.text = "Albedo only"
	albedo_only_check.button_pressed = albedo_only
	albedo_only_check.toggled.connect(_on_albedo_only_toggled)
	stack.add_child(albedo_only_check)

	var roughness_mode_row := HBoxContainer.new()
	roughness_mode_row.add_theme_constant_override("separation", 8)
	stack.add_child(roughness_mode_row)

	var roughness_mode_label := Label.new()
	roughness_mode_label.text = "Rough mode"
	roughness_mode_label.custom_minimum_size = Vector2(96.0, 0.0)
	roughness_mode_row.add_child(roughness_mode_label)

	roughness_mode_option = OptionButton.new()
	roughness_mode_option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	roughness_mode_option.add_item("Original red")
	roughness_mode_option.set_item_metadata(0, "original_red")
	roughness_mode_option.add_item("Grayscale")
	roughness_mode_option.set_item_metadata(1, "grayscale")
	roughness_mode_option.add_item("Invert red")
	roughness_mode_option.set_item_metadata(2, "invert_red")
	roughness_mode_option.add_item("Invert grayscale")
	roughness_mode_option.set_item_metadata(3, "invert_grayscale")
	roughness_mode_option.select(_roughness_mode_index(roughness_mode))
	roughness_mode_option.item_selected.connect(_on_roughness_mode_selected)
	roughness_mode_row.add_child(roughness_mode_option)

	packed_maps_check = CheckBox.new()
	packed_maps_check.text = "Use packed channels"
	packed_maps_check.button_pressed = packed_maps_enabled
	packed_maps_check.toggled.connect(_on_packed_maps_toggled)
	stack.add_child(packed_maps_check)

	var packed_row := HBoxContainer.new()
	packed_row.add_theme_constant_override("separation", 6)
	stack.add_child(packed_row)
	packed_ao_option = _add_channel_option(packed_row, "AO", packed_ao_channel, _on_packed_ao_channel_selected)
	packed_roughness_option = _add_channel_option(packed_row, "Rough", packed_roughness_channel, _on_packed_roughness_channel_selected)
	packed_metallic_option = _add_channel_option(packed_row, "Metal", packed_metallic_channel, _on_packed_metallic_channel_selected)
	_update_packed_channel_controls()

	var import_label := Label.new()
	import_label.text = "Import maps"
	stack.add_child(import_label)

	var clear_maps_button := Button.new()
	clear_maps_button.text = "Clear maps"
	clear_maps_button.pressed.connect(_on_clear_maps_pressed)
	stack.add_child(clear_maps_button)

	var import_row_one := HBoxContainer.new()
	import_row_one.add_theme_constant_override("separation", 6)
	stack.add_child(import_row_one)
	_add_import_button(import_row_one, "Albedo", "albedo")
	_add_import_button(import_row_one, "Normal", "normal")
	_add_import_button(import_row_one, "Rough", "roughness")

	var import_row_two := HBoxContainer.new()
	import_row_two.add_theme_constant_override("separation", 6)
	stack.add_child(import_row_two)
	_add_import_button(import_row_two, "Metal", "metallic")
	_add_import_button(import_row_two, "AO", "ao")
	_add_import_button(import_row_two, "Packed", "packed")

	var import_row_three := HBoxContainer.new()
	import_row_three.add_theme_constant_override("separation", 6)
	stack.add_child(import_row_three)
	_add_import_button(import_row_three, "Height", "height")
	_add_object_button(import_row_three, "Object")
	_add_reset_object_button(import_row_three, "Sphere")

	var preset_row := HBoxContainer.new()
	preset_row.add_theme_constant_override("separation", 6)
	stack.add_child(preset_row)

	preview_preset_option = OptionButton.new()
	preview_preset_option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	preset_row.add_child(preview_preset_option)

	var load_preset_button := Button.new()
	load_preset_button.text = "Load"
	load_preset_button.pressed.connect(_on_load_preview_preset_pressed)
	preset_row.add_child(load_preset_button)

	var save_preset_button := Button.new()
	save_preset_button.text = "Save"
	save_preset_button.pressed.connect(_on_save_preview_preset_pressed)
	preset_row.add_child(save_preset_button)

	health_label = Label.new()
	health_label.text = "Health: checking..."
	health_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	health_label.custom_minimum_size = Vector2(330.0, 0.0)
	stack.add_child(health_label)

	var button_row := HBoxContainer.new()
	button_row.add_theme_constant_override("separation", 8)
	stack.add_child(button_row)

	var folder_button := Button.new()
	folder_button.text = "Browse Folder"
	folder_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	folder_button.pressed.connect(_on_browse_export_folder_pressed)
	button_row.add_child(folder_button)

	var export_button := Button.new()
	export_button.text = "Export Image"
	export_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	export_button.pressed.connect(_on_export_pressed)
	button_row.add_child(export_button)

	status_label = Label.new()
	if export_directory == "":
		export_directory = _default_export_dir()
	status_label.text = "Export: %s" % export_directory
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status_label.custom_minimum_size = Vector2(330.0, 0.0)
	stack.add_child(status_label)

	_create_export_dialog()
	_create_texture_import_dialog()
	_create_object_import_dialog()
	_create_preset_name_dialog()
	_create_light_handle()
	_refresh_preview_preset_option()
	_update_control_labels()
	_update_health_check()


func _add_slider_row(parent: VBoxContainer, title: String, min_value: float, max_value: float, step: float, value: float, callback: Callable) -> Label:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	parent.add_child(row)

	var label := Label.new()
	label.custom_minimum_size = Vector2(96.0, 0.0)
	row.add_child(label)

	var slider := HSlider.new()
	slider.min_value = min_value
	slider.max_value = max_value
	slider.step = step
	slider.value = value
	slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slider.value_changed.connect(callback)
	row.add_child(slider)

	label.set_meta("title", title)
	return label


func _add_import_button(parent: HBoxContainer, text: String, channel: String) -> void:
	var button := Button.new()
	button.text = text
	button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	button.pressed.connect(_on_import_button_pressed.bind(channel))
	parent.add_child(button)


func _add_object_button(parent: HBoxContainer, text: String) -> void:
	var button := Button.new()
	button.text = text
	button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	button.tooltip_text = "Import an OBJ preview object, capped at %d triangles" % MAX_CUSTOM_OBJECT_TRIANGLES
	button.pressed.connect(_on_import_object_pressed)
	parent.add_child(button)


func _add_reset_object_button(parent: HBoxContainer, text: String) -> void:
	var button := Button.new()
	button.text = text
	button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	button.tooltip_text = "Reset the preview object to the default sphere"
	button.pressed.connect(_on_reset_object_pressed)
	parent.add_child(button)


func _add_solo_button(parent: HBoxContainer, text: String, mode: String) -> void:
	var button := Button.new()
	button.text = text
	button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	button.pressed.connect(_on_solo_button_pressed.bind(mode))
	parent.add_child(button)


func _add_channel_option(parent: HBoxContainer, label_text: String, selected_channel: String, callback: Callable) -> OptionButton:
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	parent.add_child(column)

	var label := Label.new()
	label.text = label_text
	column.add_child(label)

	var option := OptionButton.new()
	option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	option.add_item("R")
	option.set_item_metadata(0, "r")
	option.add_item("G")
	option.set_item_metadata(1, "g")
	option.add_item("B")
	option.set_item_metadata(2, "b")
	option.add_item("A")
	option.set_item_metadata(3, "a")
	option.select(_channel_index(selected_channel))
	option.item_selected.connect(callback)
	column.add_child(option)
	return option


func _add_background_swatch(parent: HBoxContainer, color: Color, tooltip: String) -> void:
	var button := Button.new()
	button.custom_minimum_size = Vector2(34.0, 28.0)
	button.tooltip_text = tooltip
	var style := StyleBoxFlat.new()
	style.bg_color = color
	style.border_color = Color(0.18, 0.20, 0.23)
	style.set_border_width_all(1)
	style.set_corner_radius_all(4)
	button.add_theme_stylebox_override("normal", style)
	button.add_theme_stylebox_override("hover", style)
	button.add_theme_stylebox_override("pressed", style)
	button.pressed.connect(_on_background_swatch_pressed.bind(color))
	parent.add_child(button)


func _on_background_swatch_pressed(color: Color) -> void:
	background_color = color
	if scene_environment != null:
		scene_environment.background_color = background_color
	if backdrop_material != null:
		backdrop_material.albedo_color = background_color
	_save_viewer_settings()


func _on_solo_button_pressed(mode: String) -> void:
	solo_view_mode = mode
	_apply_view_mode()
	_set_status("Solo view: %s" % mode.capitalize())
	_save_viewer_settings()


func _texture_for_solo_mode(mode: String) -> Texture2D:
	match mode:
		"albedo":
			return _texture_from_image(albedo_source_image)
		"normal":
			return _texture_from_image(normal_source_image)
		"roughness":
			return _texture_from_image(roughness_source_image)
		"ao":
			return _texture_from_image(ao_source_image)
		"height":
			return _texture_from_image(height_source_image)
		"metallic":
			return _texture_from_image(metallic_source_image)
		"packed":
			return _texture_from_image(packed_source_image)
		_:
			return null


func _create_light_handle() -> void:
	light_handle = Button.new()
	light_handle.text = "O"
	light_handle.tooltip_text = "Drag around the sphere to orbit the spotlight"
	light_handle.custom_minimum_size = Vector2(36.0, 36.0)
	light_handle.size = Vector2(36.0, 36.0)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.95, 0.88, 0.42, 0.95)
	style.border_color = Color(0.18, 0.16, 0.08, 1.0)
	style.set_border_width_all(1)
	style.set_corner_radius_all(18)
	light_handle.add_theme_stylebox_override("normal", style)
	light_handle.add_theme_stylebox_override("hover", style)
	light_handle.add_theme_stylebox_override("pressed", style)
	if light_handle_position.x >= 0.0 and light_handle_position.y >= 0.0:
		light_handle.position = light_handle_position
	else:
		_position_light_handle_default()
	light_handle.gui_input.connect(_on_light_handle_input)
	controls_layer.add_child(light_handle)
	_update_key_light_from_handle()


func _on_light_handle_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		dragging_light_handle = event.pressed
		light_handle.accept_event()
		return

	if event is InputEventMouseMotion and dragging_light_handle:
		var next_position: Vector2 = light_handle.position + event.relative
		var viewport_size: Vector2 = get_viewport().get_visible_rect().size
		next_position.x = clamp(next_position.x, 8.0, maxf(8.0, viewport_size.x - light_handle.size.x - 8.0))
		next_position.y = clamp(next_position.y, 8.0, maxf(8.0, viewport_size.y - light_handle.size.y - 8.0))
		light_handle.position = next_position
		light_handle_position = next_position
		_update_key_light_from_handle()
		_save_viewer_settings()
		light_handle.accept_event()


func _position_light_handle_default() -> void:
	if light_handle == null:
		return
	var viewport_size: Vector2 = get_viewport().get_visible_rect().size
	light_handle.position = Vector2(
		maxf(8.0, viewport_size.x - light_handle.size.x - 88.0),
		maxf(8.0, viewport_size.y - light_handle.size.y - 88.0)
	)
	light_handle_position = light_handle.position


func _update_key_light_from_handle() -> void:
	if key_light == null or light_handle == null:
		return
	var viewport_size: Vector2 = get_viewport().get_visible_rect().size
	var center: Vector2 = light_handle.position + light_handle.size * 0.5
	var object_center: Vector2 = viewport_size * 0.5
	var direction_2d: Vector2 = center - object_center
	if direction_2d.length() < 4.0:
		direction_2d = Vector2(1.0, 1.0)
	direction_2d = direction_2d.normalized()
	key_light.position = Vector3(direction_2d.x * 3.0, -direction_2d.y * 2.35, 2.6)
	key_light.look_at(Vector3.ZERO, Vector3.UP)


func _on_lighting_preset_selected(index: int) -> void:
	if lighting_preset_option == null:
		return
	var preset: String = str(lighting_preset_option.get_item_metadata(index))
	_apply_lighting_preset(preset)
	_save_viewer_settings()


func _apply_lighting_preset(preset: String) -> void:
	match preset:
		"studio":
			_set_lighting_values(1.6, 2.4, Vector2(0.72, 0.28), Color(0.09, 0.10, 0.12))
		"outdoor":
			_set_lighting_values(5.5, 1.1, Vector2(0.78, 0.26), Color(0.12, 0.14, 0.16))
		"grazing":
			_set_lighting_values(0.8, 4.6, Vector2(0.95, 0.52), Color(0.05, 0.055, 0.06))
		"top":
			_set_lighting_values(0.7, 3.6, Vector2(0.50, 0.06), Color(0.08, 0.085, 0.09))
		"bottom":
			_set_lighting_values(0.4, 3.6, Vector2(0.50, 0.94), Color(0.04, 0.045, 0.05))
		"neutral":
			_set_lighting_values(0.0, 2.2, Vector2(0.74, 0.32), Color(0.34, 0.34, 0.34))
		_:
			return
	_update_control_labels()
	_set_status("Lighting preset: %s" % preset.capitalize())


func _set_lighting_values(hdri_value: float, key_value: float, handle_normalized: Vector2, bg_color: Color) -> void:
	hdri_brightness = hdri_value
	key_light_energy = key_value
	background_color = bg_color
	if scene_environment != null:
		scene_environment.background_color = background_color
	if backdrop_material != null:
		backdrop_material.albedo_color = background_color
	if key_light != null:
		key_light.light_energy = key_light_energy
	if light_handle != null:
		var viewport_size: Vector2 = get_viewport().get_visible_rect().size
		light_handle_position = Vector2(
			clamp(handle_normalized.x, 0.0, 1.0) * viewport_size.x - light_handle.size.x * 0.5,
			clamp(handle_normalized.y, 0.0, 1.0) * viewport_size.y - light_handle.size.y * 0.5
		)
		light_handle.position = light_handle_position
		_update_key_light_from_handle()
	_apply_hdri_brightness()


func _on_workflow_selected(index: int) -> void:
	if workflow_option == null:
		return
	workflow_preset = str(workflow_option.get_item_metadata(index))
	_apply_workflow_preset()
	_save_viewer_settings()


func _apply_workflow_preset() -> void:
	match workflow_preset:
		"metal_rough":
			_set_roughness_mode("original_red")
			_set_status("Workflow: Metal/Rough")
		"spec_gloss":
			_set_roughness_mode("invert_red")
			_set_status("Workflow: Spec/Gloss, Rough slot reads gloss inverted")
		"diffuse_normal":
			if preview_material != null:
				preview_material.metallic = 0.0
				preview_material.metallic_texture = null
				preview_material.roughness_texture = null
				preview_material.ao_enabled = false
				preview_material.ao_texture = null
				_apply_view_mode()
			_set_status("Workflow: Diffuse/Normal only")
		"orm":
			_set_packed_channels("r", "g", "b")
			_set_status("Workflow: ORM, import a packed map")
		"mro":
			_set_packed_channels("b", "g", "r")
			_set_status("Workflow: MRO, import a packed map")
		"rma":
			_set_packed_channels("b", "r", "g")
			_set_status("Workflow: RMA, import a packed map")
		_:
			_set_status("Workflow selected")


func _set_roughness_mode(mode: String) -> void:
	roughness_mode = mode
	if roughness_mode_option != null:
		roughness_mode_option.select(_roughness_mode_index(roughness_mode))
	_apply_material_channel_sources()


func _workflow_preset_index(preset: String) -> int:
	match preset:
		"spec_gloss":
			return 1
		"orm":
			return 2
		"mro":
			return 3
		"rma":
			return 4
		"diffuse_normal":
			return 5
		_:
			return 0


func _set_packed_channels(ao_channel: String, roughness_channel: String, metallic_channel: String) -> void:
	packed_ao_channel = ao_channel
	packed_roughness_channel = roughness_channel
	packed_metallic_channel = metallic_channel
	if packed_ao_option != null:
		packed_ao_option.select(_channel_index(packed_ao_channel))
	if packed_roughness_option != null:
		packed_roughness_option.select(_channel_index(packed_roughness_channel))
	if packed_metallic_option != null:
		packed_metallic_option.select(_channel_index(packed_metallic_channel))
	_update_packed_channel_controls()
	_apply_material_channel_sources()


func _channel_index(channel: String) -> int:
	match channel:
		"g":
			return 1
		"b":
			return 2
		"a":
			return 3
		_:
			return 0


func _channel_from_option(option: OptionButton, index: int) -> String:
	if option == null:
		return "r"
	return str(option.get_item_metadata(index))


func _default_roughness_mode_for_workflow(preset: String) -> String:
	match preset:
		"spec_gloss":
			return "invert_red"
		_:
			return "original_red"


func _on_sphere_size_changed(value: float) -> void:
	_set_sphere_size(value)


func _set_sphere_size(value: float) -> void:
	sphere_size = clamp(value, 0.35, 1.8)
	if sphere != null:
		sphere.scale = Vector3.ONE * sphere_size
	_update_control_labels()
	_save_viewer_settings()


func _on_uv_scale_changed(value: float) -> void:
	uv_scale = value
	if preview_material != null:
		preview_material.uv1_scale = Vector3(uv_scale, uv_scale, 1.0)
	_update_control_labels()
	_save_viewer_settings()


func _on_height_scale_changed(value: float) -> void:
	height_scale = value
	_set_height_texture()
	_update_control_labels()
	_save_viewer_settings()


func _on_height_enabled_toggled(enabled: bool) -> void:
	height_enabled = enabled
	_set_height_texture()
	_apply_view_mode()
	_save_viewer_settings()


func _on_height_invert_toggled(enabled: bool) -> void:
	height_invert = enabled
	_set_height_texture()
	_apply_view_mode()
	_save_viewer_settings()


func _set_height_texture() -> void:
	if preview_material == null:
		return
	if height_source_image == null or not height_enabled:
		preview_material.heightmap_enabled = false
		preview_material.heightmap_texture = null
		return

	preview_material.heightmap_enabled = true
	preview_material.heightmap_scale = height_scale
	preview_material.heightmap_flip_texture = height_invert
	preview_material.heightmap_texture = ImageTexture.create_from_image(height_source_image)


func _on_roughness_changed(value: float) -> void:
	roughness_scale = value
	if preview_material != null:
		preview_material.roughness = roughness_scale
	_update_control_labels()
	_save_viewer_settings()


func _on_ao_strength_changed(value: float) -> void:
	ao_strength = value
	_apply_material_channel_sources()
	_update_control_labels()
	_save_viewer_settings()


func _set_ao_texture() -> void:
	if preview_material == null or ao_source_image == null:
		return
	_set_ao_texture_from_image(ao_source_image)


func _set_ao_texture_from_image(source_image: Image) -> void:
	if preview_material == null or source_image == null:
		return

	var adjusted: Image = Image.create(source_image.get_width(), source_image.get_height(), false, Image.FORMAT_RGB8)
	for y in range(source_image.get_height()):
		for x in range(source_image.get_width()):
			var pixel: Color = source_image.get_pixel(x, y)
			var ao_value: float = clamp((pixel.r + pixel.g + pixel.b) / 3.0, 0.0, 1.0)
			ao_value = lerpf(1.0, ao_value, ao_strength)
			adjusted.set_pixel(x, y, Color(ao_value, ao_value, ao_value, 1.0))

	preview_material.ao_enabled = ao_strength > 0.0
	preview_material.ao_texture = ImageTexture.create_from_image(adjusted)
	preview_material.ao_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED


func _on_albedo_only_toggled(enabled: bool) -> void:
	albedo_only = enabled
	_apply_view_mode()
	_save_viewer_settings()


func _apply_view_mode() -> void:
	if preview_material == null:
		return
	if solo_view_mode != "material":
		var solo_texture: Texture2D = _texture_for_solo_mode(solo_view_mode)
		preview_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		preview_material.albedo_texture = solo_texture
		preview_material.albedo_color = Color.WHITE
		preview_material.normal_enabled = false
		preview_material.heightmap_enabled = false
		preview_material.roughness_texture = null
		preview_material.metallic = 0.0
		preview_material.metallic_texture = null
		preview_material.ao_enabled = false
		preview_material.ao_texture = null
		return

	_restore_material_view()
	if albedo_only:
		preview_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	else:
		preview_material.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL


func _restore_material_view() -> void:
	if preview_material == null:
		return
	if albedo_source_image != null:
		preview_material.albedo_texture = ImageTexture.create_from_image(albedo_source_image)
	else:
		preview_material.albedo_texture = null
		preview_material.albedo_color = Color(0.62, 0.58, 0.52)
	if normal_source_image != null:
		_set_normal_texture()
	else:
		preview_material.normal_enabled = false
		preview_material.normal_texture = null
	_set_height_texture()
	_apply_material_channel_sources()


func _on_hdri_brightness_changed(value: float) -> void:
	hdri_brightness = value
	_apply_hdri_brightness()
	_update_control_labels()
	_save_viewer_settings()


func _apply_hdri_brightness() -> void:
	if scene_environment != null:
		scene_environment.ambient_light_energy = hdri_brightness
	if hdri_sky_material != null:
		hdri_sky_material.energy_multiplier = hdri_brightness


func _on_key_light_energy_changed(value: float) -> void:
	key_light_energy = value
	if key_light != null:
		key_light.light_energy = key_light_energy
	_update_control_labels()
	_save_viewer_settings()


func _on_flip_normal_green_toggled(enabled: bool) -> void:
	normal_flip_green = enabled
	_set_normal_texture()
	_apply_view_mode()
	_update_health_check()
	_save_viewer_settings()


func _set_normal_texture() -> void:
	if preview_material == null or normal_source_image == null:
		return

	var image: Image = normal_source_image
	if normal_flip_green:
		image = normal_source_image.duplicate()
		image.convert(Image.FORMAT_RGBA8)
		for y in range(image.get_height()):
			for x in range(image.get_width()):
				var pixel: Color = image.get_pixel(x, y)
				pixel.g = 1.0 - pixel.g
				image.set_pixel(x, y, pixel)

	preview_material.normal_enabled = true
	preview_material.normal_texture = ImageTexture.create_from_image(image)
	preview_material.normal_scale = 1.0


func _on_roughness_mode_selected(index: int) -> void:
	if roughness_mode_option == null:
		return
	roughness_mode = str(roughness_mode_option.get_item_metadata(index))
	_apply_material_channel_sources()
	_apply_view_mode()
	_update_health_check()
	_save_viewer_settings()


func _set_roughness_texture() -> void:
	if preview_material == null or roughness_source_image == null:
		return
	_set_roughness_texture_from_image(roughness_source_image)


func _set_roughness_texture_from_image(source_image: Image) -> void:
	if preview_material == null or source_image == null:
		return

	var scalar_map: Image = Image.create(source_image.get_width(), source_image.get_height(), false, Image.FORMAT_RGB8)
	for y in range(source_image.get_height()):
		for x in range(source_image.get_width()):
			var pixel: Color = source_image.get_pixel(x, y)
			var roughness_value: float = pixel.r
			if roughness_mode == "grayscale" or roughness_mode == "invert_grayscale":
				roughness_value = (pixel.r + pixel.g + pixel.b) / 3.0
			roughness_value = clamp(roughness_value, 0.0, 1.0)
			if roughness_mode == "invert_red" or roughness_mode == "invert_grayscale":
				roughness_value = 1.0 - roughness_value
			scalar_map.set_pixel(x, y, Color(roughness_value, roughness_value, roughness_value, 1.0))
	preview_material.roughness_texture = ImageTexture.create_from_image(scalar_map)
	preview_material.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED


func _set_metallic_texture() -> void:
	if preview_material == null or metallic_source_image == null:
		return
	_set_metallic_texture_from_image(metallic_source_image)


func _set_metallic_texture_from_image(source_image: Image) -> void:
	if preview_material == null or source_image == null:
		return
	preview_material.metallic = 1.0
	preview_material.metallic_texture = ImageTexture.create_from_image(source_image)
	preview_material.metallic_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED


func _roughness_mode_index(mode: String) -> int:
	match mode:
		"grayscale":
			return 1
		"invert_red":
			return 2
		"invert_grayscale":
			return 3
		_:
			return 0


func _on_packed_ao_channel_selected(index: int) -> void:
	packed_ao_channel = _channel_from_option(packed_ao_option, index)
	_apply_material_channel_sources()
	_apply_view_mode()
	_save_viewer_settings()


func _on_packed_roughness_channel_selected(index: int) -> void:
	packed_roughness_channel = _channel_from_option(packed_roughness_option, index)
	_apply_material_channel_sources()
	_apply_view_mode()
	_save_viewer_settings()


func _on_packed_metallic_channel_selected(index: int) -> void:
	packed_metallic_channel = _channel_from_option(packed_metallic_option, index)
	_apply_material_channel_sources()
	_apply_view_mode()
	_save_viewer_settings()


func _on_packed_maps_toggled(enabled: bool) -> void:
	packed_maps_enabled = enabled
	_update_packed_channel_controls()
	_apply_material_channel_sources()
	_apply_view_mode()
	_save_viewer_settings()
	if packed_maps_enabled:
		_set_status("Packed channels enabled")
	else:
		_set_status("Packed channels ignored")


func _update_packed_channel_controls() -> void:
	if packed_ao_option != null:
		packed_ao_option.disabled = not packed_maps_enabled
	if packed_roughness_option != null:
		packed_roughness_option.disabled = not packed_maps_enabled
	if packed_metallic_option != null:
		packed_metallic_option.disabled = not packed_maps_enabled


func _apply_material_channel_sources() -> void:
	if preview_material == null:
		return

	if packed_maps_enabled and packed_source_image != null:
		_apply_packed_map()
		return

	if ao_source_image != null:
		_set_ao_texture_from_image(ao_source_image)
	else:
		preview_material.ao_enabled = false
		preview_material.ao_texture = null

	if roughness_source_image != null:
		_set_roughness_texture_from_image(roughness_source_image)
	else:
		preview_material.roughness_texture = null

	if metallic_source_image != null:
		_set_metallic_texture_from_image(metallic_source_image)
	else:
		preview_material.metallic = 0.0
		preview_material.metallic_texture = null


func _apply_packed_map() -> void:
	if preview_material == null or packed_source_image == null or not packed_maps_enabled:
		return

	var packed_ao_image: Image = _extract_channel_image(packed_source_image, packed_ao_channel, false)
	_set_ao_texture_from_image(packed_ao_image)

	var packed_roughness_image: Image = _extract_channel_image(packed_source_image, packed_roughness_channel, false)
	_set_roughness_texture_from_image(packed_roughness_image)

	preview_material.metallic = 1.0
	preview_material.metallic_texture = _extract_channel_texture(packed_source_image, packed_metallic_channel, false)
	preview_material.metallic_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED


func _extract_channel_texture(source: Image, channel: String, invert: bool) -> Texture2D:
	return ImageTexture.create_from_image(_extract_channel_image(source, channel, invert))


func _extract_channel_image(source: Image, channel: String, invert: bool) -> Image:
	var image: Image = Image.create(source.get_width(), source.get_height(), false, Image.FORMAT_RGB8)
	for y in range(source.get_height()):
		for x in range(source.get_width()):
			var pixel: Color = source.get_pixel(x, y)
			var value: float = _channel_value(pixel, channel)
			if invert:
				value = 1.0 - value
			image.set_pixel(x, y, Color(value, value, value, 1.0))
	return image


func _channel_value(pixel: Color, channel: String) -> float:
	match channel:
		"g":
			return pixel.g
		"b":
			return pixel.b
		"a":
			return pixel.a
		_:
			return pixel.r


func _on_hdri_rotation_changed(value: float) -> void:
	hdri_rotation_degrees = value
	_schedule_hdri_rotation_update()
	_update_control_labels()
	_save_viewer_settings()


func _schedule_hdri_rotation_update() -> void:
	if capture_requested:
		_apply_hdri_rotation()
		return
	if hdri_rotation_timer == null:
		hdri_rotation_timer = Timer.new()
		hdri_rotation_timer.one_shot = true
		hdri_rotation_timer.wait_time = 0.18
		hdri_rotation_timer.timeout.connect(_apply_hdri_rotation)
		add_child(hdri_rotation_timer)
	hdri_rotation_timer.start()


func _apply_hdri_rotation() -> void:
	if scene_environment == null:
		return
	scene_environment.sky_rotation = Vector3(0.0, deg_to_rad(hdri_rotation_degrees), 0.0)
	if hdri_source_image == null or hdri_sky_material == null:
		return

	var width := hdri_source_image.get_width()
	var height := hdri_source_image.get_height()
	if width <= 0 or height <= 0:
		return

	var offset := int(round(float(width) * (hdri_rotation_degrees / 360.0))) % width
	if offset == hdri_last_offset and hdri_texture != null:
		return
	hdri_last_offset = offset

	if offset == 0:
		hdri_texture = ImageTexture.create_from_image(hdri_source_image)
		hdri_sky_material.panorama = hdri_texture
		if scene_environment.sky != null:
			scene_environment.sky.sky_material = hdri_sky_material
		return

	var rotated: Image = Image.create(width, height, false, hdri_source_image.get_format())
	rotated.blit_rect(hdri_source_image, Rect2i(offset, 0, width - offset, height), Vector2i(0, 0))
	rotated.blit_rect(hdri_source_image, Rect2i(0, 0, offset, height), Vector2i(width - offset, 0))

	var runtime_dir := ProjectSettings.globalize_path("res://temp_material/runtime_hdri")
	var dir_error := DirAccess.make_dir_recursive_absolute(runtime_dir)
	if dir_error != OK:
		push_warning("Could not create runtime HDRI directory: %s" % runtime_dir)
		return

	var rotated_path := runtime_dir.path_join("rotated_hdri_%03d.png" % offset)
	var save_image: Image = rotated.duplicate()
	save_image.convert(Image.FORMAT_RGB8)
	var save_error: int = save_image.save_png(rotated_path)
	if save_error != OK:
		push_warning("Could not save rotated HDRI: %s" % rotated_path)
		return

	hdri_texture = _load_texture(rotated_path)
	if hdri_texture == null:
		return
	hdri_sky_material.panorama = hdri_texture
	if scene_environment.sky != null:
		scene_environment.sky.sky_material = hdri_sky_material
	if hdri_debug_output != "":
		rotated.save_png(hdri_debug_output)


func _update_control_labels() -> void:
	if uv_scale_label != null:
		uv_scale_label.text = "%s %.2fx" % [uv_scale_label.get_meta("title"), uv_scale]
	if height_scale_label != null:
		height_scale_label.text = "%s %.1f" % [height_scale_label.get_meta("title"), height_scale]
	if roughness_label != null:
		roughness_label.text = "%s %.2f" % [roughness_label.get_meta("title"), roughness_scale]
	if ao_strength_label != null:
		ao_strength_label.text = "%s %.2f" % [ao_strength_label.get_meta("title"), ao_strength]
	if hdri_rotation_label != null:
		hdri_rotation_label.text = "%s %.0f" % [hdri_rotation_label.get_meta("title"), hdri_rotation_degrees]
	if hdri_brightness_label != null:
		hdri_brightness_label.text = "%s %.2f" % [hdri_brightness_label.get_meta("title"), hdri_brightness]
	if key_light_label != null:
		key_light_label.text = "%s %.2f" % [key_light_label.get_meta("title"), key_light_energy]


func _set_status(text: String) -> void:
	if status_label != null:
		status_label.text = text


func _on_export_pressed() -> void:
	_export_preview()


func _on_browse_export_folder_pressed() -> void:
	if export_dialog == null:
		return
	export_dialog.current_dir = export_directory
	export_dialog.popup_centered_ratio(0.72)


func _on_import_button_pressed(channel: String) -> void:
	if texture_import_dialog == null:
		return
	pending_import_channel = channel
	texture_import_dialog.title = "Import %s Map" % channel.capitalize()
	texture_import_dialog.popup_centered_ratio(0.72)


func _on_clear_maps_pressed() -> void:
	if preview_material == null:
		return

	normal_source_image = null
	albedo_source_image = null
	height_source_image = null
	roughness_source_image = null
	ao_source_image = null
	packed_source_image = null
	metallic_source_image = null
	map_paths.clear()
	map_sizes.clear()
	packed_maps_enabled = false
	if packed_maps_check != null:
		packed_maps_check.button_pressed = false
	height_enabled = false
	if height_enabled_check != null:
		height_enabled_check.button_pressed = false
	preview_material.albedo_texture = null
	preview_material.albedo_color = Color(0.62, 0.58, 0.52)
	preview_material.normal_enabled = false
	preview_material.normal_texture = null
	preview_material.heightmap_enabled = false
	preview_material.heightmap_texture = null
	preview_material.roughness_texture = null
	preview_material.metallic = 0.0
	preview_material.metallic_texture = null
	preview_material.ao_enabled = false
	preview_material.ao_texture = null
	if status_label != null:
		status_label.text = "Cleared material maps"
	_update_health_check()


func _create_export_dialog() -> void:
	export_dialog = FileDialog.new()
	export_dialog.title = "Choose Export Folder"
	export_dialog.file_mode = FileDialog.FILE_MODE_OPEN_DIR
	export_dialog.access = FileDialog.ACCESS_FILESYSTEM
	export_dialog.dir_selected.connect(_on_export_folder_selected)
	controls_layer.add_child(export_dialog)


func _create_texture_import_dialog() -> void:
	texture_import_dialog = FileDialog.new()
	texture_import_dialog.title = "Import Texture Map"
	texture_import_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	texture_import_dialog.access = FileDialog.ACCESS_FILESYSTEM
	texture_import_dialog.filters = PackedStringArray([
		"*.png, *.jpg, *.jpeg, *.tif, *.tiff, *.bmp, *.tga, *.hdr, *.exr ; Texture files"
	])
	texture_import_dialog.file_selected.connect(_on_texture_file_selected)
	controls_layer.add_child(texture_import_dialog)


func _create_object_import_dialog() -> void:
	object_import_dialog = FileDialog.new()
	object_import_dialog.title = "Import Preview Object"
	object_import_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	object_import_dialog.access = FileDialog.ACCESS_FILESYSTEM
	object_import_dialog.filters = PackedStringArray([
		"*.obj ; Wavefront OBJ files"
	])
	object_import_dialog.file_selected.connect(_on_object_file_selected)
	controls_layer.add_child(object_import_dialog)


func _create_preset_name_dialog() -> void:
	preset_name_dialog = AcceptDialog.new()
	preset_name_dialog.title = "Save Preview Preset"
	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 12)
	margin.add_theme_constant_override("margin_top", 12)
	margin.add_theme_constant_override("margin_right", 12)
	margin.add_theme_constant_override("margin_bottom", 12)
	preset_name_edit = LineEdit.new()
	preset_name_edit.placeholder_text = "Preset name"
	preset_name_edit.text = "Material Preview"
	margin.add_child(preset_name_edit)
	preset_name_dialog.add_child(margin)
	preset_name_dialog.confirmed.connect(_on_preset_name_confirmed)
	controls_layer.add_child(preset_name_dialog)


func _on_save_preview_preset_pressed() -> void:
	if preset_name_dialog == null:
		return
	preset_name_dialog.popup_centered(Vector2i(360, 120))


func _on_preset_name_confirmed() -> void:
	if preset_name_edit == null:
		return
	var preset_name: String = preset_name_edit.text.strip_edges()
	if preset_name == "":
		return
	var config := ConfigFile.new()
	config.load(SETTINGS_PATH)
	_write_settings_section(config, "%s/%s" % [PRESET_SECTION, preset_name])
	config.save(SETTINGS_PATH)
	_refresh_preview_preset_option()
	_set_status("Saved preset: %s" % preset_name)


func _on_load_preview_preset_pressed() -> void:
	if preview_preset_option == null or preview_preset_option.item_count == 0:
		return
	var preset_name: String = str(preview_preset_option.get_item_text(preview_preset_option.selected))
	var config := ConfigFile.new()
	if config.load(SETTINGS_PATH) != OK:
		return
	var section := "%s/%s" % [PRESET_SECTION, preset_name]
	if not config.has_section(section):
		return
	_read_settings_section(config, section)
	_apply_saved_settings_to_scene()
	_save_viewer_settings()
	_set_status("Loaded preset: %s" % preset_name)


func _refresh_preview_preset_option() -> void:
	if preview_preset_option == null:
		return
	preview_preset_option.clear()
	var config := ConfigFile.new()
	if config.load(SETTINGS_PATH) != OK:
		preview_preset_option.add_item("No presets")
		preview_preset_option.disabled = true
		return
	var names: Array[String] = []
	for section in config.get_sections():
		var section_name: String = str(section)
		var prefix := "%s/" % PRESET_SECTION
		if section_name.begins_with(prefix):
			names.append(section_name.substr(prefix.length()))
	names.sort()
	if names.is_empty():
		preview_preset_option.add_item("No presets")
		preview_preset_option.disabled = true
		return
	preview_preset_option.disabled = false
	for name in names:
		preview_preset_option.add_item(name)


func _on_export_folder_selected(path: String) -> void:
	export_directory = path
	if status_label != null:
		status_label.text = "Export: %s" % export_directory
	_save_viewer_settings()


func _on_texture_file_selected(path: String) -> void:
	_import_texture_map(pending_import_channel, path)


func _on_import_object_pressed() -> void:
	if object_import_dialog == null:
		return
	object_import_dialog.popup_centered_ratio(0.72)


func _on_reset_object_pressed() -> void:
	if default_preview_mesh == null:
		return
	sphere.mesh = default_preview_mesh
	if preview_material != null:
		sphere.set_surface_override_material(0, preview_material)
	_set_sphere_size(sphere_size)
	_set_status("Preview object: default sphere")


func _on_object_file_selected(path: String) -> void:
	_import_preview_object(path)


func _import_texture_map(channel: String, path: String) -> void:
	if preview_material == null:
		return

	var image: Image = _load_image(path)
	if image == null:
		if status_label != null:
			status_label.text = "Import failed: %s" % path
		return

	match channel:
		"albedo":
			_record_map_source("albedo", path, image)
			_limit_image_size(image, MAX_PREVIEW_TEXTURE_SIZE)
			albedo_source_image = image
			preview_material.albedo_texture = ImageTexture.create_from_image(albedo_source_image)
		"normal":
			_record_map_source("normal", path, image)
			_limit_image_size(image, MAX_PREVIEW_TEXTURE_SIZE)
			normal_source_image = image
			_set_normal_texture()
		"height":
			_record_map_source("height", path, image)
			_limit_image_size(image, MAX_PREVIEW_CONTROL_MAP_SIZE)
			height_source_image = image
			height_enabled = true
			if height_enabled_check != null:
				height_enabled_check.button_pressed = true
			_set_height_texture()
		"roughness":
			_record_map_source("roughness", path, image)
			_limit_image_size(image, MAX_PREVIEW_CONTROL_MAP_SIZE)
			roughness_source_image = image
			_apply_material_channel_sources()
		"metallic":
			_record_map_source("metallic", path, image)
			_limit_image_size(image, MAX_PREVIEW_CONTROL_MAP_SIZE)
			metallic_source_image = image
			_apply_material_channel_sources()
		"ao":
			_record_map_source("ao", path, image)
			_limit_image_size(image, MAX_PREVIEW_CONTROL_MAP_SIZE)
			ao_source_image = image
			_apply_material_channel_sources()
		"packed":
			_record_map_source("packed", path, image)
			_limit_image_size(image, MAX_PREVIEW_CONTROL_MAP_SIZE)
			packed_source_image = image
			_apply_material_channel_sources()
		_:
			return

	if status_label != null:
		status_label.text = "Imported %s: %s" % [channel, path.get_file()]
	_apply_view_mode()
	_update_health_check()


func _import_preview_object(path: String) -> void:
	var mesh: ArrayMesh = _load_obj_preview_mesh(path)
	if mesh == null:
		return
	sphere.mesh = mesh
	if preview_material != null:
		sphere.set_surface_override_material(0, preview_material)
	_set_sphere_size(sphere_size)
	_set_status("Preview object: %s" % path.get_file())


func _load_obj_preview_mesh(path: String) -> ArrayMesh:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		_set_status("Object import failed: could not open OBJ")
		return null

	var positions: Array[Vector3] = []
	var uvs: Array[Vector2] = []
	var normals: Array[Vector3] = []
	var faces: Array = []
	var min_point := Vector3(INF, INF, INF)
	var max_point := Vector3(-INF, -INF, -INF)
	var triangle_count := 0

	while not file.eof_reached():
		var line := file.get_line().strip_edges()
		if line == "" or line.begins_with("#"):
			continue
		var parts := line.split(" ", false)
		if parts.is_empty():
			continue
		match parts[0]:
			"v":
				if parts.size() >= 4:
					var position := Vector3(float(parts[1]), float(parts[2]), float(parts[3]))
					positions.append(position)
					min_point = min_point.min(position)
					max_point = max_point.max(position)
			"vt":
				if parts.size() >= 3:
					uvs.append(Vector2(float(parts[1]), 1.0 - float(parts[2])))
			"vn":
				if parts.size() >= 4:
					normals.append(Vector3(float(parts[1]), float(parts[2]), float(parts[3])).normalized())
			"f":
				if parts.size() >= 4:
					var face: Array[String] = []
					for index in range(1, parts.size()):
						face.append(str(parts[index]))
					triangle_count += face.size() - 2
					if triangle_count > MAX_CUSTOM_OBJECT_TRIANGLES:
						_set_status("Object import stopped: %d+ triangles exceeds limit %d" % [triangle_count, MAX_CUSTOM_OBJECT_TRIANGLES])
						return null
					faces.append(face)

	if positions.is_empty() or faces.is_empty():
		_set_status("Object import failed: OBJ has no usable mesh")
		return null

	var extent: Vector3 = max_point - min_point
	var max_extent: float = maxf(maxf(extent.x, extent.y), extent.z)
	if max_extent <= 0.0001:
		_set_status("Object import failed: OBJ bounds are too small")
		return null
	var center: Vector3 = (min_point + max_point) * 0.5
	var fit_scale: float = 2.0 / max_extent

	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	var has_any_normals := false
	for face in faces:
		var face_tokens: Array = face
		for index in range(1, face_tokens.size() - 1):
			has_any_normals = _add_obj_vertex(surface, face_tokens[0], positions, uvs, normals, center, fit_scale) or has_any_normals
			has_any_normals = _add_obj_vertex(surface, face_tokens[index], positions, uvs, normals, center, fit_scale) or has_any_normals
			has_any_normals = _add_obj_vertex(surface, face_tokens[index + 1], positions, uvs, normals, center, fit_scale) or has_any_normals
	if not has_any_normals:
		surface.generate_normals()
	var mesh: ArrayMesh = surface.commit()
	return mesh


func _add_obj_vertex(surface: SurfaceTool, token: String, positions: Array[Vector3], uvs: Array[Vector2], normals: Array[Vector3], center: Vector3, fit_scale: float) -> bool:
	var indices := token.split("/", true)
	if indices.is_empty():
		return false
	var position_index: int = _resolve_obj_index(str(indices[0]), positions.size())
	if position_index < 0 or position_index >= positions.size():
		return false
	var has_normal := false
	if indices.size() >= 2 and str(indices[1]) != "":
		var uv_index: int = _resolve_obj_index(str(indices[1]), uvs.size())
		if uv_index >= 0 and uv_index < uvs.size():
			surface.set_uv(uvs[uv_index])
	if indices.size() >= 3 and str(indices[2]) != "":
		var normal_index: int = _resolve_obj_index(str(indices[2]), normals.size())
		if normal_index >= 0 and normal_index < normals.size():
			surface.set_normal(normals[normal_index])
			has_normal = true
	var position: Vector3 = (positions[position_index] - center) * fit_scale
	surface.add_vertex(position)
	return has_normal


func _resolve_obj_index(text: String, item_count: int) -> int:
	if text.strip_edges() == "":
		return -1
	var raw_index := int(text)
	if raw_index > 0:
		return raw_index - 1
	if raw_index < 0:
		return item_count + raw_index
	return -1


func _export_preview() -> void:
	if status_label != null:
		status_label.text = "Exporting..."
	if controls_layer != null:
		controls_layer.visible = false
	if hdri_reference != null:
		hdri_reference.visible = false

	await get_tree().process_frame
	await get_tree().process_frame

	var export_dir := export_directory
	var dir_error := DirAccess.make_dir_recursive_absolute(export_dir)
	var export_path := export_dir.path_join("material_preview_%s.png" % _safe_timestamp())

	var image := get_viewport().get_texture().get_image()
	var save_error := ERR_CANT_CREATE
	if dir_error == OK:
		save_error = image.save_png(export_path)

	if controls_layer != null:
		controls_layer.visible = true
	if hdri_reference != null:
		hdri_reference.visible = true
	if status_label != null:
		if save_error == OK:
			status_label.text = "Exported: %s" % export_path
		else:
			status_label.text = "Export failed."


func _default_export_dir() -> String:
	var pictures_dir := OS.get_system_dir(OS.SYSTEM_DIR_PICTURES)
	if pictures_dir == "":
		pictures_dir = OS.get_user_data_dir()
	return pictures_dir.path_join("Texture Browser Material Previews")


func _safe_timestamp() -> String:
	return Time.get_datetime_string_from_system(false, true).replace(":", "-")


func _load_viewer_settings() -> void:
	var config := ConfigFile.new()
	if config.load(SETTINGS_PATH) != OK:
		return
	_read_settings_section(config, "settings")


func _save_viewer_settings() -> void:
	if capture_requested:
		return
	var config := ConfigFile.new()
	config.load(SETTINGS_PATH)
	_write_settings_section(config, "settings")
	config.save(SETTINGS_PATH)


func _write_settings_section(config: ConfigFile, section: String) -> void:
	config.set_value(section, "sphere_size", sphere_size)
	config.set_value(section, "uv_scale", uv_scale)
	config.set_value(section, "height_scale", height_scale)
	config.set_value(section, "height_enabled", height_enabled)
	config.set_value(section, "height_invert", height_invert)
	config.set_value(section, "roughness_scale", roughness_scale)
	config.set_value(section, "roughness_mode", roughness_mode)
	config.set_value(section, "ao_strength", ao_strength)
	config.set_value(section, "hdri_rotation", hdri_rotation_degrees)
	config.set_value(section, "hdri_brightness", hdri_brightness)
	config.set_value(section, "key_light_energy", key_light_energy)
	config.set_value(section, "background_color", background_color)
	config.set_value(section, "normal_flip_green", normal_flip_green)
	config.set_value(section, "packed_maps_enabled", packed_maps_enabled)
	config.set_value(section, "packed_ao_channel", packed_ao_channel)
	config.set_value(section, "packed_roughness_channel", packed_roughness_channel)
	config.set_value(section, "packed_metallic_channel", packed_metallic_channel)
	config.set_value(section, "workflow_preset", workflow_preset)
	config.set_value(section, "solo_view_mode", solo_view_mode)
	config.set_value(section, "albedo_only", albedo_only)
	config.set_value(section, "export_directory", export_directory)
	config.set_value(section, "light_handle_position", light_handle_position)


func _read_settings_section(config: ConfigFile, section: String) -> void:
	if not config.has_section(section):
		return
	sphere_size = float(config.get_value(section, "sphere_size", sphere_size))
	uv_scale = float(config.get_value(section, "uv_scale", uv_scale))
	height_scale = float(config.get_value(section, "height_scale", height_scale))
	height_enabled = bool(config.get_value(section, "height_enabled", height_enabled))
	height_invert = bool(config.get_value(section, "height_invert", height_invert))
	roughness_scale = float(config.get_value(section, "roughness_scale", roughness_scale))
	roughness_mode = str(config.get_value(section, "roughness_mode", roughness_mode))
	ao_strength = float(config.get_value(section, "ao_strength", ao_strength))
	hdri_rotation_degrees = float(config.get_value(section, "hdri_rotation", hdri_rotation_degrees))
	hdri_brightness = float(config.get_value(section, "hdri_brightness", hdri_brightness))
	key_light_energy = float(config.get_value(section, "key_light_energy", key_light_energy))
	background_color = config.get_value(section, "background_color", background_color)
	normal_flip_green = bool(config.get_value(section, "normal_flip_green", normal_flip_green))
	packed_maps_enabled = bool(config.get_value(section, "packed_maps_enabled", packed_maps_enabled))
	packed_ao_channel = str(config.get_value(section, "packed_ao_channel", packed_ao_channel))
	packed_roughness_channel = str(config.get_value(section, "packed_roughness_channel", packed_roughness_channel))
	packed_metallic_channel = str(config.get_value(section, "packed_metallic_channel", packed_metallic_channel))
	workflow_preset = str(config.get_value(section, "workflow_preset", workflow_preset))
	solo_view_mode = str(config.get_value(section, "solo_view_mode", solo_view_mode))
	albedo_only = bool(config.get_value(section, "albedo_only", albedo_only))
	export_directory = str(config.get_value(section, "export_directory", export_directory))
	light_handle_position = config.get_value(section, "light_handle_position", light_handle_position)


func _apply_saved_settings_to_scene() -> void:
	_set_sphere_size(sphere_size)
	if preview_material != null:
		preview_material.uv1_scale = Vector3(uv_scale, uv_scale, 1.0)
		preview_material.roughness = roughness_scale
	if scene_environment != null:
		scene_environment.background_color = background_color
	if backdrop_material != null:
		backdrop_material.albedo_color = background_color
	if key_light != null:
		key_light.light_energy = key_light_energy
	if light_handle != null:
		light_handle.position = light_handle_position
		_update_key_light_from_handle()
	if workflow_option != null:
		workflow_option.select(_workflow_preset_index(workflow_preset))
	if roughness_mode_option != null:
		roughness_mode_option.select(_roughness_mode_index(roughness_mode))
	if packed_maps_check != null:
		packed_maps_check.button_pressed = packed_maps_enabled
	if height_enabled_check != null:
		height_enabled_check.button_pressed = height_enabled
	if height_invert_check != null:
		height_invert_check.button_pressed = height_invert
	_apply_hdri_brightness()
	_schedule_hdri_rotation_update()
	_set_packed_channels(packed_ao_channel, packed_roughness_channel, packed_metallic_channel)
	_update_packed_channel_controls()
	_set_height_texture()
	_apply_view_mode()
	_update_control_labels()


func _load_texture(path: String) -> Texture2D:
	var image := _load_image(path)
	if image == null:
		return null

	return ImageTexture.create_from_image(image)


func _texture_from_image(image: Image) -> Texture2D:
	if image == null:
		return null
	return ImageTexture.create_from_image(image)


func _record_map_source(role: String, path: String, image: Image) -> void:
	if image == null:
		return
	if path.strip_edges() != "":
		map_paths[role] = path
	map_sizes[role] = Vector2i(image.get_width(), image.get_height())


func _update_health_check() -> void:
	if health_label == null:
		return
	var warnings: Array[String] = []
	if albedo_source_image == null:
		warnings.append("missing albedo")
	_add_dimension_warnings(warnings)
	_add_content_warnings(warnings)
	if warnings.is_empty():
		health_label.text = "Health: OK"
	else:
		health_label.text = "Health: %s" % ", ".join(warnings)


func _add_dimension_warnings(warnings: Array[String]) -> void:
	var unique_sizes: Dictionary = {}
	for role in map_sizes.keys():
		var size: Vector2i = map_sizes[role] as Vector2i
		if size.x <= 0 or size.y <= 0:
			warnings.append("%s has invalid size" % role)
			continue
		if size.x != size.y:
			warnings.append("%s non-square %dx%d" % [role, size.x, size.y])
		if size.x > 16384 or size.y > 16384:
			warnings.append("%s over 16K" % role)
		unique_sizes["%dx%d" % [size.x, size.y]] = true
	if unique_sizes.size() > 1:
		warnings.append("mismatched resolutions")


func _add_content_warnings(warnings: Array[String]) -> void:
	if ao_source_image != null and _average_luma(ao_source_image) < 0.28:
		warnings.append("AO very dark")
	if roughness_source_image != null:
		var rough_average: float = _average_luma(roughness_source_image)
		if rough_average < 0.32 and not roughness_mode.begins_with("invert"):
			warnings.append("roughness mostly dark, maybe gloss/inverted")
		if rough_average > 0.82 and roughness_mode.begins_with("invert"):
			warnings.append("inverted roughness may be too glossy")
	var normal_path: String = str(map_paths.get("normal", "")).to_lower()
	if normal_path.contains("directx") or normal_path.contains("_dx") or normal_path.contains("-dx"):
		if not normal_flip_green:
			warnings.append("normal looks DirectX, flip green may be needed")
	if normal_path.contains("opengl") or normal_path.contains("_gl") or normal_path.contains("-gl"):
		if normal_flip_green:
			warnings.append("normal looks OpenGL, green flip may be wrong")


func _average_luma(image: Image) -> float:
	if image == null:
		return 0.0
	var width: int = image.get_width()
	var height: int = image.get_height()
	if width <= 0 or height <= 0:
		return 0.0
	var step_x: int = maxi(1, int(width / 48))
	var step_y: int = maxi(1, int(height / 48))
	var total := 0.0
	var count := 0
	for y in range(0, height, step_y):
		for x in range(0, width, step_x):
			var pixel: Color = image.get_pixel(x, y)
			total += (pixel.r + pixel.g + pixel.b) / 3.0
			count += 1
	if count == 0:
		return 0.0
	return total / float(count)


func _limit_image_size(image: Image, max_dimension: int) -> void:
	var width: int = image.get_width()
	var height: int = image.get_height()
	var max_size: int = maxi(width, height)
	if max_size <= max_dimension:
		return
	var scale: float = float(max_dimension) / float(max_size)
	var resized_width: int = maxi(1, int(round(float(width) * scale)))
	var resized_height: int = maxi(1, int(round(float(height) * scale)))
	image.resize(resized_width, resized_height, Image.INTERPOLATE_LANCZOS)


func _load_image(path: String) -> Image:
	if path.strip_edges() == "":
		return null

	var image := Image.new()
	var error := image.load(path)
	if error != OK:
		push_warning("Could not load texture: %s" % path)
		return null

	return image


func _parse_args(raw_args: PackedStringArray) -> Dictionary:
	var parsed := {}
	var index := 0
	while index < raw_args.size():
		var token := raw_args[index]
		if token.begins_with("--"):
			var key_value := token.substr(2).split("=", false, 1)
			if key_value.size() == 2:
				parsed[key_value[0].to_lower()] = key_value[1]
			elif index + 1 < raw_args.size() and not raw_args[index + 1].begins_with("--"):
				parsed[key_value[0].to_lower()] = raw_args[index + 1]
				index += 1
			else:
				parsed[key_value[0].to_lower()] = "true"
		index += 1
	return parsed


func _is_true(value: Variant) -> bool:
	var text := str(value).strip_edges().to_lower()
	return text == "1" or text == "true" or text == "yes" or text == "on"
