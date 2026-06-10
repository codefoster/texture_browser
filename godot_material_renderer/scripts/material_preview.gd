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
var key_light: DirectionalLight3D
var backdrop: MeshInstance3D
var backdrop_material: StandardMaterial3D
var hdri_reference: MeshInstance3D
var hdri_source_image: Image
var hdri_sky_material: PanoramaSkyMaterial
var hdri_texture: ImageTexture
var hdri_rotation_timer: Timer
var hdri_last_offset := -1
var preview_material: StandardMaterial3D
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
var controls_layer: CanvasLayer
var status_label: Label
var workflow_option: OptionButton
var packed_maps_check: CheckBox
var packed_ao_option: OptionButton
var packed_roughness_option: OptionButton
var packed_metallic_option: OptionButton
var sphere_size_label: Label
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
var pending_import_channel := ""
var export_directory := ""
var dragging_sphere := false
var light_handle: Button
var dragging_light_handle := false
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


func _ready() -> void:
	var args: Dictionary = _parse_args(OS.get_cmdline_user_args())
	output_path = str(args.get("output", ""))
	hdri_debug_output = str(args.get("debug_save_hdri", ""))
	capture_requested = output_path != ""
	capture_frame_delay = int(str(args.get("capture_frames", "8")))
	hdri_rotation_degrees = float(str(args.get("hdri_rotation", "0.0")))
	show_hdri_background = _is_true(args.get("show_hdri_background", ""))
	normal_flip_green = _is_true(args.get("flip_normal_green", ""))
	workflow_preset = str(args.get("workflow", "metal_rough"))
	roughness_mode = str(args.get("roughness_mode", "original_red"))
	ao_strength = float(str(args.get("ao_strength", "1.0")))
	albedo_only = _is_true(args.get("albedo_only", ""))
	packed_maps_enabled = _is_true(args.get("use_packed", ""))
	height_scale = float(str(args.get("height_scale", "5.0")))
	height_invert = _is_true(args.get("invert_height", ""))
	if not args.has("roughness_mode"):
		roughness_mode = _default_roughness_mode_for_workflow(workflow_preset)
	if _is_true(args.get("invert_roughness", "")):
		roughness_mode = "invert_red"

	_setup_scene()
	_apply_hdri(args)
	_apply_material(args)

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

	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		dragging_sphere = event.pressed
		get_viewport().set_input_as_handled()
		return

	if event is InputEventMouseMotion and dragging_sphere:
		sphere.rotation_degrees.y += event.relative.x * 0.35
		sphere.rotation_degrees.x = clamp(sphere.rotation_degrees.x + event.relative.y * 0.25, -80.0, 80.0)
		get_viewport().set_input_as_handled()


func _setup_scene() -> void:
	camera.position = Vector3(0.0, 0.08, 3.0)
	camera.look_at(Vector3.ZERO, Vector3.UP)
	camera.current = true
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

	var key := DirectionalLight3D.new()
	key.name = "KeyLight"
	key.light_energy = key_light_energy
	key.rotation_degrees = Vector3(-42.0, 36.0, 0.0)
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

	var basecolor := _load_texture(str(args.get("basecolor", "")))
	if basecolor != null:
		preview_material.albedo_texture = basecolor

	normal_source_image = _load_image(str(args.get("normal", "")))
	if normal_source_image != null:
		_limit_image_size(normal_source_image, MAX_PREVIEW_TEXTURE_SIZE)
		_set_normal_texture()

	height_source_image = _load_image(str(args.get("height", "")))
	if height_source_image != null:
		_limit_image_size(height_source_image, MAX_PREVIEW_CONTROL_MAP_SIZE)
		height_enabled = not args.has("use_height") or _is_true(args.get("use_height", ""))
		_set_height_texture()

	roughness_source_image = _load_image(str(args.get("roughness", "")))
	if roughness_source_image != null:
		_limit_image_size(roughness_source_image, MAX_PREVIEW_CONTROL_MAP_SIZE)
		_set_roughness_texture()
		preview_material.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED

	metallic_source_image = _load_image(str(args.get("metallic", "")))
	if metallic_source_image != null:
		_limit_image_size(metallic_source_image, MAX_PREVIEW_CONTROL_MAP_SIZE)
		_set_metallic_texture()

	ao_source_image = _load_image(str(args.get("ao", "")))
	if ao_source_image != null:
		_limit_image_size(ao_source_image, MAX_PREVIEW_CONTROL_MAP_SIZE)
		_set_ao_texture()

	packed_source_image = _load_image(str(args.get("packed", "")))
	if packed_source_image != null:
		_limit_image_size(packed_source_image, MAX_PREVIEW_CONTROL_MAP_SIZE)
		_apply_material_channel_sources()

	sphere.set_surface_override_material(0, preview_material)
	_apply_view_mode()


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

	sphere_size_label = _add_slider_row(stack, "Sphere", 0.35, 1.8, 0.05, sphere_size, _on_sphere_size_changed)
	uv_scale_label = _add_slider_row(stack, "UV scale", 0.1, 8.0, 0.1, uv_scale, _on_uv_scale_changed)
	height_scale_label = _add_slider_row(stack, "Height", 0.0, 12.0, 0.1, height_scale, _on_height_scale_changed)
	roughness_label = _add_slider_row(stack, "Roughness", 0.0, 1.0, 0.01, roughness_scale, _on_roughness_changed)
	ao_strength_label = _add_slider_row(stack, "AO strength", 0.0, 1.0, 0.01, ao_strength, _on_ao_strength_changed)
	hdri_rotation_label = _add_slider_row(stack, "HDRI rotate", 0.0, 360.0, 1.0, hdri_rotation_degrees, _on_hdri_rotation_changed)
	hdri_brightness_label = _add_slider_row(stack, "HDRI bright", 0.0, 12.0, 0.05, hdri_brightness, _on_hdri_brightness_changed)
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

	var packed_header_row := HBoxContainer.new()
	packed_header_row.add_theme_constant_override("separation", 8)
	stack.add_child(packed_header_row)

	var packed_label := Label.new()
	packed_label.text = "Packed channels"
	packed_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	packed_header_row.add_child(packed_label)

	packed_maps_check = CheckBox.new()
	packed_maps_check.text = "Use packed channels"
	packed_maps_check.button_pressed = packed_maps_enabled
	packed_maps_check.toggled.connect(_on_packed_maps_toggled)
	packed_header_row.add_child(packed_maps_check)

	var packed_row := HBoxContainer.new()
	packed_row.add_theme_constant_override("separation", 6)
	stack.add_child(packed_row)
	packed_ao_option = _add_channel_option(packed_row, "AO", packed_ao_channel, _on_packed_ao_channel_selected)
	packed_roughness_option = _add_channel_option(packed_row, "Rough", packed_roughness_channel, _on_packed_roughness_channel_selected)
	packed_metallic_option = _add_channel_option(packed_row, "Metal", packed_metallic_channel, _on_packed_metallic_channel_selected)

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
	export_directory = _default_export_dir()
	status_label.text = "Export: %s" % export_directory
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status_label.custom_minimum_size = Vector2(330.0, 0.0)
	stack.add_child(status_label)

	_create_export_dialog()
	_create_texture_import_dialog()
	_create_light_handle()
	_update_control_labels()


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


func _create_light_handle() -> void:
	light_handle = Button.new()
	light_handle.text = "Light"
	light_handle.tooltip_text = "Drag to move the primary light"
	light_handle.custom_minimum_size = Vector2(54.0, 34.0)
	light_handle.position = Vector2(680.0, 88.0)
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
		_update_key_light_from_handle()
		light_handle.accept_event()


func _update_key_light_from_handle() -> void:
	if key_light == null or light_handle == null:
		return
	var viewport_size: Vector2 = get_viewport().get_visible_rect().size
	var center: Vector2 = light_handle.position + light_handle.size * 0.5
	var normalized_x: float = clamp(center.x / maxf(1.0, viewport_size.x), 0.0, 1.0)
	var normalized_y: float = clamp(center.y / maxf(1.0, viewport_size.y), 0.0, 1.0)
	var source_x: float = lerpf(-2.2, 2.2, normalized_x)
	var source_y: float = lerpf(1.65, -1.65, normalized_y)
	key_light.position = Vector3(source_x, source_y, 2.3)
	key_light.look_at(Vector3.ZERO, Vector3.UP)


func _on_workflow_selected(index: int) -> void:
	if workflow_option == null:
		return
	workflow_preset = str(workflow_option.get_item_metadata(index))
	_apply_workflow_preset()


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
	sphere_size = value
	sphere.scale = Vector3.ONE * sphere_size
	_update_control_labels()


func _on_uv_scale_changed(value: float) -> void:
	uv_scale = value
	if preview_material != null:
		preview_material.uv1_scale = Vector3(uv_scale, uv_scale, 1.0)
	_update_control_labels()


func _on_height_scale_changed(value: float) -> void:
	height_scale = value
	_set_height_texture()
	_update_control_labels()


func _on_height_enabled_toggled(enabled: bool) -> void:
	height_enabled = enabled
	_set_height_texture()


func _on_height_invert_toggled(enabled: bool) -> void:
	height_invert = enabled
	_set_height_texture()


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


func _on_ao_strength_changed(value: float) -> void:
	ao_strength = value
	_apply_material_channel_sources()
	_update_control_labels()


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
	_apply_view_mode()


func _on_albedo_only_toggled(enabled: bool) -> void:
	albedo_only = enabled
	_apply_view_mode()


func _apply_view_mode() -> void:
	if preview_material == null:
		return
	if albedo_only:
		preview_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	else:
		preview_material.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL


func _on_hdri_brightness_changed(value: float) -> void:
	hdri_brightness = value
	_apply_hdri_brightness()
	_update_control_labels()


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


func _on_flip_normal_green_toggled(enabled: bool) -> void:
	normal_flip_green = enabled
	_set_normal_texture()


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


func _on_packed_roughness_channel_selected(index: int) -> void:
	packed_roughness_channel = _channel_from_option(packed_roughness_option, index)
	_apply_material_channel_sources()


func _on_packed_metallic_channel_selected(index: int) -> void:
	packed_metallic_channel = _channel_from_option(packed_metallic_option, index)
	_apply_material_channel_sources()


func _on_packed_maps_toggled(enabled: bool) -> void:
	packed_maps_enabled = enabled
	_apply_material_channel_sources()
	if packed_maps_enabled:
		_set_status("Packed channels enabled")
	else:
		_set_status("Packed channels ignored")


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
	if sphere_size_label != null:
		sphere_size_label.text = "%s %.2fx" % [sphere_size_label.get_meta("title"), sphere_size]
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
	height_source_image = null
	roughness_source_image = null
	ao_source_image = null
	packed_source_image = null
	metallic_source_image = null
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


func _on_export_folder_selected(path: String) -> void:
	export_directory = path
	if status_label != null:
		status_label.text = "Export: %s" % export_directory


func _on_texture_file_selected(path: String) -> void:
	_import_texture_map(pending_import_channel, path)


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
			_limit_image_size(image, MAX_PREVIEW_TEXTURE_SIZE)
			preview_material.albedo_texture = ImageTexture.create_from_image(image)
		"normal":
			_limit_image_size(image, MAX_PREVIEW_TEXTURE_SIZE)
			normal_source_image = image
			_set_normal_texture()
		"height":
			_limit_image_size(image, MAX_PREVIEW_CONTROL_MAP_SIZE)
			height_source_image = image
			height_enabled = true
			if height_enabled_check != null:
				height_enabled_check.button_pressed = true
			_set_height_texture()
		"roughness":
			_limit_image_size(image, MAX_PREVIEW_CONTROL_MAP_SIZE)
			roughness_source_image = image
			_apply_material_channel_sources()
		"metallic":
			_limit_image_size(image, MAX_PREVIEW_CONTROL_MAP_SIZE)
			metallic_source_image = image
			_apply_material_channel_sources()
		"ao":
			_limit_image_size(image, MAX_PREVIEW_CONTROL_MAP_SIZE)
			ao_source_image = image
			_apply_material_channel_sources()
		"packed":
			_limit_image_size(image, MAX_PREVIEW_CONTROL_MAP_SIZE)
			packed_source_image = image
			_apply_material_channel_sources()
		_:
			return

	if status_label != null:
		status_label.text = "Imported %s: %s" % [channel, path.get_file()]


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


func _load_texture(path: String) -> Texture2D:
	var image := _load_image(path)
	if image == null:
		return null

	return ImageTexture.create_from_image(image)


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
