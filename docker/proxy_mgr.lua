--
-- REST based HTTP service that allows you to query/modify the contents of an
-- nginx shared memory DICT object.
--
-- bind this via an access_by_lua_file directive in nginx.conf
-- make sure that there is an nginx variable called uri_base in the current
-- context - it is used in parsing out the URI path
-- Used to implement a dynamic reverse proxy for KBase Narrative project
--
-- The following ngx.shared.DICT need to be declared in the main config, or
-- else use different names and pass them in during initialization:
--
-- proxy_map
-- proxy_state
-- proxy_last
-- proxy_mgr
--
-- Steve Chan
-- sychan@lbl.gov
--

local M={}

-- regexes for matching/validating keys and values
local key_regex = "[%w_%-%.]+"
local val_regex = "[%w_%-:%.]+"
local json = require('json')
local notemgr = require('notelauncher')

-- forward declare the functions in this module
local est_connections
local sweeper
local marker
local check_marker
local check_sweeper
local initialize
local set_proxy
local use_proxy
local idle_status
local new_container
local url_decode
local get_session
local discover

-- this are name/value pairs referencing ngx.shared.DICT objects
-- that we use to track docker containers. The ngx.shared.DICT
-- implementation only supports basic scalar types, so we need a
-- couple of these instead of using a common table object
-- proxy_map maps a session key (kbase token userid 'sychan') to an
--           ip/port proxy target ('127.0.0.1:49000')
-- proxy_last maps a session key (kbase token userid 'sychan') to a time value
--           (output from os.time()) when the proxy target was
--           last seen to be active
-- proxy_last_ip maps a session key (kbase token userid 'sychan') to an IP address
--           that was last seen connecting
-- proxy_state maps a session key (kbase token userid 'sychan') to a boolean that
--           flags if that proxy has been marked for reaping
--           a true value means that the proxy is considered alive
--           and a false value means the instance is ready to be
--           reaped
local proxy_map = nil
local proxy_last = nil
local proxy_last_ip = nil
local proxy_state = nil

-- This is a dictionary for storing proxy manager internal state
-- The following names are currentl supported
-- 'next_sweep' - this stores the next time() the reap_sweeper is scheduled
--                 to be run. It is cleared when the sweeper runs, and
--                 set when the sweeper is rescheduled. If we notice that
--                 'next_sweep' is either relatively far in the past, or
--                 not set, we generate a warning in the logs and schedule
--                 an semi-immediate asynchronous sweeper run
-- 'next_mark' - this stores the next time() the reap_marker is scheduled
--                 to be run. It is cleared when the marker runs, and
--                 set when the marker is rescheduled. If we notice that
--                 'next_mark' is either relatively far in the past, or
--                 not set, we generate a warning in the logs and schedule
--                 an immediate marker run
local proxy_mgr = nil

-- strangely, init_by_lua seems to run the initialize() method twice,
-- use this flag to avoid reinitializing
local initialized = nil

-- Command to run in order to get netstat info for tcp connections in
-- pure numeric form (no DNS or service name lookups)
local NETSTAT = 'netstat -nt'

-- How often (in seconds) does the sweeper wake up to delete dead
-- containers?
M.sweep_interval = 300


-- How often (in seconds) does the marker wake up to mark containers
-- for deletion?
M.mark_interval = 60

-- How long (in seconds) since we last saw activity on a container should we wait before
-- shutting it down?
M.timeout = 180

-- How long (in seconds) after we mark an instance for deletion should we try to sweep it?
M.sweep_delay = 30

-- Default URL for authentication failure redirect, defaults to nil which means just error
-- out without redirect
M.auth_redirect = "http://gologin.kbase.us/?redirect=%s"

--
-- Function that runs a netstat and returns a table of foreign IP:PORT
-- combinations and the number of observed ESTABLISHED connetions (at
-- least 1)
--
est_connections = function()
		     local connections = {}
		     local handle = io.popen( NETSTAT, 'r')
		     if handle then
			netstat = handle:read('*a')
			handle:close()
			for conn in string.gmatch(netstat,"[%d%.]+:[%d]+ + ESTABLISHED") do
			   ipport = string.match( conn, "[%d%.]+:[%d]+")
			   if connections[ipport] then
			      connections[ipport] = connections[ipport] + 1
			   else
			      connections[ipport] = 1
			   end
			end
		     else
			ngx.log( ngx.ERR, string.format("Error trying to execute %s", NETSTAT))
		     end
		     return connections
		  end

--
-- Reaper function that looks in the proxy_state table for instances that need to be
-- removed and removes them
sweeper = function(self)
	     ngx.log( ngx.INFO, "sweeper running")
	     proxy_mgr:delete('next_sweep')

	     local keys = proxy_state:get_keys() 
	     for key = 1, #keys do
		name = keys[key]
		if proxy_state:get(name) == false then
		   ngx.log( ngx.INFO, "sweeper removing ",name)
		   local success, err = pcall( notemgr.remove_notebook, name)
		   if success then
		      proxy_map:delete(name)
		      proxy_state:delete(name)
		      proxy_last:delete(name)
		      proxy_last_ip:delete(name)
		      ngx.log( ngx.INFO, "notebook removed")
		   elseif string.find(err, "does not exist") then
		      ngx.log( ngx.INFO, "notebook nonexistent - removing references")
		      proxy_map:delete(name)
		      proxy_state:delete(name)
		      proxy_last_ip:delete(name)
		      proxy_last:delete(name)
		   else
		      ngx.log( ngx.ERROR, string.format("error: %s", err))
		   end
		end
	     end
	     -- enqueue ourself again
	     check_sweeper()
	  end

-- Check for a sweeper in the queue and enqueue if necessary
check_sweeper = function(self)
		   local next_run = proxy_mgr:get('next_sweep')
		   if next_run == nil then -- no sweeper in the queue, put one into the queue!
		      ngx.log( ngx.ERR, string.format("enqueuing sweeper to run in  %d seconds",M.sweep_interval))
		      local success, err = ngx.timer.at(M.sweep_interval, sweeper)
		      if success then
			 proxy_mgr:set('next_sweep', os.time() + M.sweep_interval)
		      else
			 ngx.log( ngx.ERR, string.format("Error enqueuing sweeper to run in %d seconds: %s",
							 M.sweep_interval,err ))
		      end
		      return(false)
		   end
		   return(true)
		end

--
-- Reaper function that examines containers to see if they have been idle for longer than
-- M.timeout and then marks them for cleanup
--
marker = function(self)
	    ngx.log( ngx.INFO, "marker running")
	    proxy_mgr:delete('next_mark')
	    local keys = proxy_last:get_keys() 
	    local now = os.time()
	    local timeout = now - M.timeout

	    -- fetch currently open connections
	    local conn = est_connections()

	    for key = 1, #keys do
	       name = keys[key]
	       local target = proxy_map:get( name)
	       ngx.log( ngx.INFO, string.format("Checking %s -> %s", name, target))
	       if conn[target] then
		  ngx.log( ngx.INFO, string.format("Found %s among current connections", name))
		  success, err = proxy_last:set(name, now)
		  if not success then
		     ngx.log( ngx.ERR, string.format("Error setting proxy_last[ %s ] from established connections: %s",
						     name,err ))
		  end
	       else -- not among current connections, check for reaping
		  local last, flags = proxy_last:get( name)
		  if last <= timeout then
		     -- reap it
		     ngx.log( ngx.INFO, string.format("Marking %s for reaping - last seen %s",
						      name,os.date("%c",last)))
		     proxy_state:set(name,false)
		  end
	       end
	    end
	    check_sweeper()
	    -- requeue ourselves
	    check_marker()
	 end

-- This function just checks to make sure there is a sweeper function in the queue
-- returns true if there was one, false otherwise
check_marker = function(self)
		  local next_run = proxy_mgr:get('next_mark')
		  if next_run == nil then -- no marker in the queue, put one into the queue!
		     ngx.log( ngx.ERR, string.format("enqueuing marker to run in %d seconds",M.mark_interval))
		     local success, err = ngx.timer.at(M.mark_interval, marker)
		     if success then
			proxy_mgr:set('next_mark', os.time() + M.mark_interval)
		     else
			ngx.log( ngx.ERR, string.format("Error enqueuing marker to run in %d seconds: %s",
							M.mark_interval,err ))
		     end
		     return(false)
		  end
		  return(true)
	       end

--
-- Do some initialization for the proxy manager.
-- Named parameters are:
--     reap_interval - number of seconds between runs of the reaper, unused for now
--     idle_timeout  - number of seconds since last activity before a container is reaped
--     proxy_map - name to use for the nginx shared memory proxy_map
--     proxy_last - name to use for the nginx shared memory last connection access time
--
initialize = function( self, conf )
		if conf then
		   for k,v in pairs(conf) do
		      ngx.log( ngx.INFO, string.format("conf(%s) = %s",k,tostring(v)))
		   end
		else
		   conf = {}
		end
		if not initialized then
		   initialized = os.time()
		   M.sweep_interval = conf.sweep_interval or M.sweep_interval
		   M.mark_interval = conf.mark_interval or M.mark_interval
		   M.timeout = conf.idle_timeout or M.timeout
		   M.auth_redirect = conf.auth_redirect or M.auth_redirect
		   proxy_map = conf.proxy_map or ngx.shared.proxy_map
		   proxy_last = conf.proxy_last or ngx.shared.proxy_last
		   proxy_last_ip = conf.proxy_last_ip or ngx.shared.proxy_last_ip
		   proxy_state = conf.proxy_state or ngx.shared.proxy_state
		   proxy_mgr = conf.proxy_mgr or ngx.shared.proxy_mgr

		   ngx.log( ngx.INFO, string.format("Initializing proxy manager: sweep_interval %d mark_interval %d idle_timeout %d auth_redirect %s",
						    M.sweep_interval,M.mark_interval, M.timeout, tostring(M.auth_redirect)))
		else
		   ngx.log( ngx.INFO, string.format("Initialized at %d, skipping",initialized))
		end
	     end

-- This function is used to implement the rest interface
set_proxy = function(self)
	       local uri_key_rx = ngx.var.uri_base.."/("..key_regex ..")"
	       local uri_value_rx = ngx.var.uri_base.."/"..key_regex .."/".."("..val_regex..")$"
	       local method = ngx.req.get_method()
	       -- get the reaper functions into the run queue if not already
	       check_marker()
	       if method == "POST" then
		  local response = {}
		  local argc = 0
		  ngx.req:read_body()
		  local args = ngx.req:get_post_args()
		  if not args then
		     response["msg"] = "failed to get post args: "
		     ngx.status = ngx.HTTP_BAD_REQUEST
		  else
		     for key, val in pairs(args) do
			key2 = string.match( key, "^"..key_regex.."$")
			val2 = string.match( val, "^"..val_regex.."$")
			if key2 ~= key then
			   response["msg"] = "malformed key: " .. key
			   ngx.status = ngx.HTTP_BAD_REQUEST
			elseif val == "" or val2 ~= val then
			   response["msg"] = "malformed value : " .. val
			   ngx.status = ngx.HTTP_BAD_REQUEST
			elseif type(val) == "table" then
			   response["msg"] = "bad post argument: " .. key
			   ngx.status = ngx.HTTP_BAD_REQUEST
			   break
			else
			   argc = argc + 1
			   ngx.log( ngx.NOTICE, "Inserting: " .. key .. " -> " .. val)
			   success, err, force = proxy_map:add(key, val)
			   if not success then
			      ngx.status = ngx.HTTP_BAD_REQUEST
			      response["msg"] = "key insertion error " .. key .. " : " ..err
			      ngx.log( ngx.WARN, "Failed insertion: " .. key .. " -> " .. val)
			   end
			   -- add an entry for proxy state
			   success, err, force = proxy_state:add(key, true)
			   success, err, force = proxy_last:set(key,os.time())
			end
		     end
		     -- make sure we had at least 1 legit entry
		     if argc == 0 and response["msg"] == nil then
			response["msg"] = "No legitimate keys found"
		     end

		     if response["msg"] == nil then
			ngx.status = ngx.HTTP_CREATED
			response["msg"] = "Successfully added "..argc.." keys"
		     end
		  end
		  ngx.say(json.encode( response ))
	       elseif method == "GET" then
		  local response = {}

		  -- Check URI to see if a specific proxy entry is being asked for
		  -- or if we just dump it all out
		  local uri_base = ngx.var.uri_base
		  local key = string.match(ngx.var.uri,uri_key_rx)
		  if key then
		     local target, flags = proxy_map:get(key)
		     if target == nil then
			ngx.status = ngx.HTTP_NOT_FOUND
		     else
			response = target
		     end
		  else 
		     local keys = proxy_map:get_keys() 
		     for key = 1, #keys do
			local target, flags = proxy_map:get( keys[key])
			response[keys[key]] = target
		     end
		  end
		  ngx.say(json.encode( response ))
	       elseif method == "PUT" then
		  local response = {}

		  -- Check URI to make sure a specific key is being asked for
		  local uri_base = ngx.var.uri_base
		  local key = string.match(ngx.var.uri,uri_key_rx)
		  if key then
		     -- see if we have a uri of the form
		     -- $uri_base/{key}/{value}
		     val = string.match(ngx.var.uri,uri_value_rx)
		     if val == nil then
			val = ngx.req:get_body_data()
			val = string.match( val, val_regex)
		     end
		     if val then
			local success,err,forcible = proxy_map:set(key,val)
			if not success then
			   ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
			   response = err
			else
			   response = "updated"
			   success,err,forcible = proxy_state:set(key,true)
			   success,err,forcible = proxy_last:set(key,os.time())
			end
		     else
			ngx.status = ngx.HTTP_BAD_REQUEST
			response = "No value provided for key"
		     end
		  else 
		     response = "No key specified"
		     ngx.status = ngx.HTTP_NOT_FOUND
		  end
		  ngx.say(json.encode( response ))
	       elseif method == "DELETE" then
		  local response = {}

		  -- Check URI to make sure a specific key is being asked for
		  local uri_base = ngx.var.uri_base
		  local key = string.match(ngx.var.uri,uri_key_rx)
		  if key then
		     local target, flags = proxy_map:get(key)
		     if target == nil then
			ngx.status = ngx.HTTP_NOT_FOUND
		     else
			response = "Marked for reaping"
			-- mark the proxy instance for deletion
			proxy_state:set(key,false)
		     end
		  else 
		     response = "No key specified"
		     ngx.status = ngx.HTTP_NOT_FOUND
		  end
		  ngx.say(json.encode( response ))
	       else
		  ngx.exit( ngx.HTTP_METHOD_NOT_IMPLEMENTED )
	       end
	    end


--
-- simple URL decode function
url_decode = function(str)
   str = string.gsub (str, "+", " ")
   str = string.gsub (str, "%%(%x%x)",
		      function(h) return string.char(tonumber(h,16)) end)
   str = string.gsub (str, "\r\n", "\n")
  return str
end

--
-- Examines the current request to validate it and return a
-- session identifier. You can perform authentication here
-- and only return a session id if the authentication is legit
-- returns nil, err if a session cannot be found/created

get_session = function()
   local hdrs = ngx.req.get_headers()
   local cheader = hdrs['Cookie']
   local token = {}
   if cheader then
      -- ngx.log( ngx.INFO, string.format("cookie = %s",cheader))
      local session = string.match( cheader,"kbase_session=([%S]+);?")
      if session then
	 -- ngx.log( ngx.INFO, string.format("kbase_session = %s",session))
	 session = string.gsub(session,";$","")
	 session = url_decode(session)
	 for k, v in string.gmatch(session, "([%w_]+)=([^|]+);?") do
	    token[k] = v
	 end
	 if token['token'] then
	    token['token'] = string.gsub(token['token'],"PIPESIGN","|")
	    token['token'] = string.gsub(token['token'],"EQUALSSIGN","=")
	    --ngx.log( ngx.INFO, string.format("token[token] = %s",token['token']))
	 end
     end
   end
   if token['un'] then
      return token['un']
   else
      return nil, "No session id found"
   end
end

--
-- Check docker and update our list of containers
--
discover = function()
	      local notebooks = notemgr:get_notebooks()
	      ngx.log( ngx.INFO, json.encode(notebooks))
	      -- add any notebooks we don't know about
	      local k,v
	      for k,v in pairs(notebooks) do
		 if proxy_map:get(k) == nil then
		    ngx.log( ngx.INFO, "Discovered new container " .. k )
		    local success,err,forcible = proxy_map:set(k,v)
		    if not success then
		       ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
		       ngx.log( ngx.ERR, "Error setting proxy_map: " .. err)
		    end
		    success,err,forcible = proxy_last:set(k,os.time())
		    if not success then
		       ngx.log( ngx.WARN, "Error setting last seen timestamp proxy_last" )
		    end
		    success,err,forcible = proxy_state:set(k,true)
		    success,err,forcible = proxy_last_ip:set(k,client_ip)
		 end
	      end
	   end

--
-- Spin up a new instance
--
new_container = function( session_id)
		   ngx.log( ngx.INFO, "Creating new notebook instance " )
		   local status, res = pcall(notemgr.launch_notebook,session_key)
		   if status then
		      ngx.log( ngx.INFO, "New instance at: " .. res)
		      -- do a none blocking sleep for 2 seconds to allow the instance to spin up
		      ngx.sleep(5)
		      local success,err,forcible = proxy_map:set(session_key,res)
		      if not success then
			 ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
			 ngx.log( ngx.ERR, "Error setting proxy_map: " .. err)
			 response = "Unable to set routing for notebook " .. err
		      else
			 return res
		      end
		   else
		      ngx.log( ngx.ERR, "Failed to launch new instance :" .. res)
		   end
		end

--
-- Route to the appropriate proxy
--
use_proxy = function(self)
	       local target, flags
	       -- ngx.log( ngx.INFO, "In /narrative/ handler")
	       -- get the reaper functions into the run queue if not already
	       check_marker()
	       local client_ip = ngx.var.remote_addr
	       local session_key,err = get_session()
	       if session_key then
		  target, flags = proxy_map:get(session_key)
		  if target == nil then -- didn't find in proxy map, check containers
		     ngx.log( ngx.WARN, "Unknown proxy key:" .. session_key)
		     discover()
		  end
		  -- try to fetch the target again
		  target = proxy_map:get(session_key)
		  if target == nil then
		     target = new_instance( session_key)
		  end
	       else
		  ngx.log(ngx.WARN,"No session_key found!")
		  if M.auth_redirect then
		     local msg = string.format("Please try going to %s to authenticate and try again",
					       string.format( M.auth_redirect, ngx.escape_uri(ngx.var.request_uri)))
		     ngx.say( msg)
		  end
	       end
	       if target ~= nil then
		  ngx.var.target = target
		  ngx.log( ngx.INFO, "session: " .. session_key .. " target: " .. ngx.var.target )
		  local success,err,forcible = proxy_last:set(session_key,os.time())
		  if not success then
		     ngx.log( ngx.WARN, "Error setting last seen timestamp proxy_last" )
		  end
		  success,err,forcible = proxy_state:set(session_key,true)
		  success,err,forcible = proxy_last_ip:set(session_key,client_ip)
	       else
		  ngx.exit(ngx.HTTP_NOT_FOUND)
	       end
	    end

idle_status = function(self)
		 local uri_key_rx = ngx.var.uri_base.."/("..key_regex ..")"
		 local uri_value_rx = ngx.var.uri_base.."/"..key_regex .."/".."("..val_regex..")$"
		 local method = ngx.req.get_method()
		 local response = {}

		 -- run the reap marker to update state of all containers if there isn't one in the queue
		 local next_mark = proxy_mgr:get('next_mark')
		 if next_mark == nil or next_mark + 10 < os.time() then
		    ngx.log( ngx.WARN, "No marker in queue, performing immediate marker run")
		    marker()
		 end

		 -- Check URI to see if a specific proxy entry is being asked for
		 -- or if we just dump it all out
		 local uri_base = ngx.var.uri_base
		 local key = string.match(ngx.var.uri,uri_key_rx)
		 if key then
		    local last, flags = proxy_last:get(key)
		    if last == nil then
		       ngx.status = ngx.HTTP_NOT_FOUND
		    else
		       -- return the last timestamp and IP seen plus the status value
		       response = { last_seen = os.date("%c",last), last_ip = proxy_last_ip:get(key), active = tostring(proxy_state:get(key))}
		    end
		 else 
		    local keys = proxy_last:get_keys() 
		    for key = 1, #keys do
		       local last, flags = proxy_last:get( keys[key])
		       -- return the last timestamp and IP seen plus the status value
		       response[keys[key]] = { last_seen = os.date("%c",last), last_ip = proxy_last_ip:get(keys[key]), active = tostring(proxy_state:get(keys[key]))}
		    end
		 end
		 ngx.say(json.encode( response ))
	      end

M.set_proxy = set_proxy
M.use_proxy = use_proxy
M.initialize = initialize
M.idle_status = idle_status
M.est_connections = est_connections

return M