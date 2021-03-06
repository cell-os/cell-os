-- It provides methods to obtain the Mesos Master Leader, as well as its state.
--
--  It is included in the configuration files for Mesos and Marathon in order to
--  ensure that requests to Mesos API are routed to the Leader.

--  It also helps fixing an issue with the Mesos UI.
--  When the agents dwell in a private subnet the UI doesn't work correctly anymore
--  b/c it tries to directly access agents' API.
--  In order to fix this issue the Mesos API is modified so that the requests are routed back to the Gateway
--  by updating the address of the slaves before returning the response from master/state.json
--
-- User: ddascal
-- Date: 25/01/16
--

local cjson = require "cjson"

local _M = {}

---
-- the internal location to find the master.
-- i.e.:
-- location = /internal/master/redirect {
--    internal;
--    proxy_method GET;
--    proxy_pass_request_body off;
--    proxy_pass_request_headers off;
--    proxy_pass $mesos_uri/master/redirect;
-- }
local MASTER_REDIRECT_LOCATION = '/internal/master/redirect'

----
-- the internal location to retrieve the state.
-- i.e.:
-- location = /internal/master/state {
--    internal;
--    proxy_method GET;
--    proxy_pass_request_body off;
--    proxy_pass_request_headers off;
--    set $mesos_leader $arg_leader;
--    set_if_empty $mesos_leader $mesos_uri;
--    proxy_pass $mesos_leader/master/state.json;
-- }
local MASTER_STATE_LOCATION = '/internal/master/state'


--- Constructor
-- @param o An optional init object
--
function _M:new(o)
    local o = o or {}
    setmetatable(o, self)
    self.__index = self
    return o
end

local function getMesosLeaderFromCache()
    local dict = ngx.shared.cachedkeys -- cachedkeys is defined in conf.d/api_gateway_init.conf
    if dict == nil then
        ngx.log(ngx.WARN, "Could not read from dict `cachedkeys`. Please define it with 'lua_shared_dict cachedkeys 10m'")
        return nil
    end
    return dict:get("mesos_master_leader")
end

local function setMesosLeaderInCache(mesos_leader)
    local dict = ngx.shared.cachedkeys -- cachedkeys is defined in conf.d/api_gateway_init.conf
    if dict == nil then
        ngx.log(ngx.WARN, "Could not write to dict `cachedkeys`. Please define it with 'lua_shared_dict cachedkeys 10m'")
        return nil
    end
    local exptime_seconds = 10
    return dict:set("mesos_master_leader", mesos_leader, exptime_seconds)
end

local function invalidateLocalCache()
    local dict = ngx.shared.cachedkeys -- cachedkeys is defined in conf.d/api_gateway_init.conf
    if dict == nil then
        ngx.log(ngx.WARN, "Could not invalidate dict `cachedkeys`. Please define it with 'lua_shared_dict cachedkeys 10m'")
        return nil
    end
    return dict:delete("mesos_master_leader")
end

--- It uses the /master/redirect URI to detect the leader
--    It looks in the "Location" header to extract it
--    This method returns either the leader or nil
-- @param internal_location the internal location proxying to /master/redirect
local function getMesosLeaderFromMesosAPI(internal_location)
    local response = ngx.location.capture(internal_location)
    local loc = response.header["Location"]
    if loc == nil then
        ngx.log(ngx.WARN, tostring(internal_location), "Could not find the master. For status", tostring(response.status), " and body:", tostring(response.body))
        return nil
    end
    local m, err = ngx.re.match(loc, "(http[s]:)?(//)(?<host>.*)")
    if (m.host == nil or err ~= nil) then
        ngx.log(ngx.WARN, tostring(internal_location), " returned unknown Location header:", tostring(loc), ". Could not match the host. err=", err)
        return nil
    end

    return m.host
end

--- It returns the Mesos Leader either from the local cache or from /master/redirect response
-- NOTE: this cached leader might have changed since it was used last time
---
function _M:getMesosLeader()
    local cachedLeader = getMesosLeaderFromCache()
    if cachedLeader ~= nil then
        ngx.log(ngx.DEBUG, "Returning the mesos leader from shared cache:", tostring(cachedLeader))
        return cachedLeader
    end
    -- at this point we need to discover the leader as the cache is empty
    local discoveredLeader = getMesosLeaderFromMesosAPI(MASTER_REDIRECT_LOCATION)
    -- then cache the leader
    if discoveredLeader ~= nil then
        discoveredLeader = "http://" .. discoveredLeader
        ngx.log(ngx.DEBUG, "Discovered a new mesos leader at:", tostring(discoveredLeader))
        setMesosLeaderInCache(discoveredLeader)
        return discoveredLeader
    end
    ngx.log(ngx.WARN, "Could not discover mesos leader from ", tostring(MASTER_REDIRECT_LOCATION))
    return nil
end

--- It returns the state info from the Mesos Leader.
--   If the cached Mesos Leader is not leading anymore, it will lookup for a new leader and then retry once more.
-- @param update_slave_hostnames When true it updates the hostname and pid of each slave
--                               to point to the Gateway
--
function _M:getState(update_slave_hostnames)
    local leader = self:getMesosLeader()
    local response = ngx.location.capture(MASTER_STATE_LOCATION .. "?leader=" .. tostring(leader))
    local mesos_state = assert(cjson.decode(response.body),  'Could not decode ' .. tostring(response.body))

    if mesos_state.pid ~= mesos_state.leader then -- we've landed on a non-leader node
        ngx.log(ngx.DEBUG, "request landed on a non-leader mesos node:" .. tostring(leader))
        -- go back on the leader
        invalidateLocalCache()
        leader = self:getMesosLeader()
        if leader ~= nil then
            -- reload the state
            response = ngx.location.capture(MASTER_STATE_LOCATION .. "?leader=" .. tostring(leader))
            mesos_state = assert(cjson.decode(response.body), 'Could not decode ' .. tostring(response.body))
        end

    end

    if update_slave_hostnames == true then
        -- for Mesos 0.25 UI we need to replace the hostname and the pid fields
        -- the issue is in this commit: https://github.com/apache/mesos/commit/8e13a26e8514ca8be904f91f0fcc4c2fc74d71bc#diff-9f2e9a08332888bca98d111787b3a8c3R770
        -- JS should not assume all the slaves are accessible on their private IP address
        local host = ngx.var.host
        local port = ngx.var.http_x_forwarded_port or ngx.var.server_port
        local authority = host .. ":" .. port
        for _, slave in ipairs(mesos_state['slaves']) do
            slave.hostname = authority .. '/slave/' .. slave.id
            slave.pid = ngx.re.gsub(slave.pid, ":\\d+$", ':' .. port, 'jo')
        end
    end

    return mesos_state
end

--- It returns the private address of a given slave_id which could be an IP address or a hostname.
-- This is used by the Gateway to proxy requests to `/slave/<slave_id>/<api>` through to slave nodes: `<slave_address>/<api>`
-- @param slave_id The ID of the slave
--
function _M:getSlaveAddress(slave_id)
    local state = self:getState(false)
    for _, slave in ipairs(state['slaves']) do
        if slave['id'] == slave_id then
            local slave_address = ngx.re.gsub(slave['pid'], '.*@', '', 'jo')
            ngx.log(ngx.DEBUG, 'Resolved Mesos slave ', tostring(slave_id), ' to address: ', tostring(slave_address))
            return slave_address
        end
    end
    return nil
end

return _M

