# Intro

The Adobe.io gateway is an NGINX server with a series of addons for load balancing, service discovery, etc.

The docker image we use comes preconfigured to enable HDFS, Mesos, Marathon and Zookeeper(Exhibitor) access out of the box (through simple env configuration).

In addition the gateway syncs it's entire configuration from a remote source (currently S3 set through `REMOTE_CONFIG` env var).

Gateway provisioning

https://git.corp.adobe.com/metal-cell/cell-os/blob/master/deploy/seed/99-cell/provision_post


To manually start a gw container:
```
docker run \
-e "MARATHON_HOST=http://ip-10-27-15-200.ut1.adobe.net:8080" \
-e "MESOS_MASTER_HOST=http://ip-10-27-15-203.ut1.adobe.net:5050" \
-e "HDFS_NN1_HOST=ip-10-27-15-201.ut1.adobe.net" \
-e "HDFS_NN2_HOST=ip-10-27-15-201.ut1.adobe.net" \
-e "REMOTE_CONFIG=s3://cell-os--c4/cell-os--c4/membrane/apigateway/api-gateway-config" \
-e "LOG_LEVEL=debug" \
-e "AWS_ACCESS_KEY_ID=xxxxxxxxxxxxxxxxxxxxxx" \
-e "AWS_SECRET_ACCESS_KEY=yyyyyyyyyyyyyyyyyy" \
--net=host \
cellos/apigateway:1.9.7.3
```

To attach to an existing gateway:

#### SSH into one membrane node

    ./cell ssh <cell> membrane 1


#### Attaching to a gateway container

    docker ps # to get the gw container id
    docker exec -it <container> bash

#### Inside the container

* `/etc/api-gateway` - this is where the gw configuration is synced from `REMOTE_CONFIG` path

#### Reload the gateway with the latest configuration

    api-gateway -s reload
    
> TIP: Before reloading the configuration make sure it is correct by running:
    ```
    api-gateway -t -p /usr/local/api-gateway/ -c /etc/api-gateway/api-gateway.conf
    ```
# Logging

The API Gateway write logs in 2 places :
* `access_log` goes to `stdout`
* `error_log` goes to `stderr`

This brings the following advantages: 
* all the logs written by the API Gateway are accessible via the Mesos UI
* `stdout` and `stderrr` logs can be rotated automatically by Mesos

Logs could also be written inside `/mnt/mesos/sandbox/` folder and they would show up in the Mesos UI. This option should be used for debugging purposes only as these log files are not rotated automatically by Mesos. To debug a single location follow these steps: 

1. inside that location block add 
   `error_log /mnt/mesos/sandbox/foo_error.log debug` or 
   `access_log /mnt/mesos/sandbox/foo_access.log platform;`
2. update the configuration and reload the gateway
3. go into the Mesos UI and view `foo_error.log` or `foo_access.log`. 

A more concrete example with an API Gateawy location block:

```nginx
location /foo {
  error_log /mnt/mesos/sandbox/foo_error.log debug;
} 
```

# Marathon generated 
`/etc/apigateway/environment.conf.d/api-gateway-upstreams.http.conf`

