local http = require "resty.http"
local mapi = require "marathon.api"
local cjson = require "cjson"

local table = require "table"
local m = mapi.new({
    marathon_endpoint="http://marathon.gw." .. ngx.var.domain
})

local _M = {}

-- find active HBase master
-- there are multiple masters running, we find the active one
-- by checking the /master-status?format=json endpoint on each one
-- returns host:port of the active master
-- this is used both for redirects and to get the config from it
function _M.find_master(app_name)
    -- get all running hbase masters
    local endpoints = m:endpoints_for_app(app_name)
    local active_master = nil
    for _, hp in ipairs(endpoints) do
        local hc = http.new()
        local possible_master_url = hp.host .. ":" .. hp.ports[1]
        -- get the url for this master
        -- if it is active, this url returns an EMPTY object {}
        -- if it is not active, it returns a non-empty json
        local check_url = "http://" .. possible_master_url .. "/master-status?format=json"
        local res, err = hc:request_uri(check_url, {
            method = "GET",
            headers = {
                ["Content-Type"] = "application/json",
            }
        })
        if res and res.status == 200 then
            local ok, res_json = pcall(cjson.decode, res.body)
            if ok then
                -- this checks if an object is empty ({})
                if next(res_json) == nil then
                    active_master = possible_master_url
                    break
                end
            end
        end
    end
    return active_master
end

-- called when accessing any url for this workload (ignoring the path query string)
function _M.exec_default()
    local active_master = _M.find_master(ngx.var.marathon_app_name)
    if not active_master then
        ngx.header.content_type = "application/json"
        ngx.say(cjson.encode({error="Can't find HBase Master"}))
        ngx.exit(ngx.HTTP_NOT_ALLOWED)
    end
    -- forward the call to the actual master (flows in marathon_apis.conf)
    ngx.var.marathon_app_name = active_master
end

-- accepted configuration keys
local accepted_keys = {
    ["hbase.zookeeper.quorum"]=true,
    ["hbase.rootdir"]=true,
    ["zookeeper.znode.parent"]=true,
}

-- called when accessing /cellos/config
-- returns a minimal set of configurations for connections to this HBase cluster
-- or the full set of configurations if the ?raw=true parameter is passed
-- zookeeper, hdfs rootdir, zookeeper parent
function _M.exec_config()
    local active_master = _M.find_master(ngx.var.marathon_app_name)

    ngx.header.content_type = "application/json"
    if not active_master then
        ngx.say(cjson.encode({error="Can't find HBase Master"}))
        return ngx.exit(ngx.HTTP_NOT_ALLOWED)
    end

    -- get the configuration in json format
    local master_conf_url = "http://" .. active_master .. "/conf?format=json"
    local hc = http.new()
    local res, err = hc:request_uri(master_conf_url, {
        method = "GET",
        headers = {
            ["Content-Type"] = "application/json",
        }
    })

    if not (res and res.status == 200) then
        ngx.say(cjson.encode({error="Can't read HBase config: " .. err}))
        return ngx.exit(ngx.HTTP_NOT_ALLOWED)
    end

    local out = {}
    local ok, res_json = pcall(cjson.decode, res.body)
    if not ok then
        ngx.say(cjson.encode({error="Can't read HBase config from response. "}))
        return ngx.exit(ngx.HTTP_NOT_ALLOWED)
    end
    -- filter out unneeded configuration keys
    for _, kv in ipairs(res_json.properties) do
        if accepted_keys[kv.key] == true or ngx.req.get_uri_args()["raw"] ~= nil then
            out[kv.key] = kv.value
        end
    end
    -- dump configuration keys
    ngx.header.content_type = "application/json"
    ngx.say(cjson.encode(out))  
    return ngx.exit(ngx.HTTP_OK)
end

return _M
