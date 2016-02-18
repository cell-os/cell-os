local http = require "resty.http"
local mapi = require "marathon.api"
local cjson = require "cjson"

local inspect = require "inspect"
local table = require "table"
local m = mapi.new({
    marathon_endpoint="http://marathon.gw." .. ngx.var.domain
})

local _M = {}

function _M.exec_default()
    local endpoints = m:endpoints_for_app(ngx.var.marathon_app_name)
    local active_master = ""
    for _, hp in ipairs(endpoints) do
        local hc = http.new()
        local possible_master_url = hp.host .. ":" .. hp.ports[1]
        local check_url = "http://" .. possible_master_url .. "/master-status?format=json"
        local res, err = hc:request_uri(check_url, {
            method = "GET",
            headers = {
                ["Content-Type"] = "application/json",
            }
        })
        if res and res.status == 200 then
            res_json = cjson.decode(res.body)
            if next(res_json) == nil then
                ngx.var.marathon_app_name = possible_master_url
                break
            end
        end
    end
end

local accepted_keys = {
    "hbase.zookeeper.quorum"=true,
    "hbase.rootdir"=true,
    "zookeeper.znode.parent"=true,
}

function _M.exec_config()
    ngx.say(cjson.encode({error="Not Implemented"})
    local hc = http.new()
    local master_conf_url = ngx.var.marathon_app_name .. ".gw." .. ngx.var.domain .. "/conf?format=json"
    ngx.log(ngx.WARN, "AAAAAAAAAA" .. master_conf_url)
    local res, err = hc:request_uri(master_conf_url, {
        method = "GET",
        headers = {
            ["Content-Type"] = "application/json",
        }
    })
    out = {}
    if res and res.status == 200 then
        res_json = cjson.decode(res.body)
        ngx.log(ngx.WARN, "AAAAAAAA" .. inspect(res_json))
        for _, kv in ipairs(res_json.properties) do
            if accepted_keys[kv.key] then
                out[kv.key] = kv.value
            end
        end
    end
    ngx.say(cjson.encode(out))  
    return ngx.exit(ngx.HTTP_OK))
end

return _M
