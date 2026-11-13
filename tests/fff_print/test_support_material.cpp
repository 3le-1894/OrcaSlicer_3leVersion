#include <catch2/catch_all.hpp>

#include <algorithm>
#include <cmath>
#include <set>
#include "libslic3r/BoundingBox.hpp"
#include "libslic3r/ClipperUtils.hpp"
#include "libslic3r/ExtrusionEntityCollection.hpp"
#include "libslic3r/GCodeReader.hpp"
#include "libslic3r/Layer.hpp"

#include "test_helpers.hpp" // get access to init_print, etc

using namespace Slic3r::Test;
using namespace Slic3r;

TEST_CASE("Three raft layers are created", "[SupportMaterial]")
{
	Slic3r::Print print;
	Slic3r::Test::init_and_process_print({ cube(20) }, print, {
        { "enable_support", 1 },
        { "raft_layers",    3 }
		});
    REQUIRE(print.objects().front()->support_layers().size() == 3);
}

TEST_CASE("Enforced support layers are generated", "[SupportMaterial]")
{
    // enforce_support_layers forces support on the first N layers even with support off.
    Slic3r::Print baseline;
    Slic3r::Test::init_and_process_print({ TestMesh::overhang }, baseline, {
        { "enable_support",         0 },
        { "enforce_support_layers", 0 }
    });
    REQUIRE(baseline.objects().front()->support_layers().empty());

    Slic3r::Print enforced;
    Slic3r::Test::init_and_process_print({ TestMesh::overhang }, enforced, {
        { "enable_support",         0 },
        { "enforce_support_layers", 100 }
    });
    REQUIRE(enforced.objects().front()->support_layers().size() > 0);
}

SCENARIO("Support layer Z honors contact distance", "[SupportMaterial]")
{
    // Box h = 20mm, hole bottom at 5mm, hole height 10mm (top edge at 15mm).
    TriangleMesh mesh = Slic3r::Test::mesh(Slic3r::Test::TestMesh::cube_with_hole);
    mesh.rotate_x(float(M_PI / 2));

	auto check = [](Slic3r::Print &print, bool &first_support_layer_height_ok, bool &layer_height_minimum_ok, bool &layer_height_maximum_ok)
	{
        ConstSupportLayerPtrsAdaptor support_layers = print.objects().front()->support_layers();

		first_support_layer_height_ok = support_layers.front()->print_z == print.config().initial_layer_print_height.value;

		layer_height_minimum_ok = true;
		layer_height_maximum_ok = true;
		double min_layer_height = print.config().min_layer_height.values.front();
		double max_layer_height = print.config().nozzle_diameter.values.front();
		if (print.config().max_layer_height.values.front() > EPSILON)
			max_layer_height = std::min(max_layer_height, print.config().max_layer_height.values.front());
		for (size_t i = 1; i < support_layers.size(); ++ i) {
			if (support_layers[i]->print_z - support_layers[i - 1]->print_z < min_layer_height - EPSILON)
				layer_height_minimum_ok = false;
			if (support_layers[i]->print_z - support_layers[i - 1]->print_z > max_layer_height + EPSILON)
				layer_height_maximum_ok = false;
		}
	};

    GIVEN("A print object having one modelObject") {
        WHEN("Layer height = 0.2 and first layer height = 0.4") {
			Slic3r::Print print;
			Slic3r::Test::init_and_process_print({ mesh }, print, {
                { "enable_support",             1 },
                { "layer_height",               0.2 },
                { "initial_layer_print_height", 0.4 },
                { "dont_support_bridges",       false },
			});
			bool first_layer_ok, layer_min_ok, layer_max_ok;
            check(print, first_layer_ok, layer_min_ok, layer_max_ok);
            THEN("First layer height is honored")			{ REQUIRE(first_layer_ok == true); }
            THEN("No null or negative support layers")		{ REQUIRE(layer_min_ok == true); }
            THEN("No layers thicker than nozzle diameter")	{ REQUIRE(layer_max_ok == true); }
        }
        WHEN("Layer height = 0.2 and first layer height = 0.3") {
			Slic3r::Print print;
			Slic3r::Test::init_and_process_print({ mesh }, print, {
                { "enable_support",             1 },
                { "layer_height",               0.2 },
                { "initial_layer_print_height", 0.3 },
                { "dont_support_bridges",       false },
            });
            bool first_layer_ok, layer_min_ok, layer_max_ok;
            check(print, first_layer_ok, layer_min_ok, layer_max_ok);
            THEN("First layer height is honored")			{ REQUIRE(first_layer_ok == true); }
            THEN("No null or negative support layers")		{ REQUIRE(layer_min_ok == true); }
            THEN("No layers thicker than nozzle diameter")	{ REQUIRE(layer_max_ok == true); }
        }
    }
}

// extrude_support once held a `static` lambda capturing `this`, so a second export in the
// same process dereferenced a returned stack frame (ASan: stack-use-after-return).
TEST_CASE("Support G-code emission survives a second slice in the same process", "[SupportMaterial][Regression]")
{
    const std::string first = slice({ TestMesh::overhang }, { { "enable_support", 1 } });
    REQUIRE(! layers_with_role(first, "support").empty());

    const std::string second = slice({ TestMesh::overhang }, { { "enable_support", 1 } });
    REQUIRE(! layers_with_role(second, "support").empty());
}


namespace {
static TriangleMesh support_capital()
{
    TriangleMesh model = make_cube(40, 40, 2);                              // base  [0,40]x[0,40]x[0,2]
    TriangleMesh stem  = make_cube(8, 8, 12);   stem.translate(16, 16, 1);  // stem  centered, z 1..13
    TriangleMesh cap   = make_cube(40, 40, 2);  cap.translate(0, 0, 12);    // cap   z 12..14
    model.merge(stem);
    model.merge(cap);
    return model;
}
static TriangleMesh support_tunnel()
{
    TriangleMesh tunnel = Slic3r::Test::mesh(TestMesh::cube_with_hole);
    tunnel.rotate_x(float(M_PI / 2));
    return tunnel;
}
static size_t support_interface_layer_count(const std::string &gcode)
{
    return layers_with_role(gcode, "support material interface").size();
}
static size_t support_base_layer_count(const std::string &gcode)
{
    std::set<double> layers;
    GCodeReader parser;
    parser.parse_buffer(gcode, [&layers](GCodeReader &reader, const GCodeReader::GCodeLine &line) {
        if (line.extruding(reader) && line.comment().find("support material") != std::string::npos &&
            line.comment().find("interface") == std::string::npos)
            layers.insert(reader.z());
    });
    return layers.size();
}
static std::set<double> interface_heights(const Print &print)
{
    std::set<double> heights;
    for (const SupportLayer *layer : print.objects().front()->support_layers()) {
        Polygons footprint;
        const ExtrusionEntityCollection fills = layer->support_fills.flatten();
        for (const ExtrusionEntity *entity : fills.entities)
            if (entity->role() == erSupportMaterialInterface)
                entity->polygons_covered_by_width(footprint, 0.f);
        if (!footprint.empty()) {
            REQUIRE(area(union_(footprint)) > 0.);
            heights.insert(layer->print_z);
        }
    }
    return heights;
}
}


TEST_CASE("Bottom support interfaces survive quantized contact gaps", "[SupportMaterial][SupportContact][Regression]")
{
    const bool independent = GENERATE(false, true);
    const double top_gap = GENERATE(0.0, 0.2);
    CAPTURE(independent, top_gap);
    const double bottom_gap = GENERATE(0., 0.08, 0.12, 0.2, 0.28);
    CAPTURE(bottom_gap);
    Print print;
    init_and_process_print({ support_tunnel() }, print, {
        { "enable_support",                  1 },
        { "support_type",                    "normal(auto)" },
        { "layer_height",                    0.2 },
        { "initial_layer_print_height",      0.2 },
        { "independent_support_layer_height", independent },
        { "support_on_build_plate_only",     0 },
        { "support_top_z_distance",          top_gap },
        { "support_bottom_z_distance",       bottom_gap },
        { "support_interface_top_layers",    0 },
        { "support_interface_bottom_layers", 2 },
    });
    const std::string g = gcode(print);
    REQUIRE(interface_heights(print).size() == 2);
    REQUIRE(support_base_layer_count(g) > 0);
    REQUIRE(support_interface_layer_count(g) == 2);
}

TEST_CASE("Synchronized bottom support interfaces survive a rounded variable layer gap", "[SupportMaterial][SupportContact][Regression]")
{
    DynamicPrintConfig config = DynamicPrintConfig::full_print_config();
    config.set_deserialize_strict({
        { "enable_support",                  1 },
        { "support_type",                    "normal(auto)" },
        { "layer_height",                    0.2 },
        { "initial_layer_print_height",      0.2 },
        { "independent_support_layer_height", false },
        { "support_on_build_plate_only",     0 },
        { "support_top_z_distance",          0.2 },
        { "support_bottom_z_distance",       0.2 },
        { "support_interface_top_layers",    0 },
        { "support_interface_bottom_layers", 2 },
        { "gcode_comments",                  true },
    });
    Print print;
    Model model;
    init_print({ support_capital() }, print, model, config);
    // The first layer above the 2 mm base is 0.16 mm high, so a synchronized
    // 0.2 mm gap rounds down and must still exclude the supporting surface.
    model.objects.front()->layer_height_profile.set(std::vector<coordf_t>{
        0.0, 0.2, 2.0, 0.2, 2.0, 0.16, 2.16, 0.16, 2.16, 0.2, 14.0, 0.2,
    });
    print.apply(model, config);
    const std::string g = gcode(print);
    const auto &layers = print.objects().front()->layers();
    REQUIRE(std::any_of(layers.begin(), layers.end(), [](const Layer *layer) {
        return std::abs(layer->print_z - 2.16) < EPSILON;
    }));
    REQUIRE(interface_heights(print).size() == 2);
    REQUIRE(support_interface_layer_count(g) == 2);
}

TEST_CASE("Bottom support interfaces keep clearance from expanding overhang walls", "[SupportMaterial][SupportContact][Regression]")
{
    TriangleMesh mesh = make_cube(40, 40, 2);
    TriangleMesh overhang = make_pyramid(30, 6);
    overhang.rotate_x(float(M_PI));
    overhang.translate(20, 20, 7);
    mesh.merge(overhang);

    Print print;
    init_and_process_print({ mesh }, print, {
        { "enable_support",                  1 },
        { "support_type",                    "normal(auto)" },
        { "layer_height",                    0.2 },
        { "initial_layer_print_height",      0.2 },
        { "independent_support_layer_height", true },
        { "support_on_build_plate_only",     0 },
        { "support_top_z_distance",          0.2 },
        { "support_bottom_z_distance",       0.2 },
        { "support_object_xy_distance",      0.35 },
        { "support_interface_top_layers",    0 },
        { "support_interface_bottom_layers", 2 },
    });
    const PrintObject &object = *print.objects().front();
    size_t interface_layers = 0;
    size_t checked_layers = 0;
    for (const SupportLayer *support : object.support_layers()) {
        if (support->print_z <= 2.0 || support->print_z > 3.0)
            continue;
        Polygons interface_polygons;
        const ExtrusionEntityCollection fills = support->support_fills.flatten();
        for (const ExtrusionEntity *entity : fills.entities)
            if (entity->role() == erSupportMaterialInterface)
                entity->polygons_covered_by_width(interface_polygons, 0.f);
        if (interface_polygons.empty())
            continue;
        ++interface_layers;
        for (const Layer *layer : object.layers()) {
            if (layer->bottom_z() < support->print_z - EPSILON && layer->print_z >= support->print_z - EPSILON) {
                ++checked_layers;
                CAPTURE(support->print_z);
                REQUIRE(intersection(interface_polygons, to_polygons(layer->lslices)).empty());
            }
        }
    }
    REQUIRE(interface_layers > 0);
    REQUIRE(checked_layers == interface_layers);
}

TEST_CASE("Top support interfaces cover an overhang with a synchronized variable layer gap", "[SupportMaterial][SupportContact][Regression]")
{
    const bool independent = GENERATE(false, true);
    const bool variable = GENERATE(false, true);
    const double top_gap = GENERATE(0.0, 0.08, 0.12, 0.2, 0.28);
    CAPTURE(independent, variable, top_gap);
    DynamicPrintConfig config = DynamicPrintConfig::full_print_config();
    config.set_deserialize_strict({
        { "enable_support",                  1 },
        { "support_type",                    "normal(auto)" },
        { "layer_height",                    0.2 },
        { "initial_layer_print_height",      0.2 },
        { "independent_support_layer_height", independent },
        { "support_on_build_plate_only",     0 },
        { "support_top_z_distance",          top_gap },
        { "support_bottom_z_distance",       0.2 },
        { "support_object_xy_distance",      0.35 },
        { "support_interface_spacing",       0.0 },
        { "support_interface_top_layers",    2 },
        { "support_interface_bottom_layers", 0 },
        { "gcode_comments",                  true },
    });
    Print print;
    Model model;
    init_print({ support_capital() }, print, model, config);
    if (variable) {
        // Below the overhang at Z=12, 0.16 mm layers round the nominal 0.2 mm
        // synchronized gap down. No material painting is involved.
        model.objects.front()->layer_height_profile.set(std::vector<coordf_t>{
            0.0, 0.2, 1.6, 0.2, 1.6, 0.16, 14.0, 0.16,
        });
        print.apply(model, config);
    }
    print.process();
    const PrintObject &object = *print.objects().front();
    REQUIRE(!object.support_layers().empty());
    const SupportLayer &contact = *object.support_layers().back();
    REQUIRE(contact.print_z <= 12.0 + EPSILON);
    REQUIRE(contact.print_z > 11.5);
    Polygons coverage;
    Polygons footprint;
    const ExtrusionEntityCollection fills = contact.support_fills.flatten();
    for (const ExtrusionEntity *entity : fills.entities)
        if (entity->role() == erSupportMaterialInterface) {
            entity->polygons_covered_by_spacing(coverage, 0.f);
            entity->polygons_covered_by_width(footprint, 0.f);
        }
    const auto &layers = object.layers();
    const auto wall_layer = std::find_if(layers.begin(), layers.end(), [&contact](const Layer *layer) {
        return layer->bottom_z() < contact.print_z - EPSILON && layer->print_z >= contact.print_z - EPSILON;
    });
    REQUIRE(wall_layer != layers.end());
    REQUIRE(intersection(footprint, to_polygons((*wall_layer)->lslices)).empty());
    if (top_gap > 0.0) {
        const auto next_layer = std::find_if(layers.begin(), layers.end(), [&contact](const Layer *layer) {
            return layer->bottom_z() >= contact.print_z - EPSILON;
        });
        REQUIRE(next_layer != layers.end());
        // Only intervening object walls require clearance. With a sub-layer
        // independent gap the next layer may be the assigned overhang itself.
        if ((*next_layer)->bottom_z() < 12.0 - EPSILON)
            REQUIRE(intersection(footprint, to_polygons((*next_layer)->lslices)).empty());
    }
    // Check interior areas on both sides of the stem, away from the XY gap.
    const BoundingBox bounds = get_extents(object.layers().back()->lslices);
    const Point center = bounds.center();
    for (double x : {-10.0, 10.0}) {
        const Point lower = center + Point::new_scale(x - 2.0, -2.0);
        const Point upper = center + Point::new_scale(x + 2.0, 2.0);
        const Polygon target({lower, Point(upper.x(), lower.y()), upper, Point(lower.x(), upper.y())});
        CAPTURE(x, contact.print_z);
        REQUIRE(area(intersection(Polygons{target}, coverage)) > 0.9 * target.area());
    }
}

TEST_CASE("Top support interfaces keep clearance below expanding overhang walls", "[SupportMaterial][SupportContact][Regression]")
{
    const bool independent = GENERATE(false, true);
    const bool variable = GENERATE(false, true);
    const double top_gap = 0.2;
    const double object_height = variable ? 0.16 : 0.2;
    const double effective_gap = independent ? top_gap : std::round(top_gap / object_height) * object_height;
    TriangleMesh mesh = make_cube(40, 40, 2);
    TriangleMesh overhang = make_pyramid(30, 6);
    overhang.rotate_x(float(M_PI));
    overhang.translate(20, 20, 7);
    mesh.merge(overhang);

    DynamicPrintConfig config = DynamicPrintConfig::full_print_config();
    config.set_deserialize_strict({
        { "enable_support",                  1 },
        { "support_type",                    "normal(auto)" },
        { "layer_height",                    0.2 },
        { "initial_layer_print_height",      0.2 },
        { "independent_support_layer_height", independent },
        { "support_on_build_plate_only",     0 },
        { "support_top_z_distance",          top_gap },
        { "support_bottom_z_distance",       0.2 },
        { "support_object_xy_distance",      0.35 },
        { "support_interface_top_layers",    2 },
        { "support_interface_bottom_layers", 0 },
        { "thick_bridges",                   false },
    });
    Print print;
    Model model;
    init_print({ mesh }, print, model, config);
    if (variable) {
        model.objects.front()->layer_height_profile.set(std::vector<coordf_t>{
            0.0, 0.2, 1.6, 0.2, 1.6, object_height, 7.0, object_height,
        });
        print.apply(model, config);
    }
    print.process();
    const PrintObject &object = *print.objects().front();
    size_t checked_layers = 0;
    for (const SupportLayer *support : object.support_layers()) {
        if (support->print_z <= 3.0 || support->print_z >= 6.5)
            continue;
        Polygons footprint;
        const ExtrusionEntityCollection fills = support->support_fills.flatten();
        for (const ExtrusionEntity *entity : fills.entities)
            if (entity->role() == erSupportMaterialInterface)
                entity->polygons_covered_by_width(footprint, 0.f);
        if (footprint.empty())
            continue;
        for (const Layer *layer : object.layers()) {
            if (layer->bottom_z() >= support->print_z - EPSILON &&
                layer->bottom_z() < support->print_z + effective_gap - EPSILON) {
                ++checked_layers;
                CAPTURE(independent, variable, support->print_z, layer->bottom_z(), effective_gap);
                REQUIRE(intersection(footprint, to_polygons(layer->lslices)).empty());
            }
        }
    }
    REQUIRE(checked_layers > 0);
}

TEST_CASE("Top support interfaces keep clearance when clamped to the first layer", "[SupportMaterial][SupportContact][Regression]")
{
    TriangleMesh mesh = make_pyramid(30, 6);
    mesh.rotate_x(float(M_PI));
    mesh.translate(15, 15, 6);
    Print print;
    init_and_process_print({ mesh }, print, {
        { "enable_support",                  1 },
        { "support_type",                    "normal(auto)" },
        { "layer_height",                    0.28 },
        { "initial_layer_print_height",      0.2 },
        { "independent_support_layer_height", false },
        { "support_top_z_distance",          0.2 },
        { "support_object_xy_distance",      0.35 },
        { "support_interface_top_layers",    2 },
        { "support_interface_bottom_layers", 0 },
        { "thick_bridges",                   false },
    });
    const PrintObject &object = *print.objects().front();
    REQUIRE(!object.support_layers().empty());
    const SupportLayer &first = *object.support_layers().front();
    REQUIRE_THAT(first.print_z, Catch::Matchers::WithinAbs(0.2, EPSILON));
    REQUIRE(object.layers().size() > 1);
    Polygons footprint;
    const ExtrusionEntityCollection fills = first.support_fills.flatten();
    for (const ExtrusionEntity *entity : fills.entities)
        if (entity->role() == erSupportMaterialInterface)
            entity->polygons_covered_by_width(footprint, 0.f);
    REQUIRE(intersection(footprint, to_polygons(object.layers()[1]->lslices)).empty());
}

TEST_CASE("Configured interface stacks fit available support height", "[SupportMaterial][SupportContact][Regression]")
{
    const bool limited = GENERATE(false, true);
    CAPTURE(limited);
    TriangleMesh mesh = support_capital();
    if (limited) mesh.scale(0.15); // 1.5 mm clear span cannot fit twelve .2 mm interfaces.
    Print print;
    init_and_process_print({mesh}, print, {
        {"enable_support", 1}, {"support_type", "normal(auto)"},
        {"layer_height", .2}, {"initial_layer_print_height", .2},
        {"independent_support_layer_height", false}, {"support_on_build_plate_only", false},
        {"support_top_z_distance", 0.}, {"support_bottom_z_distance", 0.},
        {"support_interface_top_layers", 6}, {"support_interface_bottom_layers", 6},
        {"support_object_xy_distance", .35}, {"support_interface_spacing", 0.}
    });
    const auto heights = interface_heights(print);
    REQUIRE_FALSE(heights.empty());
    CHECK(heights.size() <= 12);
    if (!limited) CHECK(heights.size() == 12);
    else CHECK(heights.size() < 12);
    for (double z : heights) {
        CHECK(z >= .2 - EPSILON);
        CHECK(z < (limited ? 1.8 : 12.) + EPSILON);
    }
}


TEST_CASE("Rafted objects retain nonempty interface contacts above the bed", "[SupportMaterial][SupportContact][Regression]")
{
    const bool independent = GENERATE(false, true);
    CAPTURE(independent);
    Print print;
    init_and_process_print({support_capital()}, print, {
        {"enable_support", 1}, {"support_type", "normal(auto)"}, {"raft_layers", 3},
        {"layer_height", .2}, {"initial_layer_print_height", .2},
        {"independent_support_layer_height", independent}, {"support_on_build_plate_only", false},
        {"support_top_z_distance", .2}, {"support_bottom_z_distance", .2},
        {"support_interface_top_layers", 2}, {"support_interface_bottom_layers", 2},
        {"support_object_xy_distance", .35}, {"support_interface_spacing", 0.}
    });
    const PrintObject &object = *print.objects().front();
    REQUIRE(object.support_layers().size() > 3);
    REQUIRE_FALSE(interface_heights(print).empty());
    CHECK(object.layers().front()->bottom_z() > 0.);
    double previous = 0.;
    for (const SupportLayer *layer : object.support_layers()) {
        CHECK(layer->print_z >= .2 - EPSILON);
        CHECK(layer->print_z > previous);
        previous = layer->print_z;
    }
}
