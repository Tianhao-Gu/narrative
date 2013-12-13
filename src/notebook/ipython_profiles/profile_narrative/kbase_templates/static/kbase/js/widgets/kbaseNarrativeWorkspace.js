/**
 * Top-level 'widget' for the workspace interaction with the KBase narrative.
 *
 * The widget lists the objects in the workspace and include a search field
 * to filter the list, as well as a button to 'Add' new items from sources 
 * like the CDS and local files.
 *
 * Options:
 *    workspaceURL - the location of the workspace service (default points to existing deployed service)
 *    loadingImage - an image to show in the middle of the widget while loading data
 *    tableElem - HTML element container for the data table
 *    controlsElem - HTML element container for the controls (search/add)
 *
 * Triggers events:
 * updateData.Narrative - when any externally represented data should be updated.
 * 
 * @author Bill Riehl <wjriehl@lbl.gov>
 * @author Dan Gunter <dkgunter@lbl.gov>
 * @public
 */

(function( $, undefined ) {
    $.KBWidget({
        name: "kbaseNarrativeWorkspace", 
        parent: "kbaseWidget",
        version: "1.0.0",
        options: {
            workspaceURL: "https://www.kbase.us/services/workspace",
            loadingImage: "../images/ajax-loader.gif",
            tableElem: null,
            controlsElem: null
        },
        ws_client: null,
        ws_id: null,
        defaultOutputWidget: "kbaseDefaultNarrativeOutput",
        defaultInputWidget: "kbaseDefaultNarrativeInput",
        errorWidget: "kbaseNarrativeError",

        // constants.
        KB_CELL: 'kb-cell',
        KB_TYPE: 'type',
        KB_FUNCTION_CELL: 'function_input',
        KB_OUTPUT_CELL: 'function_output',
        KB_ERROR_CELL: 'kb_error',
        KB_CODE_CELL: 'kb_code',

        init: function(options) {
            this._super(options);

            var self = this;
            // Whenever the notebook gets loaded, it should rebind things.
            // This *should* only happen once, but I'm putting it here anyway.

            $([IPython.events]).on('notebook_loaded.Notebook', $.proxy(function() {
                this.rebindActionButtons();
                this.hideGeneratedCodeCells();
            }), this);

            $(document).on('workspaceUpdated.Narrative', 
                $.proxy(function(e, ws_id) {
                    console.log(ws_id);
                    this.ws_id = ws_id;
                }, 
                this)
            );

            $(document).on('dataUpdated.Narrative', 
                $.proxy(function(event) {
                    if (IPython && IPython.notebook) {
                        this.renderFunctionInputs();
                    }
                },
                this)
            );

            // When a user clicks on a function, this event gets fired with
            // method information. This builds a function cell out of that method
            // and inserts it in the right place.
            $(document).on('function_clicked.Narrative', function(event, method) {
                self.buildFunctionCell(method);
            });

            // Build the list of available functions.
            $("#function-test").kbaseNarrativeFunctionPanel({});

            // Initialize the data table.
//            this.initDataTable(options.tableElem);
            this.initControls(options.controlsElem);

            // bind search to data table
            $search_inp = options.controlsElem.find(':input');
            var that = this;
            $search_inp.on('change keyup', function(e) {
                var tbl = that.dataTableWidget.table;
                tbl.fnFilter($search_inp.val());
                tbl.fnDraw();
            });

            // **DEPRECATED** Initializes controls.
            this.initFuncs();

            this.render();
            return this;
        },
        
        /**
         * Initialize controls at top of workspace view.
         *
         * @param elem Workspace view element
         * @returns this
         */
        initControls: function(elem) {
            console.debug('initControls.begin');
            var $search = $('<div>').addClass('kb-search')
            var $search_inp = $('<input>').attr('type', 'text');
            $search.append($search_inp);
            $search.append($('<i>').addClass('icon-search'));
            elem.append($search);
            // populate the dropdown
            var $dd_menu = $('<div>').addClass('dropdown').attr({id:'kb-ws-upload-pulldown'});
            var $dd_toggle = $('<a>').addClass("dropdown-toggle").attr({'data-toggle':'dropdown',
                            href: '#', id: 'kb-ws-add-data'}).text('+ Add');
            $dd_menu.append($dd_toggle);
            var ul = $('<ul>').addClass('dropdown-menu').attr({role: 'menu', 'aria-labelledby': 'dLabel'});
            ul.append($('<li>').addClass('nav-header').text('Add data from..'));
            ul.append($('<li>').addClass('divider'));
            var dd_items = { // key: [label, element_id]
                'upload': {label:'Local file', id: 'kb-ws-upload-local'},
                'cds': {label:'Central Data Store', id:'kb-ws-upload-cds'}
            }
            $.each(dd_items, function(key, info) {
                var item = $('<li>');
                item.append($('<a>').attr({'href': '#', 'id': info.id}).text(info.label));
                ul.append(item);
            })
            $dd_menu.append(ul);
            // add to element
            elem.append($dd_menu);
            // activate the dropdown
            $dd_toggle.dropdown();
            // bind the upload action
            var $dlg = $('#kb-ws-upload-dialog');
            var opts = {$anchor: $('#' + dd_items.upload.id),
                        ws_parent: this};
            this.uploadWidget_dlg = $dlg //$dlg.kbaseUploadWidget;
            this.uploadWidget_opts = opts;
            // Add a 'refresh' button, bound to this widget's render() function
            var $refresh = $('<button>')
                .addClass('btn btn-default btn-sm')
                .attr({'type': 'button', 'id': 'kb-ws-refresh'});
                //.text("Refresh");
            // XXX: BS-3 glyphicons aren't working
            //$refresh.append($('<span>').addClass("glyphicon glyphicon-refresh"));
            $refresh.append($('<i>').addClass('icon-refresh'));
            elem.append($refresh);
            var self = this;
            elem.on('click', function(e) {
                console.debug("refresh.begin");
                self.render();
                console.debug("refresh.end");
            });
            // done

            return this;
        },

        /**
         * Initialize the data table in the workspace view
         *
         * @param elem Data table parent element
         * @returns this
         */
        // initDataTable: function(elem) {
        //     this.dataTableWidget = elem.kbaseWorkspaceDataWidget({
        //         loadingImage: this.options.loadingImage,
        //         container: elem
        //      });
        //     return this;
        // },

        /**
         * Set up interactive features of the function-list panel.
         */
        initFuncs: function() {
            var env = this;
            $('.kb-function-body ul li').each(function(index) {
                var $anchor = $(this).find('a');
                this.name = $anchor.data('name');
                var self = this;
                // Add cell for function
                $anchor.click(function() {
                    env.addCellForFunction(self.name);
                });
                // Help for function
                var $anchor2 = $(this).find('span.kb-function-help');
                this.help = $anchor2.data('help');
                this.help_title = $anchor2.data('name');
                $anchor2.click(function() {
                    console.debug("help asked for");
                    var $elt = $('#kb-function-help');
                    $elt.addClass("alert alert-info");
                    $elt.html("<h1>" + self.help_title + " help</h1>" + 
                              self.help + 
                              "<h2>Click to hide</h2>");
                    $elt.click(function() {
                        $(this).hide();
                    });
                    $elt.show();
                });
            });
        },

        /**
         * @method buildFunctionCell
         * @param {Object} method - the JSON schema version of the method to invoke. This will
         * include a list of parameters and outputs.
         */
        buildFunctionCell: function(method) {
            console.log(method);

            var cell = IPython.notebook.insert_cell_below('markdown');
            // make this a function input cell, as opposed to an output cell
            this.setFunctionCell(cell, method);

            // THIS IS WRONG! FIX THIS LATER!
            // But it should work for now... nothing broke up to this point, right?
            var cellIndex = IPython.notebook.ncells() - 1;
            var cellId = 'kb-cell-' + cellIndex + "-" + this.uuidgen();

            // The various components are HTML STRINGS, not jQuery objects.
            // This is because the cell expects a text input, not a jQuery input.
            // Yeah, I know it's ugly, but that's how it goes.
            var cellContent;

            if (this.validateMethod(method)) {
                // This is the list of parameters for the given method
//                var inputs = this.buildFunctionInputs(method, cellId);
                var inputWidget = this.defaultInputWidget;
                if (method.properties.widgets.input_widget)
                    inputWidget = method.properties.widgets.input_widget;

                var inputDiv = "<div id='inputs'></div>";

                // These are the 'delete' and 'run' buttons for the cell
                var buttons = "<div class='buttons pull-right' style='margin-top:10px'>" +
                                  "<button id='" + cellId + "-delete' type='button' value='Delete' class='btn btn-warning'>Delete</button> " +
                                  "<button id='" + cellId + "-run' type='button' value='Run' class='btn btn-primary'>Run</button>" + 
                              "</div>";

                // The progress bar remains hidden until invoked by running the cell
                var progressBar = "<div id='kb-func-progress' style='display:none;'>" +
                                    "<div class='progress progress-striped active kb-cell-progressbar'>" +
                                        "<div class='progress-bar progress-bar-success' role='progressbar' aria-valuenow='0' " +
                                        "aria-valuemin='0' aria-valuemax='100' style='width:0%'/>" +
                                    "</div>" +
                                    "<p class='text-success'/>" +
                                  "</div>";

                // Bringing it all together...
                cellContent = "<div class='kb-cell-run' " + "id='" + cellId + "'>" + 
                                  "<h1>" + method.title + "</h1>" +
                                  "<div>" +  
                                      inputDiv +
                                      buttons + 
                                  "</div>" +
                                  progressBar +
                              "</div>\n" + 
                              "<script>" + 
                              "$('#" + cellId + " > div > #inputs')." + inputWidget + "({ method:'" + JSON.stringify(method) + "'});" +
                              "</script>";
            }
            else {
                cellContent = "Error - the selected method is invalid.";
            }
            cell.set_text(cellContent);

            cell.rendered = false;
            cell.render();

            this.removeCellEditFunction(cell);
            this.bindActionButtons(cell);
        },

        /**
         * Refreshes any function inputs to sync with workspace data.
         * Since this re-renders the cell, it must rebind all buttons, too.
         * Kind of annoying, but it should run quickly enough.
         * @private
         */
        renderFunctionInputs: function() {
            if (IPython && IPython.notebook) {
                var cells = IPython.notebook.get_cells();
                for (var i=0; i<cells.length; i++) {
                    var cell = cells[i];
                    if (this.isFunctionCell(cell)) {
//                    if (cell.metadata && cell.metadata['kb-cell'] && cell.metadata['kb-cell']['type'] == this.FUNCTION_CELL) {
                        cell.rendered = false;
                        cell.render();
                        this.bindActionButtons(cell);
                    }
                }
            }
        },


        /**
         * Builds the input div for a function cell, based on the given method object.
         * @param {Object} method - the method being constructed around.
         * @returns {String} an HTML string describing the available parameters for the cell.
         * @private
         */
        buildFunctionInputs: function(method, cellId) {
            var inputDiv = "<div class='kb-cell-params'><table class='table'>";
            var params = method.properties.parameters;
            for (var i=0; i<Object.keys(params).length; i++) {
                var p = 'param' + i;
                inputDiv += "<tr style='border:none'>" + 
                                "<td style='border:none'>" + params[p].ui_name + "</td>" + 
                                "<td style='border:none'><input type='text' name='" + p + "' value=''></input></td>" +
                                "<td style='border:none'>" + params[p].description + "</td>" +
                            "</tr>";
            }
            inputDiv += "</table></div>";

            return inputDiv;
        },

        /**
         * Checks if the given method object has a minimally valid structure.
         * Each method needs the following properties:
         * title - string, the title of the method (required non-empty)
         * service - string, the service where the method came from (required non-empty)
         * description - string, the description of the method
         * properties - object, contains parameters for the method
         * properties.parameters - object, essentially a list of parameters for the method
         *
         * @param {object} method - the method to validate
         * @private
         */
        validateMethod: function(method) {
            // if no title, return false
            if (!method.hasOwnProperty('title') || method.title.length == 0)
                return false;

            // if no service, return false
            if (!method.hasOwnProperty('service') || method.service.length == 0)
                return false;

            // if no properties, or it's not an object, return false
            if (!method.hasOwnProperty('properties') || typeof method.properties !== 'object')
                return false;

            if (!method.properties.hasOwnProperty('parameters') || typeof method.properties.parameters !== 'object')
                return false;

            return true;
        },

        /**
         * @method removeCellEditFunction
         * Removes the ability to edit a markdown cell by double-clicking or pressing Enter.
         * Handy for dealing with KBase function or output cells.
         * @param cell - the cell to modify.
         * @private
         */
        removeCellEditFunction: function(cell) {
            // remove its double-click and return functions. sneaky!
            $(cell.element).off('dblclick');
            $(cell.element).off('keydown');
        },

        /**
         * @method bindActionButtons
         * Binds the action (delete and run) buttons of a function cell.
         * This requires the cell to have {'kb-cell' : 'function'} in its metadata, otherwise it's ignored.
         * @param cell - the IPython Notebook cell with buttons to be bound.
         * @private
         */
        bindActionButtons: function(cell) {
            // get the cell.
            // look for the two buttons.
            // bind them to the right actions.
            if (this.isFunctionCell(cell)) {
                $(cell.element).find(".buttons [id*=delete]").off('click');
                $(cell.element).find(".buttons [id*=delete]").click(this.bindDeleteButton());
                $(cell.element).find(".buttons [id*=run]").off('click');
                $(cell.element).find(".buttons [id*=run]").click(this.bindRunButton());
            }
        },

        /**
         * Once the notebook is loaded, all code cells with generated code
         * (e.g. the placeholder, provenance cells) should be hidden.
         * At least for now.
         * So this function does that.
         * @private
         */
        hideGeneratedCodeCells: function() {
            var cells = IPython.notebook.get_cells();
            for (var i=0; i<cells.length; i++) {
                var cell = cells[i];
                if (this.isFunctionCodeCell(cell))
                    cell.element.css('display', 'none');
            }
        },

        isFunctionCell: function(cell) {
            return this.checkCellType(cell, this.KB_FUNCTION_CELL);
        },

        setFunctionCell: function(cell, method) {
            var cellInfo = {}
            cellInfo[this.KB_TYPE] = this.KB_FUNCTION_CELL;
            cellInfo['method'] = method;

            cell.metadata[this.KB_CELL] = cellInfo;
        },

        isOutputCell: function(cell) {
            return this.checkCellType(cell, this.KB_OUTPUT_CELL);
        },

        setOutputCell: function(cell) {
            var cellInfo = {};
            cellInfo[this.KB_TYPE] = this.KB_OUTPUT_CELL;
            cell.metadata[this.KB_CELL] = cellInfo;
        },

        isFunctionCodeCell: function(cell) {
            return this.checkCellType(cell, this.KB_CODE_CELL);
        },

        setCodeCell: function(cell) {
            var cellInfo = {};
            cellInfo[this.KB_TYPE] = this.KB_CODE_CELL;
            cell.metadata[this.KB_CELL] = cellInfo;
        },

        checkCellType: function(cell, type) {
            return cell.metadata &&
                   cell.metadata[this.KB_CELL] &&
                   cell.metadata[this.KB_CELL][this.KB_TYPE] === type;
        },

        /**
         * @method bindRunButton
         * @private
         */
        bindRunButton: function() {
            var self = this;
            return (
                function(event) {
                    event.preventDefault();
                    var cell = IPython.notebook.get_selected_cell();
                    var paramList = [];
                    $(cell.element).find("[name^=param]").filter(":input").each(function(key, field) {
                        console.log(field.name + "=" + field.value);
                        paramList.push(field.value);
                    });
                    var method = cell.metadata[self.KB_CELL].method;

                    self.runCell()(cell, method.service, method.title, paramList);
                }
            );
        },

        /**
         * @method bindDeleteButton
         * @private
         */
        bindDeleteButton: function() {
            var self = this;
            return( 
                function(event) {
                    event.preventDefault();
                    var idx = IPython.notebook.get_selected_index();
                    IPython.notebook.delete_cell(idx);
                }
            );
        },

        /**
         * @method rebindActionButtons
         * Rebinds all the run buttons to their original function.
         * This iterates over all cells, looking for a 'kb-cell' field in its metadata.
         * If it finds it, it removes the double-click and keyboard-enter abilities from the cell.
         * If that 'kb-cell' field === 'function', it rebinds the delete and run buttons as well.
         *
         * @public
         */
        rebindActionButtons: function() {
            if (!(IPython && IPython.notebook))
                return;
            
            // Rewrite the following to iterate using the IPython cell
            // based methods instead of DOM objects

            var cells = IPython.notebook.get_cells();

            // not using $.each because its namespacing kinda screws things up.
            for (var i=0; i<cells.length; i++) {
                var cell = cells[i];
                var cellType = cell.metadata[this.KB_CELL];
                if (cellType) {
                    this.removeCellEditFunction(cell);
                    if (this.isFunctionCell(cell)) { //cellType[this.KB_TYPE] == this.FUNCTION_CELL) {
                        this.bindActionButtons(cell);
                    }
                }
            }
        },

        /**
         * Run a function cell
         * The cell should contain all the information it needs to run.
         *
         * @param {Object} cell - the cell that needs to be run
         * @param {}
         * @private
         */
        runCell: function() {
            var self = this;
            return function(cell, service, method, params) {
                var nb = IPython.notebook;
                var currentIndex = nb.get_selected_index();
                var codeCell = nb.insert_cell_below('code', currentIndex);
                self.setCodeCell(codeCell);
                codeCell.element.css('display', 'none');

                var callbacks = {
                    'execute_reply' : function(content) { self.handleExecuteReply(cell, content); },
                    'output' : function(msgType, content) { self.handleOutput(cell, msgType, content); },
                    'clear_output' : function(content) { self.handleClearOutput(cell, content); },
                    'set_next_input' : function(text) { self.handleSetNextInput(cell, content); },
                    'input_request' : function(content) { self.handleInputRequest(cell, content); },
                };

                var code = self.buildRunCommand(service, method, params);
                codeCell.set_text(code);
                codeCell.output_area.clear_output(true, true, true);
                codeCell.set_input_prompt('*');
//                console.debug('Running function: ' + service + '.' + method);

                $(cell.element).find('#kb-func-progress').css({'display': 'block'});
                nb.kernel.execute(code, callbacks, {silent: true});
            };
        },

        /**
         * Stitches together the command needed to run a method in the IPython kernel.
         * It is assumed that params is a list, with all values in the right order.
         * @param {String} service - the registered service name
         * @param {String} method - the registered method name
         * @param {Array} params - a list of parameter values
         * @returns {String} the constructed IPython kernel command
         * @private
         */
        buildRunCommand: function(service, method, params) {
            var cmd = "import biokbase.narrative.common.service as Service\n" +
                      "method = Service.get_service('" + service + "').get_method('" + method + "')\n" +
                      "import os; os.environ['KB_WORKSPACE_ID'] = '" + this.ws_id + "'\n" +
                      "os.environ['KB_AUTH_TOKEN'] = '" + this.ws_auth + "'\n";

            var paramList = params.map(function(p) { return '"' + p + '"'; });
            cmd += "method(" + paramList + ")";
//            console.debug(cmd);
            return cmd;
        },

        /**
         * Make JS dict into Python dict (string)
         */
         _pythonDict: function(data) {
            var dict = "{";
            $.each(data, function(key, value) {
                dict += "'" + key + "': ";
                // XXX: assume either more maps or simple type
                var vtype = typeof value;
                switch(vtype) {
                    case "boolean":
                        if (value)
                            dict += "True";
                        else
                            dict += "False";
                        break;
                    case "number":
                        dict += value;
                        break;
                    case "string":
                        dict += "'" + value + "'";
                        break;
                    case "undefined":
                        dict += "None";
                        break;
                    case "object":
                        dict += this._pythonDict(value);
                        break;
                    default:
                        console.error("Cannot convert to Python:", vtype);
                }
                dict += ", "
            });
            return dict + "}";
         },

        /* ------------------------------------------------------
         * Functions to handle running code.
         */
        /**
         * @method _handle_execute_reply
         * @private
         */
        handleExecuteReply: function (cell, content) {
            console.debug("Done running the function", content);
            this.showCellProgress(cell, "DONE", 0, 0);
            //this.set_input_prompt(content.execution_count);
            $([IPython.events]).trigger('set_dirty.Notebook', {value: true});
        },
        /**
         * @method _handle_set_next_input
         * @private
         */
        handleSetNextInput: function (cell, text) {
            var data = {'cell': this, 'text': text}
            $([IPython.events]).trigger('set_next_input.Notebook', data);
        },
        /**
         * @method _handle_input_request
         * @private
         */
        handleInputRequest: function (cell, content) {
            console.log("handle input request called");
            return;
            //this.output_area.append_raw_input(content);
        },
        /**
         * @method _handle_clear_output
         * @private
         */
        handleClearOutput: function (cell, content) {
            console.debug("handle clear output called");
            return;
            //this.clear_output(content.stdout, content.stderr, content.other);
        },

        /**
         * @method _handle_output
         */
        handleOutput: function (cell, msgType, content) {
            // copied from outputarea.js
            var buffer = "";
            if (msgType === "stream") {
                buffer += content.data;
                var lines = buffer.split("\n");
                var offs = 0, 
                    done = false, 
                    self = this,
                    result = "";

                $.each(lines, function(index, line) {
                    if (!done) {
                        if (line.length == 0) {
                            offs += 1; // blank line, move offset
                        }
                        else {
                            // look for @@S, @@P, @@D, or @@E
                            var matches = line.match(/^@@([SPDE])(.*)/);
                            if (matches) { // if we got one
                                if (matches[1] === 'S') {
                                    // if we're starting, init the progress bar.
                                }
                                else if (matches[1] === 'D') {
                                    // were done, so hide the progress bar (wait like a second or two?)
                                    self.resetProgress(cell);
                                }
                                else if (matches[1] === 'P') {
                                    // progress! capture the progress info and pass it along.
                                    var progressInfo = matches[2].split(',');
                                    if (progressInfo.length == 3) {
                                        self.showCellProgress(cell, progressInfo[0], progressInfo[1], progressInfo[2]);
                                        offs += line.length;
                                        if (index < lines.length - 1)
                                            offs += 1;
                                    }
                                    else
                                        done = true;
                                }
                                else if (matches[1] === 'E') {
                                    // Error!
                                    var errorJson = matches[2];
                                    self.createErrorCell(cell, errorJson);
//                                    self.createOutputCell(cell, 'kbaseNarrativeError({error: ' + errorJson + '})');
                                    self.dbg("Narrative error: " + errorJson);
                                }
                                else if (matches[1] === 'G') {
                                    // Debug statement.
                                    var debug = matches[2];
                                    self.dbg("[KERNEL] " + debug);
                                }
                            }
                            // No progress marker on non-empty line => final output of program?
                            else {
                                // XXX: @ and # should probably be swapped in meaning
                                // if (line.match(/^#/)) {
                                //     // log lines starting with '@'
                                //     console.info("[KERNEL] " + line.substr(1, line.length).trim());
                                //     // consume data
                                //     offs += line.length;
                                // }
                                // else {
                                    // save the line
                                    result += line;
                                    // all but the last line should have \n appended
                                    if (index < lines.length - 1) {
                                        result += "\n";
                                    }
                                // }
                            }
                        }
                    }
                });
                if (offs > 0) {
                    // if we found progress markers, trim processed prefix from buffer
                    buffer = buffer.substr(offs, buffer.length - offs);
                }
                if (result.length > 0) {
                    this.createOutputCell(cell, result);
                }
            }
        },

        createErrorCell: function(cell, errorJson) {
            var error = {
                'widget': this.errorWidget,
                'data': '{"error": ' + errorJson + "}",
                'embed': true
            };
            this.createOutputCell(cell, error);
        },

        /**
         * Result is an object with this structure:
         * widget - the widget to use (if null, then use kbaseDefaultNarrativeOutput)
         * data - the object to be passed in to the widget
         * embed - if true, then embed the widget and render it.
         */
        createOutputCell: function(cell, result) {
            if (typeof result === 'string')
                result = JSON.parse(result);

            console.log(result);

            if (!result.embed) {
                //do something.
                return;
            }

            var outputCell = this.addOutputCell(IPython.notebook.find_cell_index(cell));
            var uuid = this.uuidgen();

            // set up the widget line
            var widgetInvoker = "";
            if (result.widget && result.widget.length > 0)
                widgetInvoker = result.widget + "(" + result.data + ");";
            else
                widgetInvoker = this.defaultOutputWidget + "({'data' : " + result.data + "});";

            var cellText = ['<div id="'+uuid+'"></div>',
                            '<script>',
                            '$("#'+uuid+'").' + widgetInvoker, 
                            // Make the element a little bigger,
                            '$("#'+uuid+'").css({margin: "-10px"});',
                            // Disable most actions on this element'
                            '$("#'+uuid+'").off("click dblclick keydown keyup keypress focus");',
                            '</script>'].join('\n');
            console.log(cellText);
            outputCell.set_text(cellText);
            outputCell.rendered = false; // force a render
            outputCell.render();
        },

        /**
         * @method resetProgress
         * @private
         * Resets the progress bar in the given cell to not show any progress or progress message.
         * @param cell - the IPython notebook cell to reset.
         */
        resetProgress: function(cell) {
            var $progressBar = $(cell.element).find("#kb-func-progress .kb-cell-progressbar .progress-bar");
            $progressBar.css('width', '0%');

            var $progressMsg = $(cell.element).find("#kb-func-progress .text-success");
            $progressMsg.text("");
        },

        /**
         * @method showCellProgress
         *
         * Shows current progress in a running IPython function.
         * @param cell - the cell being run
         * @param name - the text of the progress to set
         * @param done - the number of steps finished.
         * @param total - the total number of steps to go through.
         *
         * @private
         */
        showCellProgress: function(cell, name, done, total) {
            var percentDone = 0;

            var $progressBar = $(cell.element).find("#kb-func-progress .kb-cell-progressbar .progress-bar");
            var $progressMsg = $(cell.element).find("#kb-func-progress .text-success");
            if (name === 'DONE') {
                $progressMsg.text("Completed");
                percentDone = 100;
                $progressBar.css('width', '100%');
                $(cell.element).find("#kb-func-progress").fadeOut(1000);
            }
            else {
                $progressMsg.text("Step " + done + " / " + total + ": " + name);
                percentDone = (100 * done - 100) / total;
                $progressBar.css('width', percentDone + '%');
            }
        },

        /**
         * Add a new cell for output of the script.
         *
         * The cell is added below the cell in currentIndex. This position
         * should be set by the calling function to represent the position of
         * the calling function cell.
         *
         * @method _addOutputCell
         * @private
         * @return id of <div> inside cell where content can be placed
         */
        addOutputCell: function(currentIndex) {
            var nb = IPython.notebook;
            var cell = nb.insert_cell_below('markdown', currentIndex);

            cell.metadata['kb-cell'] = 'output';
            this.removeCellEditFunction(cell);

            return( cell );
        },

        /** Not really used right now. */
        convert_mime_types: function (json, data) {
            if (data === undefined) {
                return json;
            }
            if (data['text/plain'] !== undefined) {
                json.text = data['text/plain'];
            }
            if (data['text/html'] !== undefined) {
                json.html = data['text/html'];
            }
            if (data['image/svg+xml'] !== undefined) {
                json.svg = data['image/svg+xml'];
            }
            if (data['image/png'] !== undefined) {
                json.png = data['image/png'];
            }
            if (data['image/jpeg'] !== undefined) {
                json.jpeg = data['image/jpeg'];
            }
            if (data['text/latex'] !== undefined) {
                json.latex = data['text/latex'];
            }
            if (data['application/json'] !== undefined) {
                json.json = data['application/json'];
            }
            if (data['application/javascript'] !== undefined) {
                json.javascript = data['application/javascript'];
            }
            return json;
        },

        /* ------------------------------------------------------ */
        /* Accessors */

        workspace : function(key, value) {
            return this._accessor('_workspace', key, value);
        },

        _accessor : function(name, key, value) {
            if (this.data(name) == undefined) {
                this.data(name, {});
            }

            var obj = this.data(name);

            if (arguments.length == 2) {
                obj[key] = value;
            }

            if (arguments.length > 0) {
                return obj[key];
            }
            else {
                return obj;
            }
        },

        /* ------------------------------------------------------ */

        /**
         * Render the widgets.
         *
         * @returns this
         */
        render: function() {
            this.rebindActionButtons();
            this.hideGeneratedCodeCells();
            this.trigger('updateData.Narrative');
            return this;
        },

        /**
         * Log in to all the widgets.
         *
         * @param token
         * @returns this
         */
        loggedIn: function(token) {
            this.ws_client = new workspaceService(this.options.workspaceURL);
            this.ws_auth = token;
            var un = token.match(/un=[\w_]+|/);
            this.ws_user = un[0].substr(3, un[0].length - 3);
            // grab ws_id to give to, e.g., upload widget

            //this.dataTableWidget.loggedIn(this.ws_client, this.ws_auth).ws_id;
            this.workspace("id", this.ws_id); // add to global accessor
            // create/refresh the upload dialog, which needs login to populate types
            this.uploadWidget = this.uploadWidget_dlg.kbaseUploadWidget(this.uploadWidget_opts);
            //this.uploadWidget.createDialog(); -- redundant
            this.render();
        },

        /**
         * Log out from all the widgets.
         *
         * @param token
         * @returns this
         */
        loggedOut: function(token) {
            this.dataTableWidget.loggedOut(token);
            this.ws_client = null, this.ws_auth = null;
        },

        /**
         * Initialize the logger
         */
        initLogging: function(level) {
            Logger.useDefaults();
            Logger.setLevel(level);
        },
        /**
         * uuid generator
         *
         * @private
         */
        uuidgen: function() {
            return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                var r = Math.random()*16|0, v = c == 'x' ? r : (r&0x3|0x8);
                return v.toString(16);});
        },
    });

})( jQuery );