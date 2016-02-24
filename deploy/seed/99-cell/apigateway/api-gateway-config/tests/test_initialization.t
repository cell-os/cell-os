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
    include /etc/api-gateway/conf.d/commons/whitelist.conf;
    include /etc/api-gateway/conf.d/commons/blacklist.conf;

    include /etc/api-gateway/conf.d/*.conf;
_EOC_

no_long_string();
run_tests();

__DATA__

=== TEST 1: check that JIT is enabled
--- http_config eval: $::HttpConfig
--- config
    location /jitcheck {
        content_by_lua '
            if jit then
                ngx.say(jit.version);
            else
                ngx.say("JIT Not Enabled");
            end
        ';
    }
--- request
GET /jitcheck
--- response_body_like eval
["LuaJIT .*"]
--- no_error_log
[error]

=== TEST 2: check health-check page
--- http_config eval: $::HttpConfig
--- config
    location /health-check {
        access_log off;
            # MIME type determined by default_type:
            default_type 'text/plain';

            content_by_lua "ngx.say('API-Platform is running!')";
    }
--- request
GET /health-check
--- response_body_like eval
["API-Platform is running!"]
--- no_error_log
[error]

=== TEST 3: check nginx_status is enabled
--- http_config eval: $::HttpConfig
--- config
    location /nginx_status {
            stub_status on;
            access_log   off;
            allow 127.0.0.1;
            deny all;
    }
--- request
GET /nginx_status
--- response_body_like eval
["Active connections: 1"]
--- no_error_log
[error]

