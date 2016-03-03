local http = require "resty.http"
local cjson = require "cjson"

local _M = {
    VERSION = "0.1"
}
local mt = {__index=_M}

function _M.find_active_namenode()
    local hc = http.new()
    local nn1_url = "http://" .. ngx.var.hdfs_nn1 .. ":" .. ngx.var.hdfs_http_port.. "/jmx?qry=Hadoop:service=NameNode,name=NameNodeStatus"
    local res, err = hc:request_uri(nn1_url, {
        method = "GET",
        headers = {
            ["Content-Type"] = "application/json",
        }
    })
    if err ~= nil or (err == nil and res.status ~= 200) then
        return ngx.var.hdfs_nn2
    end

    local ok, nn1_jmx_bean = pcall(cjson.decode, res.body)
    if (not ok) then
        ngx.log(ngx.WARN, 'Could not decode HDFS response from ', tostring(ngx.var.hdfs_nn1), '. Response=', tostring(res.body))
        return ngx.var.hdfs_nn2
    end

    -- hdfs_state contains a piece of JMX response containing the active namenode
    if nn1_jmx_bean ~= nil and nn1_jmx_bean.beans ~= nil then
        nn1_state = nn1_jmx_bean.beans[1]
        -- nn1_state - object containing namenode state
        if nn1_state.State ~= 'active' then
            -- NOTE: at the moment when NN2 becomes unavailable the cell doesn't recover
            ngx.var.hdfs_active_nn = ngx.var.hdfs_nn2
            return ngx.var.hdfs_nn2
        end
    end
    return ngx.var.hdfs_nn1
end

local accepted_keys = {
    ["fs.default.name"]=true,
    ["dfs.nameservice.id"]=true,
    ["dfs.nameservices"]=true,
    ["dfs%.namenode%.rpc%-address.*"]=true,
    ["dfs%.namenode%.http%-address.*"]=true,
    ["dfs%.ha%.namenodes.*"]=true,
    ["dfs%.client%.failover%.proxy%.provider.*"]=true,
}

function _M.get_config(file)
    local active_nn = _M.find_active_namenode(ngx.var.marathon_app_name)

    if not active_nn then
        return cjson.encode({error="Can't find HDFS Active NameNode"}), nil
    end

    -- get the actual config from the namenode
    local nn_conf_url = "http://" .. active_nn .. ":" .. ngx.var.hdfs_http_port .. "/conf?format=json"
    local hc = http.new()
    local res, err = hc:request_uri(nn_conf_url, {
        method = "GET",
        headers = {
            ["Content-Type"] = "application/json",
        }
    })
    if not (res and res.status == 200) then
        return cjson.encode({error="Can't read HDFS Config: " .. err}), nil
    end
    local ok, res_json = pcall(cjson.decode, res.body)
    if not ok then
        return cjson.encode({error="Can't read HDFS config from response. "}), nil
    end

    -- filter out un-needed configuration keys
    local out = {}
    -- keep track of the nameservice key
    local nameservice = nil
    for _, prop in ipairs(res_json.properties) do
        if prop.resource == "hdfs-site.xml" or prop.resource == "core-site.xml" then
            if prop.key == "dfs.nameservices" then
                nameservice = prop.value
            end

            local is_source_ok = true
            if file ~= nil and prop.resource ~= file then
                is_source_ok = false
            end

            local is_key_ok = false
            if ngx.req.get_uri_args()["raw"] ~= nil then
                is_key_ok = true
            else
                is_key_ok = accepted_keys[prop.key] == true
                if not is_key_ok then
                    for key_regex, _ in pairs(accepted_keys) do
                        if string.match(prop.key, key_regex) then
                            is_key_ok = true
                            break
                        end
                    end
                end
            end

            if is_key_ok and is_source_ok then
                out[prop.key] = prop.value
            end
        end
    end

    -- we can't use the values for fs.defaultFS, because they are translated to the NN host
    if out["fs.defaultFS"] or (file ~= nil and file == "core-site.xml") then
        out["fs.defaultFS"] = nameservice
    end
    return nil, out
end

xml_prefix = [[
<?xml version="1.0"?>
<configuration>
]]

xml_suffix = [[
</configuration>
]]

xml_prop = [[
  <property>
    <name>%s</name>
    <value>%s</value>
  </property>
]]

function _M.exec_config(file)
    -- dump configuration keys
    local err, config = _M.get_config(file)
    if err ~= nil then
        ngx.say(err)
        return ngx.exit(ngx.HTTP_NOT_ALLOWED)
    end

    if file == nil then
        ngx.header.content_type = "application/json"
        ngx.say(cjson.encode(config))  
        return ngx.exit(ngx.HTTP_OK)
    else
        ngx.header.content_type = "application/xml"
        local xml = xml_prefix
        for k, v in pairs(config) do
            xml = xml .. string.format(xml_prop, k, v)
        end
        xml = xml .. xml_suffix
        ngx.say(xml)
        return ngx.exit(ngx.HTTP_OK)
    end
end

return _M
