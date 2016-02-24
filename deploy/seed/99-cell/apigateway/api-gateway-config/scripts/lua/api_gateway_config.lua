--
-- Lua module for storing API Gateway wide configs
--
-- User: ddascal
-- Date: 22/02/16
--

local _M = {}

---
-- Returns an endpoint for accessing Marathon APIs
function _M:getMarathonEndpoint()
    local cell_domain = ngx.var.domain
    local marathon_endpoint = "http://marathon.gw." .. tostring(cell_domain)
    if (cell_domain == nil) then
        ngx.log(ngx.WARN, "domain var was not configured or it's empty. Marathon endpoint won't work correctly:" , tostring(marathon_endpoint))
    end
    return marathon_endpoint
end

return _M

