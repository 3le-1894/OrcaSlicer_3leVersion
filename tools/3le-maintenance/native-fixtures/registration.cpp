// UNEXECUTED native fixture: actual queue/registration C++, synthetic wx/app/logger.
#include <vector>
#include <memory>
#include <functional>
#include <sstream>
#include <cassert>
#define BOOST_LOG_TRIVIAL(level) std::ostringstream()
inline void wxLogError(const char*){}
struct wxWebView;
template<class T> struct wxWeakRef {T* ptr;std::weak_ptr<int> token;wxWeakRef(T* p):ptr(p),token(p->token){} T* get()const{return token.expired()?nullptr:ptr;}};
struct WebViewRef {bool m_script_handler_added=false;};
struct wxWebView {std::shared_ptr<int> token=std::make_shared<int>(); WebViewRef ref;bool success=true;std::function<void()> during,queued;
void CallAfter(std::function<void()> f){queued=f;}void run(){auto f=std::move(queued);if(f)f();}
bool AddScriptMessageHandler(const char*){if(during)during();return success;}};
inline WebViewRef* webview_ref(wxWebView* p){return &p->ref;}
namespace Slic3r {namespace GUI {struct App{bool adding=false;std::vector<std::function<void()>> posted;
bool is_adding_script_handler(){return adding;}void set_adding_script_handler(bool b){adding=b;}void CallAfter(std::function<void()> f){posted.push_back(f);}
void flush(){auto callbacks=std::move(posted);posted.clear();for(auto& f:callbacks)f();}};static App app;inline App& wxGetApp(){return app;}}}
struct WebViewRegistration {
    wxWeakRef<wxWebView> view;
    std::function<void(bool)> complete;
};
static std::vector<WebViewRegistration> g_delay_webviews;

static void complete_registration(const WebViewRegistration& target, bool success)
{
    if (target.complete) {
        // Never call a page constructor back synchronously, including on Windows.
        Slic3r::GUI::wxGetApp().CallAfter([complete = target.complete, success] {
            complete(success);
        });
    }
}

void create(wxWebView* webView,std::function<void(bool)> handler_ready){
        const WebViewRegistration target{wxWeakRef<wxWebView>(webView), std::move(handler_ready)};
        auto addScriptMessageHandler = [] (const WebViewRegistration& target) {
            wxWebView* webView = target.view.get();
            if (!webView) {
                complete_registration(target, false);
                return;
            }
            // Skip if SendAPIKey() already registered "wx"; a duplicate add throws an
            // uncatchable NSException on WKWebView, killing the app at startup.
            WebViewRef *ref = webview_ref(webView);
            if (ref && ref->m_script_handler_added) {
                complete_registration(target, true);
                return;
            }
            BOOST_LOG_TRIVIAL(info) << __FUNCTION__ << ": begin to add script message handler for wx.";
            Slic3r::GUI::wxGetApp().set_adding_script_handler(true);
            const bool added = webView->AddScriptMessageHandler("wx");
            Slic3r::GUI::wxGetApp().set_adding_script_handler(false);
            // Registration may yield; do not retain ref-data across that call.
            wxWebView* live = target.view.get();
            if (added && live) {
                if (WebViewRef* live_ref = webview_ref(live))
                    live_ref->m_script_handler_added = true;
            }
            complete_registration(target, added && live);
            if (!added && !target.complete)
                wxLogError("Could not add script message handler");
            BOOST_LOG_TRIVIAL(info) << __FUNCTION__ << ": finished add script message handler for wx.";
        };
#ifndef __WIN32__
        webView->CallAfter([target, addScriptMessageHandler] {
#endif
            if (Slic3r::GUI::wxGetApp().is_adding_script_handler()) {
                g_delay_webviews.push_back(target);
            } else {
                addScriptMessageHandler(target);
                while (!g_delay_webviews.empty()) {
                    auto views = std::move(g_delay_webviews);
                    for (const auto& queued : views)
                        addScriptMessageHandler(queued);
                }
            }
#ifndef __WIN32__
        });
#endif

}
int main(){
using namespace Slic3r::GUI;std::vector<int> done;
for(int mode=0;mode<4;++mode){done.clear();wxWebView a,b;b.success=mode!=2;b.ref.m_script_handler_added=mode==3;
create(&b,[&](bool ok){done.push_back(ok?22:-22);});a.during=[&]{b.run();};
create(&a,mode==1?std::function<void(bool)>{}:std::function<void(bool)>{[&](bool ok){assert(ok);done.push_back(11);}});a.run();assert(done.empty());app.flush();
assert(done.back()==(mode==2?-22:22));assert(done.size()==(mode==1?1:2));}
// Destroy a queued target before another view drains it.
done.clear();wxWebView a;auto b=std::make_unique<wxWebView>();create(b.get(),[&](bool ok){done.push_back(ok?1:-1);});
a.during=[&]{b->run();b.reset();};create(&a,{});a.run();app.flush();assert(done==std::vector<int>{-1});
}
