// UNEXECUTED native fixture: actual candidate methods/callback, synthetic GUI/capability.
#include <atomic>
#include <memory>
#include <string>
#include <functional>
#include <sstream>
#include <cassert>
#define BOOST_LOG_TRIVIAL(level) std::ostringstream()
static int errors=0; inline void wxLogError(const char*) { ++errors; }
struct wxString { static std::string FromUTF8(const std::string& s) {return s;} };
struct wxWebViewEvent { void Skip() {} };
struct Cap { std::string get_ui() {return "generated";} void clear_message_sender() {} std::string name(){return "fixture";} };
struct Browser { int loads=0; void SetPage(const std::string&,const std::string&) {++loads;} };
class PluginPage { public:
Browser storage; Browser* m_browser=&storage; std::shared_ptr<Cap> m_cap=std::make_shared<Cap>();
std::shared_ptr<std::atomic<PluginPage*>> m_lifetime=std::make_shared<std::atomic<PluginPage*>>(this);
bool m_content_loaded=false,m_bootstrap_ready=false,m_handler_ready=false;
~PluginPage(){detach_capability();}
std::function<void(bool)> ready_callback(){const auto lifetime=m_lifetime; return [lifetime](bool success) {
        if (PluginPage* page = lifetime->load(std::memory_order_acquire)) {
            if (!success) {
                page->detach_capability();
                wxLogError("Could not register plugin page message handler");
                return;
            }
            page->m_handler_ready = true;
            page->load_plugin_content();
        }
    };}
std::string web_base_url(){return "generated";}
void detach_capability(); void load_plugin_content(); void on_bootstrap_event(wxWebViewEvent&);
};
void PluginPage::detach_capability()
{
    if (m_lifetime)
        m_lifetime->store(nullptr, std::memory_order_release);
    if (m_cap)
        m_cap->clear_message_sender();
    m_cap.reset();
}

void PluginPage::on_bootstrap_event(wxWebViewEvent& event)
{
    m_bootstrap_ready = true;
    load_plugin_content();
    event.Skip();
}

void PluginPage::load_plugin_content()
{
    if (m_content_loaded || !m_bootstrap_ready || !m_handler_ready || m_browser == nullptr || m_cap == nullptr)
        return;

    m_content_loaded = true;
    try {
        m_browser->SetPage(wxString::FromUTF8(m_cap->get_ui()), web_base_url());
    } catch (const std::exception& error) {
        BOOST_LOG_TRIVIAL(error) << "Failed to load plugin page '" << m_cap->name() << "': " << error.what();
        detach_capability();
    } catch (...) {
        BOOST_LOG_TRIVIAL(error) << "Failed to load plugin page '" << m_cap->name() << "'";
        detach_capability();
    }
}

int main(){
wxWebViewEvent e;
{PluginPage p; auto cb=p.ready_callback();p.on_bootstrap_event(e);assert(p.storage.loads==0);cb(true);assert(p.storage.loads==1);p.on_bootstrap_event(e);cb(true);assert(p.storage.loads==1);}
{PluginPage p;auto cb=p.ready_callback();cb(true);assert(p.storage.loads==0);p.on_bootstrap_event(e);assert(p.storage.loads==1);}
{PluginPage p;auto cb=p.ready_callback();p.on_bootstrap_event(e);cb(false);assert(!p.m_cap && p.storage.loads==0);cb(true);assert(p.storage.loads==0);}
{PluginPage p;auto cb=p.ready_callback();p.detach_capability();cb(true);p.on_bootstrap_event(e);assert(p.storage.loads==0);}
std::function<void(bool)> old;{PluginPage p;old=p.ready_callback();}old(true);old(false);
{PluginPage fresh;old(true);fresh.on_bootstrap_event(e);assert(fresh.storage.loads==0);fresh.ready_callback()(true);assert(fresh.storage.loads==1);}
assert(errors==1);
}
