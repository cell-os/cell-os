-- It provides methods to obtain the Mesos Master Leader, as well as its state
--
-- User: ddascal
-- Date: 25/01/16
--

local cjson = require"cjson"

local _M = {}

---
-- the internal location to find the master
local MASTER_REDIRECT_LOCATION = '/internal/master/redirect'

----
-- the internal location to retrieve the state
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
    if ( dict == nil ) then
        ngx.log(ngx.WARN, "Could not read from dict `cachedkeys`. Please define it with 'lua_shared_dict cachedkeys 10m'")
        return nil
    end
    return dict:get("mesos_master_leader")
end

local function setMesosLeaderInCache(mesos_leader)
    local dict = ngx.shared.cachedkeys -- cachedkeys is defined in conf.d/api_gateway_init.conf
    if ( dict == nil ) then
        ngx.log(ngx.WARN, "Could not write to dict `cachedkeys`. Please define it with 'lua_shared_dict cachedkeys 10m'")
        return nil
    end
    local exptime_seconds = 10
    return dict:set("mesos_master_leader", mesos_leader, exptime_seconds)
end

local function invalidateLocalCache()
    local dict = ngx.shared.cachedkeys -- cachedkeys is defined in conf.d/api_gateway_init.conf
    if ( dict == nil ) then
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
    if ( loc == nil ) then
        ngx.log(ngx.WARN, tostring(url), "Could not find the master. For status", tostring(response.status), " and body:", tostring(response.body))
        return nil
    end
    local m, err = ngx.re.match(loc, "(http[s]:)*(//)*(?<host>.*)")
    if ( m.host == nil or err ~= nil ) then
        ngx.log(ngx.WARN, tostring(internal_location), " returned unknown Location header:", tostring(loc), ". Could not match the host. err=", err )
        return nil
    end

    return m.host
end

--- It teturns the Mesos Leader.
-- NOTE: this cached leader might have changed since it was used last time
---
function _M:getMesosLeader()
    local cachedLeader = getMesosLeaderFromCache()
    if ( cachedLeader ~= nil ) then
        ngx.log(ngx.DEBUG, "Returning the mesos leader from shared cache:", tostring(cachedLeader))
        return cachedLeader
    end
    -- at this point we need to discover the Leader as no leader was found in cache
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


function _M:getState(update_slave_hostnames)
    local leader = self:getMesosLeader()
    local response = ngx.location.capture(MASTER_STATE_LOCATION .. "?leader=" .. tostring(leader))
    local mesos_state = assert(cjson.decode(response.body),  'Could not decode ' .. tostring(response.body))

    if mesos_state.pid ~= mesos_state.leader then -- we've landed on a non-leader node
        ngx.log(ngx.DEBUG, "request landed on a non-leader mesos node:" .. tostring(leader))
        -- go back on the leader
        invalidateLocalCache()
        leader = self:getMesosLeader()
        if ( leader ~= nil ) then
            -- reload the state
            response = ngx.location.capture(MASTER_STATE_LOCATION .. "?leader=" .. tostring(leader))
            mesos_state = assert(cjson.decode(response.body), 'Could not decode ' .. tostring(response.body))
        end

    end

    if update_slave_hostnames == true then
        -- for Mesos 0.25 UI we need to replace the hostname and the pid fields
        -- the issue is in this commit: https://github.com/apache/mesos/commit/8e13a26e8514ca8be904f91f0fcc4c2fc74d71bc#diff-9f2e9a08332888bca98d111787b3a8c3R770
        -- JS should not assume all the slaves are accessible on their private IP address
        for _, slave in ipairs(mesos_state['slaves']) do
            slave.hostname = ngx.var.host .. '/slave/' .. slave.id
            slave.pid = ngx.re.gsub(slave.pid, ':\\\\d+$', ':' .. ngx.var.proxy_forwarded_port, 'jo')
        end
    end

    return mesos_state
end

function _M:getSlaveAddress(slave_id)
    local state = self:getState(false)
    for _, slave in ipairs(state['slaves']) do
        if slave['id'] == slave_id then
            local slave_address = ngx.re.gsub(slave['pid'], '.*@', '', 'jo')
            return slave_address
            -- ngx.log(ngx.DEBUG, 'Resolved Mesos slave to address ', tostring(slave_address) )
        end
    end
    return nil
end

return _M

