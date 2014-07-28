/**
 * Flow.
 * 1. User goes to "their" page (narratives, newsfeeds, w/e).
 * 2. Widget inits.
 * 3. If User isn't logged in (widget doesn't get a token):
 *    a. Hide everything.
 *    b. Modal with login prompt.
 *    c. If cancel, return to kbase.us
 *    d. If login okay, login user and... what? Reload page? Continue with page population?
 * 4. If User is logged in, continue. Everything's peachy.
 * 5. Widget sits in T/R corner.
 */

(function( $, undefined ) {

    $(function() {
        // set the auth token by calling the kernel execute method on a function in
        // the magics module

        var setToken = function () {

            var registerLogin = function() {
                // grab the token from the handler, since it isn't passed in with args
                var token = $("#signin-button").kbaseLogin('session', 'token');

                var cmd = "biokbase.narrative.magics.set_token('" + token + "')\n" +
                          "import os\n" +
                          "os.environ['KB_AUTH_TOKEN'] = '" + token + "'\n";

                if (IPython.notebook.metadata && IPython.notebook.metadata.ws_name) {
                    cmd += "\nos.environ['KB_WORKSPACE_ID'] = '" + IPython.notebook.metadata.ws_name + "'\n" + 
                           "from biokbase.narrative.services import *";  // timing is everything!
                }

                IPython.notebook.kernel.execute( cmd );
            };

            // make sure the shell_channel is ready, otherwise sleep for .5 sec
            // and then try it. We use the ['kernel'] attribute deref in case
            // because at parse time the kernel attribute may not be ready
            if (IPython.notebook.kernel.shell_channel.readyState == 1) {
                registerLogin();
            } else {
                console.log("Pausing for 500 ms before passing credentials to kernel");
                setTimeout( function() { registerLogin(); }, 500 );
            }
        };



        var loginWidget = $("#signin-button").kbaseLogin({ 
            login_callback: function(args) {
                // If the notebook kernel's initialized, tell it to set the token.
                if (IPython && IPython.notebook) {
                    setToken();
                } else {
                    console.log("IPython.notebook not set, cannot set token on backend");
                }
            },

            logout_callback: function(args) {
                // If the notebook kernel's initialized, tell it to clear the token in 
                // the ipython kernel using special handler
                console.log("LOGOUT CALLBACK");

                if (IPython && IPython.notebook) {
                    var cmd = "biokbase.narrative.magics.clear_token()" + 
                              "import os\n" +
                              "del os.environ['KB_AUTH_TOKEN']\n" + 
                              "del os.environ['KB_WORKSPACE_ID']";
                    IPython.notebook.kernel.execute( cmd );
                }

                window.location.href = "/";
            },

            prior_login_callback: function(args) {
                // Do actual login once the kernel is up - only an issue for prior_login
                $([IPython.events]).one('status_started.Kernel', setToken);
            },
        });

        $('#signin-button').css('padding', '0');  // Jim!

        if (loginWidget.token() === undefined) {
            // include hiding div.
            loginWidget.openDialog();
        }
    });

})( jQuery );