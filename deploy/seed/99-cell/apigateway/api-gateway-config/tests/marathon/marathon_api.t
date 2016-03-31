# vim:set ft= ts=4 sw=4 et fdm=marker:
use lib 'lib';
use strict;
use warnings;
use Test::Nginx::Socket::Lua;
use Cwd qw(cwd);

repeat_each(2);

plan tests => repeat_each() * (blocks() * 3);

my $pwd = cwd();

our $HttpConfig = <<_EOC_;
    # lua_package_path "$pwd/lib/?.lua;;";
#    init_by_lua '
#        local v = require "jit.v"
#        v.on("$Test::Nginx::Util::ErrLogFile")
#        require "resty.core"
#    ';

    client_body_temp_path /tmp/;
    proxy_temp_path /tmp/;
    fastcgi_temp_path /tmp/;

    include /etc/api-gateway/environment.conf.d/api-gateway-env.http.conf;
    geo \$http_x_forwarded_for \$is_admin_zone_ip {
        127.0.0.1 1;
    }
    include /etc/api-gateway/conf.d/commons/blacklist.conf;

    include /etc/api-gateway/conf.d/*.conf;
_EOC_

no_long_string();
run_tests();

__DATA__

=== TEST 1: check that marathon endpoint is set correctly
--- http_config eval: $::HttpConfig
--- config
    error_log ../test-logs/marathon_api_test1_error.log debug;

    set $domain cell-1;
    set $marathon_app_name test-app;

    location /t {
        content_by_lua '
            local mapi = require "marathon.api"
            local m = mapi.new()
            ngx.say(m.marathon_endpoint)
        ';
    }
--- request
GET /t
--- response_body_like eval
["http://marathon.gw.cell-1"]
--- no_error_log
[error]

=== TEST 2: check app info is retrieved correctly
--- http_config eval: $::HttpConfig
--- config
    error_log ../test-logs/marathon_api_test2_error.log debug;

    set $domain cell-1;
    set $marathon_endpoint http://127.0.0.1:$TEST_NGINX_PORT;
    set $marathon_app_name test-app;

    location /v2/apps {
        return 200 '{
            "apps": [{"id": "/test-app"},{"id": "/app2"}]
        }';
    }

    location /t {
        content_by_lua '
            local cjson = require "cjson"
            local mapi = require "marathon.api"
            local m = mapi.new()
            -- overwrite Marathon endpoint
            m.marathon_endpoint = ngx.var.marathon_endpoint
            local app_info = m:app_for_name("test-app")
            ngx.print(cjson.encode(app_info.id))
        ';
    }
--- request
GET /t
--- response_body_like eval
['test-app']
--- no_error_log
[error]


=== TEST 3: test when domain var is not set
--- http_config eval: $::HttpConfig
--- config
    error_log ../test-logs/marathon_api_test3_error.log debug;

    set $marathon_app_name test-app;

    location /t {
        content_by_lua '
            local mapi = require "marathon.api"
            local m = mapi.new()
            ngx.say(m.marathon_endpoint)
        ';
    }
--- request
GET /t
--- response_body_like eval
["http://marathon.gw.*"]
--- no_error_log
[error]

