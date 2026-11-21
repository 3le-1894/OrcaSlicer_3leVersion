#include "PluginHostBindings.hpp"

#include <libslic3r/Model.hpp>
#include <libslic3r/PresetBundle.hpp>
#include <slic3r/GUI/GUI.hpp>
#include <slic3r/GUI/GUI_App.hpp>
#include <slic3r/GUI/Plater.hpp>
#include <slic3r/GUI/PartPlate.hpp>
#include <slic3r/GUI/BackgroundSlicingProcess.hpp>
#include <slic3r/plugin/PluginFsUtils.hpp>
#include <wx/thread.h>
#include <nlohmann/json.hpp>

#include <memory>
#include <stdexcept>

namespace py = pybind11;

namespace Slic3r {
namespace {

GUI::Plater* current_plater()
{
    if (wxTheApp == nullptr)
        throw std::runtime_error("OrcaSlicer application is not initialized");

    GUI::Plater* plater = GUI::wxGetApp().plater();
    if (plater == nullptr)
        throw std::runtime_error("Plater is not available");

    return plater;
}

PresetBundle* current_preset_bundle()
{
    if (wxTheApp == nullptr)
        throw std::runtime_error("OrcaSlicer application is not initialized");

    PresetBundle* preset_bundle = GUI::wxGetApp().preset_bundle;
    if (preset_bundle == nullptr)
        throw std::runtime_error("Preset bundle is not available");

    return preset_bundle;
}

} // namespace

// Access to the live GUI application: the Plater and the module-level
// plater()/model()/preset_bundle() accessors. Everything here is owned by the
// app and only reachable once the GUI is up (the accessors throw before that).
void host_bindings::register_app(py::module_& host)
{
    py::class_<GUI::Plater, std::unique_ptr<GUI::Plater, py::nodelete>>(host, "Plater")
        .def("model", static_cast<Model& (GUI::Plater::*)()>(&GUI::Plater::model), py::return_value_policy::reference_internal)
        .def("is_project_dirty", &GUI::Plater::is_project_dirty)
        .def("is_presets_dirty", &GUI::Plater::is_presets_dirty)
        .def("inside_snapshot_capture", &GUI::Plater::inside_snapshot_capture);

    host.def("calculator_snapshot", []() {
        if (!wxIsMainThread())
            throw std::runtime_error("calculator_snapshot requires the UI thread");
        auto* plater = current_plater();
        nlohmann::json out = {{"busy", true}};
        if (plater->calculator_mutating() || plater->is_background_process_update_scheduled())
            return json_to_py(out);
        // UI control cannot start work during this non-yielding native copy.
        // Never call Python, audit hooks or UI callbacks inside it.
        plater->background_process().copy_calculator_idle([&](unsigned long long generation) {
            out = {{"busy", false}, {"epoch", std::to_string(plater->calculator_project_epoch())},
                   {"model", std::to_string(plater->model().id().id)}, {"generation", std::to_string(generation)},
                   {"project", GUI::into_u8(plater->get_project_filename())}, {"plates", nlohmann::json::array()}};
            const auto* bundle = current_preset_bundle();
            const auto& printer = bundle->printers.get_edited_preset();
            out["printer"] = printer.name;
            out["printer_model"] = printer.config.opt_string("printer_model");
            const auto* vendor = dynamic_cast<const ConfigOptionString*>(printer.config.option("printer_vendor"));
            out["printer_vendor"] = vendor ? vendor->value : std::string();
            out["filaments"] = bundle->filament_presets;
            int index = 0;
            for (auto* plate : plater->get_partplate_list().get_plate_list()) {
                const auto* result = plate->get_slice_result();
                out["plates"].push_back({{"id", std::to_string(plate->id().id)}, {"index", index++},
                    {"path", result ? result->filename : std::string()},
                    {"valid", !plate->is_apply_result_invalid() && plate->is_slice_result_valid()}});
            }
        });
        return json_to_py(out);
    });

    host.def("plater", &current_plater, py::return_value_policy::reference);
    host.def("model", []() -> Model& {
        return current_plater()->model();
    }, py::return_value_policy::reference);
    host.def("preset_bundle", &current_preset_bundle, py::return_value_policy::reference);
    // UI language of the running app ("en_US", "ru_RU", ...), so plugins can
    // localize their own dialogs. The app config file that stores this value
    // is deny-listed by the audit hook (it sits next to cloud secrets), so a
    // read-only accessor is the supported way to get just the language.
    host.def("app_language", []() -> std::string {
        if (wxTheApp == nullptr)
            throw std::runtime_error("OrcaSlicer application is not initialized");
        return GUI::into_u8(GUI::wxGetApp().current_language_code_safe());
    });
}

} // namespace Slic3r
