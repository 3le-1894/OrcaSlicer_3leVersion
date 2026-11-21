#ifndef slic3r_GUI_WebView_hpp_
#define slic3r_GUI_WebView_hpp_

#include <wx/webview.h>
#include <wx/event.h>
#include <functional>

wxDECLARE_EVENT(EVT_WEBVIEW_RECREATED, wxCommandEvent);

class WebView
{
public:
    // Completion runs later on the UI thread for this target's registration.
    // Destroying the view before its deferred work runs may cancel completion.
    // true means registration succeeded (not that a document acknowledged a message).
    static wxWebView *CreateWebView(wxWindow *parent, wxString const &url,
                                   std::function<void(bool)> handler_ready = {});
#if wxUSE_WEBVIEW_EDGE
    static bool CheckWebViewRuntime();
    static bool DownloadAndInstallWebViewRuntime();
#endif
    static void LoadUrl(wxWebView * webView, wxString const &url);

    static bool RunScript(wxWebView * webView, wxString const & msg);

    // Marks "wx" as registered so CreateWebView's deferred add skips the duplicate.
    static void MarkScriptMessageHandlerAdded(wxWebView * webView);

    static void RecreateAll();
};

#endif // !slic3r_GUI_WebView_hpp_
