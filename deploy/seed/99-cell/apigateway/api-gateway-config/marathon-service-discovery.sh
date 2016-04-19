#!/bin/sh
#/*
# * Copyright (c) 2012 Adobe Systems Incorporated. All rights reserved.
# *
# * Permission is hereby granted, free of charge, to any person obtaining a
# * copy of this software and associated documentation files (the "Software"),
# * to deal in the Software without restriction, including without limitation
# * the rights to use, copy, modify, merge, publish, distribute, sublicense,
# * and/or sell copies of the Software, and to permit persons to whom the
# * Software is furnished to do so, subject to the following conditions:
# *
# * The above copyright notice and this permission notice shall be included in
# * all copies or substantial portions of the Software.
# *
# * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# * DEALINGS IN THE SOFTWARE.
# *
# */

#
#  Overview:
#    It reads the list of tasks from Marathon and it dynamically generates the Nginx configuration with the upstreams.
#
#    In order to gather the information the script needs to know where to find Marathon
#       so it looks for the $MARATHON_HOST environment variable.
#

TMP_DIR=/tmp/
CONFIG_DIR=/etc/api-gateway/environment.conf.d/
marathon_host=$(echo $MARATHON_HOST)

do_log() {
        local _MSG=$1
        echo "`date +'%Y/%m/%d %H:%M:%S'` - marathon-service-discovery: ${_MSG}"
}

fatal_error() {
        local _MSG=$1
        do_log "ERROR: ${_MSG}"
        exit 255
}

info_log() {
        local _MSG=$1
        do_log "${_MSG}"
}

# 1. create the new vars config
VARS_FILE_NAME=api-gateway-vars.server.conf
TMP_VARS_FILE=${TMP_DIR}/${VARS_FILE_NAME}
VARS_FILE=${CONFIG_DIR}/${VARS_FILE_NAME}
# jq outputs the json tree as 
# labels /hbase-master lb:enabled true
# labels /hbase-master lb:module hbase
curl -s ${marathon_host}/v2/apps | jq -r '.apps[] as $app | $app.labels|to_entries as $labels | $labels[] | [$app.id, .key, .value] | join("\t")' | gawk '
{
  if ($2 !~ /DCOS_/) { # ignore DCOS variables
    # add to a map because I do not want to depend on order
    # the output from Marathon / Jq might have the values in a different order
    labels[$1 "_" $2]=$3
  }
}
END {
  for (key in labels) {
    # start from 2 so that we ignore the initial slash
    # /hbase-master_lb:module -> hbase_master_lb_module
    var_name = gensub(/[:\-|\.\/]/, "_", "G", substr(key, 2))
    print "set $" var_name " \"" labels[key] "\";"
  }
}
' > ${TMP_VARS_FILE}

# 2. create the new upstream config
UPSTREAM_FILE_NAME=api-gateway-upstreams.http.conf
TMP_UPSTREAM_FILE=${TMP_DIR}/${UPSTREAM_FILE_NAME}
UPSTREAM_FILE=${CONFIG_DIR}/${UPSTREAM_FILE_NAME}
curl -s ${marathon_host}/v2/tasks -H "Accept:text/plain" | gawk '
{
  app=$1
  port_index[app]++

  # compute the upstream servers list from this line
  servers="";
  for (f=3; f<=NF; f++) {
    servers = servers "\n server " $f " fail_timeout=10s;";
  }
  # if this is the first port, expose it as "workload"
  if (port_index[app] == 1 && servers != "") {
    print "upstream " app " {" servers "\n keepalive 16;\n}";
  }

  # for the rest of the ports, also expose "workload_port0", "workload_port1" etc
  if (servers != "") {
    print "upstream " app "_port" (port_index[app]-1) " {" servers "\n keepalive 16;\n}";
  }
}
' > ${TMP_UPSTREAM_FILE}

# 2.1. check redis upstreams
# ASSUMPTION:  there is a redis app named "api-gateway-redis" deployed in marathon and optionally another app named "api-gateway-redis-replica"
#
redis_master=$(cat ${TMP_UPSTREAM_FILE} | grep api-gateway-redis | wc -l)
redis_replica=$(cat ${TMP_UPSTREAM_FILE} | grep api-gateway-redis-replica | wc -l)
#      if api-gateway-redis upstream exists but api-gateway-redis-replica does not, then create the replica
if [ ${redis_master} -gt 0 ] && [ ${redis_replica} -eq 0 ]; then
    # clone api-gateway-redis block
    sed -e '/api-gateway-redis/,/}/!d' ${TMP_UPSTREAM_FILE} | sed 's/-redis/-redis-replica/' >> ${TMP_UPSTREAM_FILE}
fi

if [ ${redis_master} -eq 0 ]; then
    echo "upstream api-gateway-redis { server 127.0.0.1:6379; }" >> ${TMP_UPSTREAM_FILE}
fi

# 2.2 mesos tasks upstream
MESOS_UPSTREAM_FILE_NAME=api-gateway-mesos-upstreams.http.conf
TMP_MESOS_UPSTREAM_FILE=${TMP_DIR}/${MESOS_UPSTREAM_FILE_NAME}
MESOS_UPSTREAM_FILE=${CONFIG_DIR}/${MESOS_UPSTREAM_FILE_NAME}
MESOS_LOCATION=$(curl -i $MESOS_MASTER_HOST/master/redirect 2>/dev/null | grep "Location:" | tr '\r' ' ' | awk '{print $2}')
curl "http:${MESOS_LOCATION}/state.json" 2>/dev/null | python /etc/api-gateway/mesos-service-discovery.py > ${TMP_MESOS_UPSTREAM_FILE}

# 2. check for changes
changed_files=$(find /etc/api-gateway -type f -newer /var/run/apigateway-config-watcher.lastrun -print)
# check both the vars and upstream files
cmp -s ${TMP_UPSTREAM_FILE} ${UPSTREAM_FILE}
changed_upstreams=$?
cmp -s ${TMP_VARS_FILE} ${VARS_FILE}
changed_vars=$?
cmp -s ${TMP_MESOS_UPSTREAM_FILE} ${MESOS_UPSTREAM_FILE}
changed_mesos_upstreams=$?
# if any of the Api Gateway configuration files has changed, reload the configuration
# We might get changes when something happens in Marathon or in Mesos
if [[ \( -n "${changed_files}" \) -o \( ${changed_upstreams} -gt 0 \) -o \( ${changed_vars} -gt 0 \) -o \( ${changed_mesos_upstreams} -gt 0 \) ]]; then
    info_log "discovered changed files ..."
    info_log ${changed_files}
    cp ${TMP_UPSTREAM_FILE} ${UPSTREAM_FILE}
    cp ${TMP_VARS_FILE} ${VARS_FILE}
    cp ${TMP_MESOS_UPSTREAM_FILE} ${MESOS_UPSTREAM_FILE}
    info_log "reloading gateway ..."
    api-gateway -t -p /usr/local/api-gateway/ -c /etc/api-gateway/api-gateway.conf && api-gateway -s reload
fi

echo `date` > /var/run/apigateway-config-watcher.lastrun
