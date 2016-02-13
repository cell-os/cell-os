local http = require "resty.http"
local cjson = require "cjson"

-- transforms the Marathon workload name in the same way as for GW 
-- / -> _
local function mangled_app_name(name)
    return string.gsub(string.sub(name, 2), "/", "_")
end

local function get(url)
    local hc = http.new()
    ngx.log(ngx.DEBUG, "Making Marathon request to " .. url)
    local res, err = hc:request_uri(url, {
        method = "GET",
        headers = {
            ["Content-Type"] = "application/json",
        }
    })
    if not res or res.status ~= 200 then
        return nil
    end
    return res
end

local _M = {
    VERSION="0.1",
    marathon_endpoint = ""
}
local mt = {__index=_M}

function _M.new(o)
    local o = o or {}
    return setmetatable(o, mt)
end

function _M:app_for_name(name)
    local res = assert(
        get(self.marathon_endpoint .. "/v2/apps"),
        'Could not make request to ' .. self.marathon_endpoint .. "/v2/apps"
    )
    local apps = assert(cjson.decode(res.body), 'Could not decode ' .. tostring(res.body))
    for i, app in ipairs(apps.apps) do
        -- FIXME: stops at the first application 
        if mangled_app_name(app.id) == name then
            return app
        end
    end
    return nil
end

function _M:endpoints_for_app(app_name)
    local res = assert(
        get(self.marathon_endpoint .. "/v2/tasks"),
        'Could not make request to ' .. self.marathon_endpoint .. "/v2/tasks"
    )
    local tasks = assert(cjson.decode(res.body),  'Could not decode ' .. tostring(res.body))
    out = {}
    for i, task in pairs(tasks.tasks) do
        if mangled_app_name(task.appId) == app_name then
            table.insert(out, {host=task.host, ports=task.ports})
        end
    end
    return out
end

return _M
