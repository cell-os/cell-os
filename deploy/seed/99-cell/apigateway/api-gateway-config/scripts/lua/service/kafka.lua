local http = require "resty.http"
local mapi = require "marathon.api"
local cjson = require "cjson"

local _M = {}

function _M.exec_default() 
    -- pass through to defaults
end

function _M.exec_config()
    local m = mapi.new({
        marathon_endpoint="http://marathon.gw." .. ngx.var.domain
    })
    local endpoints = m:endpoints_for_app(ngx.var.marathon_app_name)
    if #endpoints < 1 then
      ngx.header.content_type = "application/json; charset=utf-8"
      ngx.say(cjson.encode({ error = "Application has no endpoints" }))
      return ngx.exit(ngx.HTTP_OK)
    end
    out = {}
    local scheduler_url = "http://" .. endpoints[1].host .. ":" .. endpoints[1].ports[1] .. "/api/broker/list"

    local hc = http.new()
    local res, err = hc:request_uri(scheduler_url, {
        method = "GET",
        headers = {
            ["Content-Type"] = "application/json",
        }
    })
    if err == nil and res.status == 200 then
        local brokers = cjson.decode(res.body)
        for _, broker in ipairs(brokers.brokers) do
            if broker.task.state == "running" then
                table.insert(out, broker.task.endpoint)
            end
        end
    end
    ngx.status = ngx.HTTP_OK  
    ngx.header.content_type = "application/json; charset=utf-8"  
    ngx.say(cjson.encode({ brokers = out }))  
    return ngx.exit(ngx.HTTP_OK)  
end

return _M
