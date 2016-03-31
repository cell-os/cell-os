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



=== TEST 1: test that getMesosLeader() returns the correct leader
--- http_config eval: $::HttpConfig
--- config
    error_log ../test-logs/mesos_state_test1_error.log debug;

    include /etc/api-gateway/conf.d/commons/common-headers.conf;

    set $domain cell-1;

    location /internal/master/redirect {
        return 307 http://127.0.0.1:$TEST_NGINX_PORT;
    }

    location /t {
        content_by_lua '
            local mesos_state_cls = require "mesos.MesosState"
            local m = mesos_state_cls:new()
            ngx.say("Mesos Leader is " .. m:getMesosLeader())
        ';
    }
--- request
GET /t
--- response_body
Mesos Leader is http://127.0.0.1:1981
--- no_error_log
[error]

=== TEST 2: test that getState(true) method returns modified hostname and pid
--- http_config eval: $::HttpConfig
--- config
    error_log ../test-logs/mesos_state_test2_error.log debug;

    include /etc/api-gateway/conf.d/commons/common-headers.conf;

    set $domain cell-1;

    location /internal/master/redirect {
        return 307 http://127.0.0.1:$TEST_NGINX_PORT;
    }

    location /internal/master/state {
        return 200
        '
        {
            "version": "0.28.0",
            "pid": "master@10.0.0.223:5050",
            "hostname": "ip-10-0-0-223.eu-west-1.compute.internal",
            "leader": "master@10.0.0.223:5050",
            "arg_leader" : "$arg_leader",
            "slaves": [
                {
                    "id": "S1",
                    "pid": "slave(1)@10.0.0.223:5051",
                    "hostname": "ip-10-0-0-223.eu-west-1.compute.internal"
                },{
                    "id": "S2",
                    "pid": "slave(2)@10.0.0.224:5051",
                    "hostname": "ip-10-0-0-224.eu-west-1.compute.internal"
                }
            ]
        }
        ';
    }

    location /t {
        content_by_lua '
            local mesos_state_cls = require "mesos.MesosState"
            local m = mesos_state_cls:new()
            local mesos_state = m:getState(true)
            local pids = ""
            local hostnames = ""
            for _, slave in ipairs(mesos_state.slaves) do
                pids = pids .. tostring(slave.pid) .. ","
                hostnames = hostnames .. tostring(slave.hostname) .. ","
            end
            ngx.say(pids .. hostnames .. mesos_state.arg_leader)
        ';
    }
--- request
GET /t
--- response_body
slave(1)@10.0.0.223:1981,slave(2)@10.0.0.224:1981,localhost/slave/S1,localhost/slave/S2,http://127.0.0.1:1981
--- no_error_log
[error]

=== TEST 3: test that getState() is called from the leader
--- http_config eval: $::HttpConfig
--- config
    error_log ../test-logs/mesos_state_test3_error.log debug;

    include /etc/api-gateway/conf.d/commons/common-headers.conf;

    set $domain cell-1;

    location /internal/master/redirect {
        return 307 http://127.0.0.1:$TEST_NGINX_PORT;
    }

    location /internal/master/state {
        return 200
        '
        {
            "version": "0.28.0",
            "pid": "master@10.0.0.223:5050",
            "hostname": "ip-10-0-0-223.eu-west-1.compute.internal",
            "leader": "ANOTHER_LEADER@127.0.0.1:0000",
            "arg_leader" : "$arg_leader",
            "slaves": [
                {
                    "id": "S1",
                    "pid": "slave(1)@10.0.0.223:5051",
                    "hostname": "ip-10-0-0-223.eu-west-1.compute.internal"
                },{
                    "id": "S2",
                    "pid": "slave(2)@10.0.0.224:5051",
                    "hostname": "ip-10-0-0-224.eu-west-1.compute.internal"
                }
            ]
        }
        ';
    }

    location /t {
        content_by_lua '
            local mesos_state_cls = require "mesos.MesosState"
            local m = mesos_state_cls:new()
            -- in this test we are calling getState without any arg to get the unmodified mesos response
            local mesos_state = m:getState()
            local pids = ""
            local hostnames = ""
            for _, slave in ipairs(mesos_state.slaves) do
                pids = pids .. tostring(slave.pid) .. ","
                hostnames = hostnames .. tostring(slave.hostname) .. ","
            end
            ngx.say(pids .. hostnames .. mesos_state.arg_leader)
        ';
    }
--- request
GET /t
--- response_body
slave(1)@10.0.0.223:5051,slave(2)@10.0.0.224:5051,ip-10-0-0-223.eu-west-1.compute.internal,ip-10-0-0-224.eu-west-1.compute.internal,http://127.0.0.1:1981
--- no_error_log
[error]


=== TEST 4: test that getSlaveAddress(slave_id) returns the correct address of the slave
--- http_config eval: $::HttpConfig
--- config
    error_log ../test-logs/mesos_state_test4_error.log debug;

    include /etc/api-gateway/conf.d/commons/common-headers.conf;

    set $domain cell-1;

    location /internal/master/redirect {
        return 307 http://127.0.0.1:$TEST_NGINX_PORT;
    }

    location /internal/master/state {
        return 200
        '
        {
            "version": "0.28.0",
            "pid": "master@10.0.0.223:5050",
            "hostname": "ip-10-0-0-223.eu-west-1.compute.internal",
            "leader": "ANOTHER_LEADER@127.0.0.1:0000",
            "arg_leader" : "$arg_leader",
            "slaves": [
                {
                    "id": "S1",
                    "pid": "slave(1)@10.0.0.223:5051",
                    "hostname": "ip-10-0-0-223.eu-west-1.compute.internal"
                },{
                    "id": "S2",
                    "pid": "slave(2)@10.0.0.224:5051",
                    "hostname": "ip-10-0-0-224.eu-west-1.compute.internal"
                }
            ]
        }
        ';
    }

    location /t {
        content_by_lua '
            local mesos_state_cls = require "mesos.MesosState"
            local m = mesos_state_cls:new()
            -- in this test we are calling getState without any arg to get the unmodified mesos response
            local addr = m:getSlaveAddress("S1")

            ngx.say(addr)
        ';
    }
--- request
GET /t
--- response_body
10.0.0.223:5051
--- no_error_log
[error]



