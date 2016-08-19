import json
import sys
import logging

logging.basicConfig(
    filename='/var/log/api-gateway/mesos-service-discovery.log',
    filemode='a',
    level=logging.DEBUG)

SERVER_FAIL_TIMEOUT_SECONDS = 10
UPSTREAM_KEEP_ALIVE = 16

"""
Create a list of Api Gateway / Openresty upstreams from the list
of tasks in running Mesos frameworks.
Mesos frameworks are started in Marathon, but we might want to create load
balancer pools directly over the Mesos framework tasks;

For example, Elasticsearch starts only 1 task in Marathon (the actual
framework), but the servers in the Elasticsearch cluster are not known
to Marathon.

The list of running frameworks and each task for the frameworks can be found
at this Mesos HTTP endpoint:

http://mesos.apache.org/documentation/latest/endpoints/master/state.json/

TODO: highly dependent on state.json format, we need to find a way to test
      this automatically all the time
"""

def mesos_port_declaration(decl):
    """
    parses Mesos port declarations into number array
    E.g:
        [31000-31002] -> [31000, 31001, 31002]
    """
    tmp = map(lambda i: int(i), decl[1:-1].split("-"))
    # range is [start, end), so we need to add 1
    return range(tmp[0], tmp[1] + 1)

def make_server_upstream(ip, port):
    return "server {} fail_timeout={}s;".format(
        ip + ":" + str(port), SERVER_FAIL_TIMEOUT_SECONDS
    )

def mesos_state_to_upstream_defs(mesos_state_json):
    """
    - parses Mesos state.json
    - for each framework:
        - find all tasks
        - only export the external ones if tasks have visibility specified
        - export all if the "visibility" tag is missing
    """
    apigateway_conf = []
    for framework in mesos_state_json["frameworks"]:
        if framework["active"] == False:
            continue
        name = framework["name"]
        discoverable_tasks = {}
        all_tasks = {}
        has_discoverable_tasks = False
        for task in framework["tasks"]:
            if task["state"] != "TASK_RUNNING":
                continue
            try:
                lsi = len(task["statuses"]) - 1
                ip = task["statuses"][lsi]["container_status"]\
                    ["network_infos"][0]["ip_addresses"][0]["ip_address"]
                # Mesos tasks are tagged with a discovery tag
                # http://mesos.apache.org/documentation/latest/app-framework-development-guide/
                # However, this part of the task info is optional, so we are
                # being conservative:
                # if the task does not contain this DiscoveryInfo,
                # we treat it as externally visible
                if "discovery" in task and \
                    task["discovery"]["visibility"] != "FRAMEWORK":
                    has_discoverable_tasks = True
                    if "ports" in task["discovery"]["ports"]:
                        for idx, raw_port in enumerate(
                            task["discovery"]["ports"]["ports"]
                        ):
                            port = raw_port["number"]
                            upstream_name = "{}_{}_{}".format(
                                name,
                                task["discovery"]["visibility"].lower(),
                                idx
                            )
                            discoverable_tasks.setdefault(
                                upstream_name,
                                []
                            ).append(make_server_upstream(ip, port))
                elif not "discovery" in task:
                    if "ports" in task["resources"]:
                        ports = mesos_port_declaration(
                            task["resources"]["ports"]
                        )
                        for idx, port in enumerate(ports):
                            all_tasks.setdefault(
                                "{}_external_{}".format(name, idx), []
                            ).append(make_server_upstream(ip, port))
            except Exception as e:
                logging.exception("Error reading tasks for framework {}".format(
                    name)
                )

        if has_discoverable_tasks:
            upstream_def = discoverable_tasks
        else:
            upstream_def = all_tasks

        for upstream_name, upstreams in upstream_def.iteritems():
            apigateway_conf.append("""\
upstream {}_tasks {{
{}
keepalive {};
}}""".format(upstream_name, "\n  ".join(upstreams), UPSTREAM_KEEP_ALIVE))

    return "\n".join(apigateway_conf)

if __name__ == "__main__":
    mesos_state_json = json.loads(sys.stdin.read())
    print mesos_state_to_upstream_defs(mesos_state_json)
